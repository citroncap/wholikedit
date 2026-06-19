"""Application-wide configuration and persistent settings."""
from __future__ import annotations
import os
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# Increment this whenever a migration is needed in Settings.load().
SETTINGS_VERSION = 2

APP_NAME    = "WhoLikedIt"
APP_VERSION = "2.0.0"

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR        = Path(__file__).resolve().parent.parent
DATA_DIR        = Path(os.getenv("APPDATA", BASE_DIR)) / APP_NAME
DB_PATH             = DATA_DIR / "game.db"
PLAYER_PATH         = DATA_DIR / "player.json"
SETTINGS_PATH       = DATA_DIR / "settings.json"
LIKED_VIDEOS_PATH   = DATA_DIR / "liked_videos.json"
THUMBNAIL_DIR       = DATA_DIR / "thumbnails"

for _d in (DATA_DIR, THUMBNAIL_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── Network ───────────────────────────────────────────────────────────────────
DISCOVERY_PORT     = 45000          # UDP broadcast port for room discovery
TCP_PORT_RANGE     = (45100, 45200) # Host picks a free port from this range
DISCOVERY_INTERVAL = 2.5            # seconds between host UDP announcements
DISCOVERY_TIMEOUT  = 6.0            # seconds client waits for a response
MAX_PLAYERS        = 8

# ── Relay server ──────────────────────────────────────────────────────────────
# Set RELAY_URL to your deployed relay (relay_server.py on Render.com).
# Use "wss://" for Render HTTPS services, "ws://" for plain HTTP/local.
# Leave empty to disable relay (friends join via IP:PORT instead).
RELAY_URL = "wss://wholikedit.onrender.com"

# ── Game defaults ─────────────────────────────────────────────────────────────
DEFAULT_ROUNDS       = 10
DEFAULT_TIMER_SEC    = 15
DEFAULT_VIDEO_COUNT  = 20
SCORE_BASE           = 1000

# ── TikTok OAuth ──────────────────────────────────────────────────────────────
TIKTOK_CLIENT_KEY    = "your_client_key_here"
TIKTOK_CLIENT_SECRET = "your_client_secret_here"
TIKTOK_REDIRECT_URI  = "http://127.0.0.1:8765/callback"
TIKTOK_OAUTH_SCOPE   = "user.info.basic,video.list"
TIKTOK_AUTH_URL      = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_TOKEN_URL     = "https://open.tiktokapis.com/v2/oauth/token/"
OAUTH_CALLBACK_PORT  = 8765

# ── UI ────────────────────────────────────────────────────────────────────────
WINDOW_MIN_W = 1100
WINDOW_MIN_H = 720

AVATAR_COLORS = [
    "#FE2C55", "#25F4EE", "#F39C12", "#2ECC71",
    "#9B59B6", "#E74C3C", "#3498DB", "#1ABC9C",
]


class Settings:
    _defaults: dict = {
        "settings_version": 1,          # written by older versions without this key
        "round_timer":      DEFAULT_TIMER_SEC,
        "rounds_per_game":  DEFAULT_ROUNDS,
        "video_count":      DEFAULT_VIDEO_COUNT,
        # Credentials stored here take precedence over the constants above.
        # Empty string = use the hardcoded placeholder (i.e. not configured).
        "tiktok_client_key":    "",
        "tiktok_client_secret": "",
        # Demo / developer mode flag.  MUST default to False so production
        # users are never silently put into a fake-account flow.
        "use_mock_tiktok":  False,
        "window_x":         None,
        "window_y":         None,
        "window_w":         WINDOW_MIN_W,
        "window_h":         WINDOW_MIN_H,
    }

    def __init__(self) -> None:
        self._data: dict = {}
        self.load()

    def load(self) -> None:
        if SETTINGS_PATH.exists():
            try:
                self._data = json.loads(SETTINGS_PATH.read_text("utf-8"))
            except (json.JSONDecodeError, OSError):
                log.warning("settings.json is corrupt; starting with defaults")
                self._data = {}

        # ── Migration ─────────────────────────────────────────────────────────
        # v1 shipped with use_mock_tiktok=True as the default, which caused
        # every user to be put in the fake-login flow.  Any settings file
        # that lacks a version number was written by v1 and needs this reset.
        stored_version = self._data.get("settings_version", 1)
        if stored_version < 2:
            if self._data.get("use_mock_tiktok", False):
                log.info(
                    "Settings migration v1→v2: resetting use_mock_tiktok "
                    "from True to False (old default was wrong)"
                )
            self._data["use_mock_tiktok"] = False
            self._data["settings_version"] = SETTINGS_VERSION
            # Persist the migration immediately so it never runs again
            self._write()

        # Fill in any keys added in newer versions
        for k, v in self._defaults.items():
            self._data.setdefault(k, v)

    def save(self) -> None:
        self._data["settings_version"] = SETTINGS_VERSION
        self._write()

    def _write(self) -> None:
        try:
            SETTINGS_PATH.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        except OSError as exc:
            log.error("Could not write settings.json: %s", exc)

    def get(self, key: str, default=None):
        return self._data.get(key, self._defaults.get(key, default))

    def set(self, key: str, value) -> None:
        self._data[key] = value
        self.save()

    # ── TikTok credential helpers ─────────────────────────────────────────────

    def get_tiktok_client_key(self) -> str:
        """Return the user-configured client key, or '' if not set."""
        return self._data.get("tiktok_client_key", "").strip()

    def get_tiktok_client_secret(self) -> str:
        """Return the user-configured client secret, or '' if not set."""
        return self._data.get("tiktok_client_secret", "").strip()

    def set_tiktok_credentials(self, key: str, secret: str) -> None:
        self._data["tiktok_client_key"]    = key.strip()
        self._data["tiktok_client_secret"] = secret.strip()
        self.save()

    def has_tiktok_credentials(self) -> bool:
        """True when real (non-placeholder) credentials have been configured."""
        key = self.get_tiktok_client_key()
        return bool(key and key != TIKTOK_CLIENT_KEY)

    def __getitem__(self, key: str):
        return self.get(key)

    def __setitem__(self, key: str, value) -> None:
        self.set(key, value)
