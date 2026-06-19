"""Game state and round models."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class GameStatus(str, Enum):
    WAITING    = "waiting"
    IN_PROGRESS = "in_progress"
    FINISHED   = "finished"


@dataclass
class GameVideo:
    """A video that appears in a game round."""
    video_id: str
    description: str
    thumbnail_url: str
    thumbnail_path: Optional[str]
    author_username: str
    view_count: int
    like_count: int
    owner_player_id: str    # the player who "liked"/posted this
    video_url: str = ""     # direct TikTok link for the Watch button

    @property
    def short_description(self) -> str:
        return self.description[:80] + "…" if len(self.description) > 80 else self.description

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "GameVideo":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__})


@dataclass
class PlayerAnswer:
    player_id: str
    guessed_player_id: str
    elapsed_ms: int
    is_correct: bool
    points_earned: int


@dataclass
class RoundResult:
    round_number: int
    video: GameVideo
    correct_player_id: str
    correct_display_name: str
    answers: list[PlayerAnswer] = field(default_factory=list)


@dataclass
class GameSettings:
    total_rounds: int
    timer_seconds: int
    video_count: int

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "GameSettings":
        return cls(**d)
