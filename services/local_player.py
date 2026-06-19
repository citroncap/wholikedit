"""Manages the local player's identity and TikTok token.
Stored in APPDATA/WhoLikedIt/player.json – no passwords.
"""
from __future__ import annotations
import json
import logging
from typing import Optional
from utils.config import PLAYER_PATH, AVATAR_COLORS
from utils.security import encrypt_token, decrypt_token, generate_player_id

log = logging.getLogger(__name__)


class LocalPlayer:
    """Represents the local player. Loaded/saved from player.json."""

    def __init__(self) -> None:
        self.player_id: str = generate_player_id()
        self.display_name: str = ""
        self.avatar_color: str = AVATAR_COLORS[0]
        self._tiktok_token_encrypted: Optional[str] = None
        self._tiktok_refresh_encrypted: Optional[str] = None
        self.tiktok_username: Optional[str] = None
        self.tiktok_open_id: Optional[str] = None
        self._loaded = False

    # ── Persistence ───────────────────────────────────────────────────────────

    def load(self) -> bool:
        """Load from disk. Returns True if profile exists."""
        if not PLAYER_PATH.exists():
            return False
        try:
            data = json.loads(PLAYER_PATH.read_text("utf-8"))
            # Restore the stable player_id if present; otherwise keep the one
            # generated in __init__ and it will be saved on next save().
            if data.get("player_id"):
                self.player_id = data["player_id"]
            self.display_name               = data.get("display_name", "")
            self.avatar_color               = data.get("avatar_color", AVATAR_COLORS[0])
            self._tiktok_token_encrypted    = data.get("tiktok_token")
            self._tiktok_refresh_encrypted  = data.get("tiktok_refresh")
            self.tiktok_username            = data.get("tiktok_username")
            self.tiktok_open_id             = data.get("tiktok_open_id")
            self._loaded = bool(self.display_name)
            return self._loaded
        except (json.JSONDecodeError, OSError, KeyError) as exc:
            log.warning("Failed to load player profile: %s", exc)
            return False

    def save(self) -> None:
        data = {
            "player_id":        self.player_id,
            "display_name":     self.display_name,
            "avatar_color":     self.avatar_color,
            "tiktok_token":     self._tiktok_token_encrypted,
            "tiktok_refresh":   self._tiktok_refresh_encrypted,
            "tiktok_username":  self.tiktok_username,
            "tiktok_open_id":   self.tiktok_open_id,
        }
        PLAYER_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ── TikTok token management ────────────────────────────────────────────────

    @property
    def has_tiktok(self) -> bool:
        return bool(self._tiktok_token_encrypted and self.tiktok_username)

    def store_tokens(
        self,
        access_token: str,
        refresh_token: Optional[str],
        username: str,
        open_id: str,
    ) -> None:
        self._tiktok_token_encrypted   = encrypt_token(access_token)
        self._tiktok_refresh_encrypted = encrypt_token(refresh_token) if refresh_token else None
        self.tiktok_username           = username
        self.tiktok_open_id            = open_id
        self.save()

    def get_access_token(self) -> Optional[str]:
        if not self._tiktok_token_encrypted:
            return None
        try:
            return decrypt_token(self._tiktok_token_encrypted)
        except Exception:
            return None

    def get_refresh_token(self) -> Optional[str]:
        if not self._tiktok_refresh_encrypted:
            return None
        try:
            return decrypt_token(self._tiktok_refresh_encrypted)
        except Exception:
            return None

    def disconnect_tiktok(self) -> None:
        self._tiktok_token_encrypted   = None
        self._tiktok_refresh_encrypted = None
        self.tiktok_username           = None
        self.tiktok_open_id            = None
        self.save()

    # ── Setup ────────────────────────────────────────────────────────────────

    @property
    def is_setup(self) -> bool:
        return bool(self.display_name)

    def setup(self, display_name: str) -> None:
        self.display_name = display_name.strip()
        from utils.helpers import avatar_color_for
        self.avatar_color = avatar_color_for(display_name)
        self.save()
