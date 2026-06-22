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

# Prefer H.264 (avc1) for maximum WebEngine / QMediaPlayer compatibility.
_FORMAT = (
    "bestvideo[vcodec^=avc1]+bestaudio[ext=m4a]"
    "/bestvideo[vcodec^=avc1]+bestaudio"
    "/best[vcodec^=avc1][ext=mp4]"
    "/best[ext=mp4]"
    "/best"
)

# Browsers to try for cookie extraction when TikTok requires login.
_BROWSERS = ("chrome", "edge", "firefox", "chromium", "brave")

# Keywords that indicate auth is needed (not a permanent failure).
# "IP blocked" is NOT included — that means video unavailable, cookies won't help.
_AUTH_KEYWORDS = ("log in", "login", "comfortable", "authentication", "cookie")


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

        base_opts = {
            "format":         _FORMAT,
            "outtmpl":        str(self._tmp_dir / "round.%(ext)s"),
            "quiet":          True,
            "no_warnings":    True,
            "progress_hooks": [hook],
            "noplaylist":     True,
        }

        # First attempt without cookies. If TikTok requires login (age-restricted
        # content), retry with cookies from each installed browser.
        attempts: list[dict] = [{}]
        attempts += [{"cookiesfrombrowser": (b,)} for b in _BROWSERS]

        last_error = ""
        for extra in attempts:
            if self._stop:
                return
            actual_path = ""
            opts = {**base_opts, **extra}
            browser = extra.get("cookiesfrombrowser", ("",))[0] or "no-cookies"
            try:
                import yt_dlp as _ydlp
                with _ydlp.YoutubeDL(opts) as ydl:
                    ydl.download([self._url])
                log.info("Download succeeded (cookies: %s)", browser)
                break
            except InterruptedError:
                return
            except Exception as exc:
                last_error = str(exc)
                log.warning("Download failed (cookies: %s): %s", browser, exc)
                lower = last_error.lower()
                if not any(kw in lower for kw in _AUTH_KEYWORDS):
                    break  # permanent failure (video gone, IP blocked, etc.)

        if self._stop:
            return

        if not actual_path or not Path(actual_path).exists():
            files = list(self._tmp_dir.glob("round.*"))
            actual_path = str(files[0]) if files else ""

        if actual_path and Path(actual_path).exists():
            if last_error:
                # yt-dlp rename error when ffmpeg merged directly to final filename
                log.info("File found despite earlier error — treating as success")
            self.progress.emit(100)
            self.finished.emit(actual_path)
        else:
            self.error.emit(last_error or "Fichier téléchargé introuvable")
