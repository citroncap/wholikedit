"""Leaderboard models."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LeaderboardEntry:
    player_id: str
    display_name: str
    avatar_color: str
    total_points: int
    correct_answers: int
    total_rounds: int
    avg_elapsed_ms: float

    @property
    def accuracy(self) -> float:
        return self.correct_answers / self.total_rounds if self.total_rounds else 0.0

    @property
    def accuracy_pct(self) -> str:
        return f"{self.accuracy * 100:.0f}%"

    def to_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "LeaderboardEntry":
        return cls(**d)


@dataclass
class Leaderboard:
    entries: list[LeaderboardEntry] = field(default_factory=list)

    def sort(self) -> None:
        self.entries.sort(key=lambda e: (-e.total_points, e.avg_elapsed_ms))

    def winner(self) -> Optional[LeaderboardEntry]:
        return self.entries[0] if self.entries else None

    def rank_of(self, player_id: str) -> int:
        for i, e in enumerate(self.entries):
            if e.player_id == player_id:
                return i + 1
        return -1
