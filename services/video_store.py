"""Stores the local player's imported liked videos in liked_videos.json."""
from __future__ import annotations
import json
import logging
from utils.config import LIKED_VIDEOS_PATH

log = logging.getLogger(__name__)


class VideoStore:
    """Persists the list of liked videos imported from TikTok."""

    def __init__(self) -> None:
        self._videos: list[dict] = []
        self._load()

    def _load(self) -> None:
        if not LIKED_VIDEOS_PATH.exists():
            return
        try:
            data = json.loads(LIKED_VIDEOS_PATH.read_text("utf-8"))
            self._videos = data.get("videos", [])
            log.info("Loaded %d liked videos from disk", len(self._videos))
        except (json.JSONDecodeError, OSError) as exc:
            log.error("Failed to load liked_videos.json: %s", exc)

    def _save(self) -> None:
        try:
            LIKED_VIDEOS_PATH.write_text(
                json.dumps({"version": 1, "videos": self._videos}, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            log.error("Failed to save liked_videos.json: %s", exc)

    def set_videos(self, videos: list[dict]) -> None:
        self._videos = list(videos)
        self._save()
        log.info("Stored %d liked videos", len(self._videos))

    def get_videos(self) -> list[dict]:
        return list(self._videos)

    def count(self) -> int:
        return len(self._videos)

    def clear(self) -> None:
        self._videos = []
        self._save()
        log.info("Liked videos cleared")
