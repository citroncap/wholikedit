"""Background thread that downloads a TikTok video with yt-dlp."""
from __future__ import annotations
import logging
import subprocess
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal

log = logging.getLogger(__name__)

try:
    import yt_dlp  # noqa: F401
    _YTDLP = True
except ImportError:
    _YTDLP = False

# Prefer VP9/VP8 (handled by Chromium's bundled libvpx, no WMF needed).
# Fall back to H.264 if TikTok doesn't offer WebM streams; the downloader
# will transcode to VP8/WebM in that case.
_FORMAT = (
    "bestvideo[vcodec^=vp9][ext=webm]+bestaudio[ext=webm]"
    "/bestvideo[vcodec^=vp9]+bestaudio"
    "/bestvideo[vcodec^=vp8]+bestaudio"
    "/bestvideo[vcodec^=avc1]+bestaudio[ext=m4a]"
    "/bestvideo[vcodec^=avc1]+bestaudio"
    "/best[ext=webm]"
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

    def __init__(self, url: str, tmp_dir: Path, transcode_webm: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._url            = url
        self._tmp_dir        = tmp_dir
        self._transcode_webm = transcode_webm
        self._stop           = False

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
                log.info("File found despite earlier error — treating as success")
            if self._transcode_webm and not actual_path.endswith(".webm"):
                actual_path = self._transcode(actual_path)
                if not actual_path:
                    return
            self.progress.emit(100)
            self.finished.emit(actual_path)
        else:
            self.error.emit(last_error or "Fichier téléchargé introuvable")

    def _transcode(self, src: str) -> str:
        """Re-encode src to VP9+Opus WebM; returns output path or '' on failure."""
        out = str(self._tmp_dir / "round.webm")
        log.info("Transcoding to VP9/WebM: %s → %s", src, out)
        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-y", "-i", src,
                    "-c:v", "libvpx",          # VP8 — same libvpx, 8× faster than VP9
                    "-deadline", "realtime", "-cpu-used", "16",
                    "-b:v", "1500k",
                    "-c:a", "libvorbis", "-q:a", "5",
                    out,
                ],
                capture_output=True,
                timeout=120,
            )
            if result.returncode == 0 and Path(out).exists():
                log.info("Transcode done: %s", out)
                return out
            log.warning(
                "ffmpeg transcode failed (rc=%d): %s",
                result.returncode,
                result.stderr.decode(errors="replace")[-400:],
            )
            self.error.emit("Transcoding vidéo échoué")
            return ""
        except FileNotFoundError:
            log.warning("ffmpeg introuvable — lecture H.264 requise")
            # Fall back: return original file; WebEngine may not play it but won't crash
            return src
        except subprocess.TimeoutExpired:
            log.warning("ffmpeg transcode timeout")
            self.error.emit("Transcoding vidéo trop long")
            return ""
