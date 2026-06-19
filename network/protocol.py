"""Network message type constants and helpers.

All messages are newline-delimited JSON over TCP.
Format: {"type": "<MSG_TYPE>", ...fields...}\n
"""
from __future__ import annotations
import json

# ── Client → Host ─────────────────────────────────────────────────────────────
MSG_JOIN_REQUEST   = "join_request"    # {player_id, display_name, avatar_color}
MSG_VIDEO_SYNC     = "video_sync"      # {videos: [{video_id, description, thumbnail_url, author_username, view_count, like_count}]}
MSG_PLAYER_READY   = "player_ready"    # {ready: bool}
MSG_ANSWER         = "answer"          # {guessed_player_id: str, elapsed_ms: int}
MSG_PING           = "ping"            # {}

# ── Host → Client ─────────────────────────────────────────────────────────────
MSG_JOIN_ACCEPT    = "join_accept"     # {your_player_id, players: [Player.to_dict()], settings: {...}}
MSG_JOIN_REJECT    = "join_reject"     # {reason: str}
MSG_LOBBY_UPDATE   = "lobby_update"    # {players: [Player.to_dict()]}
MSG_PLAYER_KICKED  = "player_kicked"   # {}
MSG_GAME_START     = "game_start"      # {settings: GameSettings.to_dict()}
MSG_ROUND_BEGIN    = "round_begin"     # {round_number, total_rounds, video: {video_id, description, thumbnail_url, author_username, view_count, like_count}}
MSG_ROUND_RESULT   = "round_result"    # {round_number, correct_player_id, correct_display_name, answers: [{player_id, display_name, guessed_player_id, is_correct, points, elapsed_ms}], scores: {player_id: int}}
MSG_GAME_END       = "game_end"        # {leaderboard: [LeaderboardEntry.to_dict()]}
MSG_PONG           = "pong"            # {}


def encode(msg: dict) -> bytes:
    """Encode a message dict to wire format."""
    return (json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8")


def decode(line: bytes) -> dict:
    """Decode a single wire-format line to a dict."""
    return json.loads(line.decode("utf-8").strip())


class MessageReader:
    """Buffers incoming bytes and yields complete messages."""

    def __init__(self) -> None:
        self._buf = b""

    def feed(self, data: bytes) -> list[dict]:
        """Feed raw bytes; returns any complete messages parsed."""
        self._buf += data
        messages: list[dict] = []
        while b"\n" in self._buf:
            line, self._buf = self._buf.split(b"\n", 1)
            line = line.strip()
            if line:
                try:
                    messages.append(decode(line))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass  # discard malformed frames
        return messages
