"""TikTok data sync and thumbnail caching.

SyncWorker fetches videos from the provider and stores them in the local DB.
It also downloads and caches thumbnail images for offline use.
"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Optional
from PyQt6.QtCore import QThread, pyqtSignal
from models.game import GameVideo
from database.db_manager import DatabaseManager
from tiktok.provider import TikTokProvider
from utils.helpers import utcnow_str
from utils.config import THUMBNAIL_DIR

log = logging.getLogger(__name__)


class SyncWorker(QThread):
    """Fetches videos from TikTok (or mock) and stores them in the DB.

    Signals:
      progress(fetched_count)
      finished(total_count)
      error(message)
    """
    progress = pyqtSignal(int)
    finished = pyqtSignal(int)
    error    = pyqtSignal(str)

    def __init__(
        self,
        provider: TikTokProvider,
        db: DatabaseManager,
        access_token: str,
        max_videos: int = 50,
    ) -> None:
        super().__init__()
        self._provider     = provider
        self._db           = db
        self._token        = access_token
        self._max_videos   = max_videos

    def run(self) -> None:
        try:
            log.info("Starting TikTok video sync (max=%d)", self._max_videos)
            videos = self._provider.get_videos(self._token, self._max_videos)

            now = utcnow_str()
            for i, video in enumerate(videos, 1):
                self._db.upsert_video(video, now)
                self._cache_thumbnail(video)
                self.progress.emit(i)

            log.info("Sync complete: %d videos", len(videos))
            self.finished.emit(len(videos))
        except Exception as exc:
            log.error("Sync error: %s", exc)
            self.error.emit(str(exc))

    def _cache_thumbnail(self, video: GameVideo) -> Optional[Path]:
        """Download thumbnail to THUMBNAIL_DIR and update video.thumbnail_path."""
        if video.thumbnail_path and Path(video.thumbnail_path).exists():
            return Path(video.thumbnail_path)
        if not video.thumbnail_url or video.thumbnail_url.startswith("mock://"):
            return None
        try:
            import requests
            resp = requests.get(video.thumbnail_url, timeout=10)
            resp.raise_for_status()
            ext  = ".jpg"
            dest = THUMBNAIL_DIR / f"{video.video_id}{ext}"
            dest.write_bytes(resp.content)
            video.thumbnail_path = str(dest)
            # Re-upsert with updated path
            self._db.upsert_video(video, utcnow_str())
            return dest
        except Exception as exc:
            log.debug("Thumbnail download skipped for %s: %s", video.video_id, exc)
            return None
