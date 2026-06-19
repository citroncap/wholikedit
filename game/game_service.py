"""Core game logic: video pool, round management, scoring.

Runs entirely on the host machine. GameService is stateful; create one
per game session.
"""
from __future__ import annotations
import random
import logging
import time
from typing import Optional
from models.game import GameVideo, GameSettings, PlayerAnswer, RoundResult
from models.player import Player
from models.score import Leaderboard, LeaderboardEntry
from utils.config import SCORE_BASE

log = logging.getLogger(__name__)


class GameService:
    def __init__(self, settings: GameSettings) -> None:
        self._settings       = settings
        self._players:  list[Player]     = []
        self._pool:     list[GameVideo]  = []   # full shuffled pool
        self._rounds:   list[GameVideo]  = []   # selected videos for this game
        self._scores:   dict[str, int]   = {}   # player_id → cumulative score
        self._answers:  dict[str, PlayerAnswer] = {}  # current round answers
        self._round_idx = -1
        self._round_start_time: float = 0.0

    # ── Setup ────────────────────────────────────────────────────────────────

    def set_players(self, players: list[Player]) -> None:
        self._players = list(players)
        self._scores  = {p.player_id: 0 for p in players}

    def add_player_videos(
        self, player_id: str, videos: list[dict]
    ) -> None:
        """Accept both old API format (video_id/thumbnail_url) and
        liked-videos browser format (id/thumbnail/url).
        """
        for v in videos:
            try:
                video_id = v.get("video_id") or v.get("id", "")
                if not video_id:
                    continue
                gv = GameVideo(
                    video_id=       video_id,
                    description=    v.get("description", ""),
                    thumbnail_url=  v.get("thumbnail_url") or v.get("thumbnail") or "",
                    thumbnail_path= v.get("thumbnail_path"),
                    author_username=v.get("author_username") or v.get("author", ""),
                    view_count=     v.get("view_count", 0),
                    like_count=     v.get("like_count", 0),
                    owner_player_id=player_id,
                    video_url=      v.get("url") or v.get("video_url", ""),
                )
                self._pool.append(gv)
            except (KeyError, TypeError) as exc:
                log.warning("Skipping malformed video dict: %s", exc)

    def build_rounds(self) -> int:
        """Build rounds with fair round-robin distribution across players."""
        if not self._pool:
            log.warning("Video pool is empty; using placeholder rounds")
            self._rounds = self._placeholder_rounds()
            return len(self._rounds)

        # Group by player and shuffle each bucket individually
        by_player: dict[str, list[GameVideo]] = {}
        for v in self._pool:
            by_player.setdefault(v.owner_player_id, []).append(v)
        for vlist in by_player.values():
            random.shuffle(vlist)

        # Round-robin interleave so every player contributes equally
        player_order = list(by_player.keys())
        random.shuffle(player_order)
        result: list[GameVideo] = []
        while len(result) < self._settings.total_rounds:
            added_any = False
            for pid in player_order:
                if by_player[pid] and len(result) < self._settings.total_rounds:
                    result.append(by_player[pid].pop(0))
                    added_any = True
            if not added_any:
                break

        random.shuffle(result)  # final shuffle hides the interleave pattern
        self._rounds = result
        log.info(
            "Built %d rounds from %d players (%d total videos)",
            len(self._rounds), len(by_player), len(self._pool),
        )
        return len(self._rounds)

    def _placeholder_rounds(self) -> list[GameVideo]:
        """Minimal fallback when no videos were synced."""
        descriptions = [
            "Cat video 🐱", "Cooking fail 🍳", "Dance challenge 💃",
            "Nature clip 🌿", "Tech unboxing 📦", "Funny dog 🐶",
            "Sunset reel 🌅", "Street food tour 🍜", "Gaming clip 🎮",
            "Travel vlog ✈️",
        ]
        players = self._players or []
        return [
            GameVideo(
                video_id=f"placeholder_{i}",
                description=descriptions[i % len(descriptions)],
                thumbnail_url="",
                thumbnail_path=None,
                author_username="@unknown",
                view_count=random.randint(1000, 1_000_000),
                like_count=random.randint(100, 100_000),
                owner_player_id=(players[i % len(players)].player_id if players else ""),
            )
            for i in range(min(self._settings.total_rounds, 10))
        ]

    # ── Round lifecycle ───────────────────────────────────────────────────────

    @property
    def total_rounds(self) -> int:
        return len(self._rounds)

    @property
    def current_round_number(self) -> int:
        return self._round_idx + 1

    @property
    def has_next_round(self) -> bool:
        return self._round_idx + 1 < len(self._rounds)

    def begin_next_round(self) -> Optional[GameVideo]:
        if not self.has_next_round:
            return None
        self._round_idx += 1
        self._answers   = {}
        self._round_start_time = time.perf_counter()
        return self._rounds[self._round_idx]

    def current_video(self) -> Optional[GameVideo]:
        if 0 <= self._round_idx < len(self._rounds):
            return self._rounds[self._round_idx]
        return None

    # ── Answer processing ─────────────────────────────────────────────────────

    def record_answer(
        self,
        player_id: str,
        guessed_player_id: str,
        elapsed_ms: int,
    ) -> Optional[PlayerAnswer]:
        """Record one player's answer. Returns None if already answered."""
        if player_id in self._answers:
            return None
        video = self.current_video()
        if not video:
            return None

        is_correct = guessed_player_id == video.owner_player_id
        points = 0
        if is_correct:
            timer_ms = self._settings.timer_seconds * 1000
            if timer_ms > 0:
                remaining = max(0, timer_ms - elapsed_ms)
                points = max(10, int(SCORE_BASE * remaining / timer_ms))
            else:
                points = SCORE_BASE

        answer = PlayerAnswer(
            player_id=player_id,
            guessed_player_id=guessed_player_id,
            elapsed_ms=elapsed_ms,
            is_correct=is_correct,
            points_earned=points,
        )
        self._answers[player_id] = answer
        self._scores[player_id] = self._scores.get(player_id, 0) + points
        return answer

    def all_answered(self) -> bool:
        video = self.current_video()
        owner_id = video.owner_player_id if video else ""
        eligible = sum(1 for p in self._players if p.player_id != owner_id)
        return len(self._answers) >= max(1, eligible)

    def end_round(self) -> RoundResult:
        video  = self.current_video()
        owner  = next(
            (p for p in self._players if p.player_id == video.owner_player_id),
            None,
        )
        return RoundResult(
            round_number=     self._round_idx + 1,
            video=            video,
            correct_player_id= video.owner_player_id,
            correct_display_name= owner.display_name if owner else "Unknown",
            answers=          list(self._answers.values()),
        )

    # ── Scores ────────────────────────────────────────────────────────────────

    def scores(self) -> dict[str, int]:
        return dict(self._scores)

    def build_leaderboard(self) -> Leaderboard:
        entries: list[LeaderboardEntry] = []
        for p in self._players:
            pid = p.player_id
            player_answers = [
                a for rnd in self._rounds
                for a in [self._answers.get(pid)]
                if a is not None
            ]
            # Recount from all game answers
            all_answers = self._collect_all_answers(pid)
            correct = sum(1 for a in all_answers if a.is_correct)
            total   = len(all_answers)
            avg_ms  = (sum(a.elapsed_ms for a in all_answers) / total) if total else 0

            entries.append(LeaderboardEntry(
                player_id=     pid,
                display_name=  p.display_name,
                avatar_color=  p.avatar_color,
                total_points=  self._scores.get(pid, 0),
                correct_answers=correct,
                total_rounds=  self.total_rounds,
                avg_elapsed_ms=avg_ms,
            ))
        board = Leaderboard(entries=entries)
        board.sort()
        return board

    def _collect_all_answers(self, player_id: str) -> list[PlayerAnswer]:
        """We track answers only for the current round in _answers.
        Use scores to back-calculate; store all answers in a separate list.
        """
        # Simple approach: only current-round data available here.
        # For history, game_screen accumulates answers per round.
        a = self._answers.get(player_id)
        return [a] if a else []

    # ── Choices ───────────────────────────────────────────────────────────────

    def get_choices(self, video: GameVideo) -> list[Player]:
        """Return 4 shuffled player choices for a round (includes correct owner)."""
        correct = next((p for p in self._players if p.player_id == video.owner_player_id), None)
        others  = [p for p in self._players if p.player_id != video.owner_player_id]
        random.shuffle(others)
        choices = ([correct] + others[:3]) if correct else others[:4]
        random.shuffle(choices)
        return choices


class HostGameController:
    """Coordinates GameService, GameHost networking, and UI callbacks.

    The host uses this as its game state machine.
    """

    def __init__(
        self,
        service:     "GameService",
        host_server: "GameHost",           # type: ignore  (avoid circular import)
    ) -> None:
        self._svc    = service
        self._server = host_server
        # Map player_id → all answers across all rounds for leaderboard
        self._all_answers: dict[str, list[PlayerAnswer]] = {}

    def on_answer_received(
        self, player_id: str, guessed: str, elapsed_ms: int
    ) -> None:
        answer = self._svc.record_answer(player_id, guessed, elapsed_ms)
        if answer:
            pid = answer.player_id
            self._all_answers.setdefault(pid, []).append(answer)

    def end_round_and_broadcast(self) -> RoundResult:
        result  = self._svc.end_round()
        answers = [
            {
                "player_id":        a.player_id,
                "display_name":     self._player_name(a.player_id),
                "guessed_player_id": a.guessed_player_id,
                "is_correct":       a.is_correct,
                "points":           a.points_earned,
                "elapsed_ms":       a.elapsed_ms,
            }
            for a in result.answers
        ]
        self._server.broadcast_round_result(
            round_number=           result.round_number,
            correct_player_id=      result.correct_player_id,
            correct_display_name=   result.correct_display_name,
            answers=                answers,
            scores=                 self._svc.scores(),
        )
        return result

    def build_leaderboard(self) -> Leaderboard:
        """Build leaderboard using accumulated all-round answers."""
        board = self._svc.build_leaderboard()
        # Patch entries with full correct/total counts from all rounds
        for entry in board.entries:
            all_a = self._all_answers.get(entry.player_id, [])
            entry.correct_answers = sum(1 for a in all_a if a.is_correct)
            entry.total_rounds    = self._svc.total_rounds
            entry.avg_elapsed_ms  = (
                sum(a.elapsed_ms for a in all_a) / len(all_a) if all_a else 0
            )
        board.sort()
        return board

    def _player_name(self, player_id: str) -> str:
        p = next((x for x in self._svc._players if x.player_id == player_id), None)
        return p.display_name if p else player_id
