"""Background thread that downloads a TikTok video with yt-dlp."""
from __future__ import annotations
import logging
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal

log = logging.getLogger(__name__)

try:
    import yt_dlp  # noqa: F401
    _YTDLP = True
except ImportError:
    _YTDLP = False


class VideoDownloader(QThread):
    """Downloads a single video URL to a temp directory.

    Signals are Qt-queued and safe to connect from the main thread.
    """

    progress = pyqtSignal(int)   # 0–100 %
    finished = pyqtSignal(str)   # absolute path of downloaded file
    error    = pyqtSignal(str)   # human-readable error message

    def __init__(self, url: str, tmp_dir: Path, parent=None) -> None:
        super().__init__(parent)
        self._url     = url
        self._tmp_dir = tmp_dir
        self._stop    = False

    def cancel(self) -> None:
        self._stop = True

    def run(self) -> None:
        if not _YTDLP:
            self.error.emit("yt-dlp non installé — lance : pip install yt-dlp")
            return

        # Clean up any leftover file from a previous round
        for old in self._tmp_dir.glob("round.*"):
            try:
                old.unlink()
            except OSError:
                pass

        actual_path: str = ""

        def hook(d: dict) -> None:
            if self._stop:
                raise InterruptedError("cancelled")
            status = d.get("status", "")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                done  = d.get("downloaded_bytes", 0)
                if total:
                    self.progress.emit(min(99, int(done * 100 / total)))
            elif status == "finished":
                nonlocal actual_path
                actual_path = d.get("filename", "")
                self.progress.emit(99)

        opts = {
            "format":         "best[ext=mp4]/best",
            "outtmpl":        str(self._tmp_dir / "round.%(ext)s"),
            "quiet":          True,
            "no_warnings":    True,
            "progress_hooks": [hook],
            "noplaylist":     True,
        }

        try:
            import yt_dlp as _ydlp
            with _ydlp.YoutubeDL(opts) as ydl:
                ydl.download([self._url])
        except InterruptedError:
            return
        except Exception as exc:
            log.error("yt-dlp download error: %s", exc)
            if not self._stop:
                self.error.emit(str(exc))
            return

        if self._stop:
            return

        # Resolve the actual path (yt-dlp adds the extension)
        if not actual_path or not Path(actual_path).exists():
            files = list(self._tmp_dir.glob("round.*"))
            actual_path = str(files[0]) if files else ""

        if actual_path and Path(actual_path).exists():
            self.progress.emit(100)
            self.finished.emit(actual_path)
        else:
            self.error.emit("Fichier téléchargé introuvable")
