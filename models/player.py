"""Player model – no accounts, just a session identity."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Player:
    player_id: str           # UUID, generated each session
    display_name: str
    avatar_color: str        # hex, e.g. "#FE2C55"
    is_host: bool = False
    is_ready: bool = False
    tiktok_connected: bool = False
    tiktok_username: Optional[str] = None
    video_count: int = 0     # liked/posted videos synced for this game

    @property
    def initials(self) -> str:
        parts = self.display_name.split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return self.display_name[:2].upper()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Player":
        return cls(
            player_id=d["player_id"],
            display_name=d["display_name"],
            avatar_color=d["avatar_color"],
            is_host=d.get("is_host", False),
            is_ready=d.get("is_ready", False),
            tiktok_connected=d.get("tiktok_connected", False),
            tiktok_username=d.get("tiktok_username"),
            video_count=d.get("video_count", 0),
        )
