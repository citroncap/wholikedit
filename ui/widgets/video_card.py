"""Video card shown during a game round.

Player priority:
  1. QMediaPlayer + QVideoWidget  (requires WMF on Windows — install Media Feature Pack)
  2. QWebEngineView via localhost HTTP  (fallback if QMediaPlayer errors)
  3. Gradient card + open-in-browser link  (last resort)
"""
from __future__ import annotations
import functools
import http.server
import logging
import socketserver
import threading
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QSizePolicy, QStackedWidget,
)
from PyQt6.QtCore import Qt, QUrl, QTimer
from PyQt6.QtGui import QFont, QColor, QPainter, QLinearGradient, QDesktopServices
from models.game import GameVideo

log = logging.getLogger(__name__)

# ── Local HTTP server (fallback for WebEngine) ────────────────────────────────
_HTTP_PORT: int = 0
_http_server: socketserver.TCPServer | None = None
_http_lock = threading.Lock()


def _ensure_video_server(directory: Path) -> int:
    global _http_server, _HTTP_PORT
    with _http_lock:
        if _http_server is not None:
            return _HTTP_PORT
        try:
            handler = functools.partial(
                http.server.SimpleHTTPRequestHandler,
                directory=str(directory),
            )
            server = socketserver.TCPServer(("127.0.0.1", 0), handler)
            _HTTP_PORT = server.server_address[1]
            t = threading.Thread(target=server.serve_forever, daemon=True)
            t.start()
            _http_server = server
            log.info("Video HTTP server started on 127.0.0.1:%d", _HTTP_PORT)
        except Exception as exc:
            log.warning("Could not start video HTTP server: %s", exc)
    return _HTTP_PORT


# ── Optional dependencies ─────────────────────────────────────────────────────
try:
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PyQt6.QtMultimediaWidgets import QVideoWidget
    _MULTIMEDIA = True
except ImportError as _e:
    log.warning("PyQt6 multimedia not available: %s", _e)
    _MULTIMEDIA = False

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    _WEBENGINE = True
except ImportError as _e:
    log.warning("PyQt6-WebEngine not available: %s", _e)
    _WEBENGINE = False

try:
    import yt_dlp  # noqa: F401
    _YTDLP = True
except ImportError as _e:
    log.warning("yt-dlp not available: %s", _e)
    _YTDLP = False

_GRADIENTS = [
    ("#FE2C55", "#FF6B35"), ("#25F4EE", "#0090FF"), ("#9B59B6", "#FE2C55"),
    ("#2ECC71", "#25F4EE"), ("#F39C12", "#FE2C55"), ("#3498DB", "#9B59B6"),
    ("#E74C3C", "#F39C12"), ("#1ABC9C", "#2ECC71"),
]
_AlignC = Qt.AlignmentFlag.AlignCenter


class VideoCard(QWidget):
    """Downloads and plays a TikTok video locally.

    Pages (QStackedWidget):
      0 – downloading  (progress bar)
      1 – playing      (player widget created at runtime)
      2 – fallback     (gradient card + open-in-browser button)
    """

    def __init__(
        self,
        video: GameVideo,
        color1: str = "#FE2C55",
        color2: str = "#25F4EE",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._video     = video
        self._color1    = color1
        self._color2    = color2
        self._player:   QMediaPlayer | None = None
        self._audio:    QAudioOutput | None = None
        self._dl        = None
        self._tmp_file: str = ""
        self._html_file: str = ""
        self._uses_webengine = False
        self._vid_view  = None          # created lazily in _init_player
        self._player_area_layout: QVBoxLayout | None = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._build()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        log.info("VideoCard init: yt-dlp=%s  multimedia=%s  webengine=%s  url=%s",
                 _YTDLP, _MULTIMEDIA, _WEBENGINE, bool(self._video.video_url))

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget()
        root.addWidget(self._stack)

        self._stack.addWidget(self._make_download_page())   # 0
        self._stack.addWidget(self._make_player_page())     # 1
        self._stack.addWidget(self._make_fallback_page())   # 2

        url = self._video.video_url
        if url and _YTDLP and (_MULTIMEDIA or _WEBENGINE):
            self._start_download(url)
            self._stack.setCurrentIndex(0)
        else:
            self._stack.setCurrentIndex(2)

    def _make_download_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background:#0a0a0a;")
        v = QVBoxLayout(page)
        v.setAlignment(_AlignC)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(10)
        v.addStretch()

        lbl = QLabel("Téléchargement de la vidéo…")
        lbl.setFont(QFont("Segoe UI", 13))
        lbl.setStyleSheet("color:#888;")
        lbl.setAlignment(_AlignC)
        v.addWidget(lbl)

        self._dl_bar = QProgressBar()
        self._dl_bar.setRange(0, 100)
        self._dl_bar.setValue(0)
        self._dl_bar.setTextVisible(False)
        self._dl_bar.setFixedHeight(6)
        self._dl_bar.setStyleSheet(
            "QProgressBar{background:#1a1a1a;border-radius:3px;border:none;}"
            "QProgressBar::chunk{background:#FE2C55;border-radius:3px;}"
        )
        v.addWidget(self._dl_bar)

        self._dl_pct = QLabel("0 %")
        self._dl_pct.setStyleSheet("color:#555;font-size:11px;")
        self._dl_pct.setAlignment(_AlignC)
        v.addWidget(self._dl_pct)

        if self._video.author_username:
            auth = QLabel(f"@{self._video.author_username}")
            auth.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            auth.setStyleSheet("color:#444;margin-top:20px;")
            auth.setAlignment(_AlignC)
            v.addWidget(auth)

        if self._video.short_description:
            desc = QLabel(self._video.short_description)
            desc.setWordWrap(True)
            desc.setStyleSheet("color:#333;font-size:11px;")
            desc.setAlignment(_AlignC)
            v.addWidget(desc)

        v.addStretch()
        return page

    def _make_player_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background:#000;")
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # The actual player widget is added here at play time (_init_player)
        area = QWidget()
        area.setStyleSheet("background:#000;")
        self._player_area_layout = QVBoxLayout(area)
        self._player_area_layout.setContentsMargins(0, 0, 0, 0)
        v.addWidget(area, 1)

        ctrl = QWidget()
        ctrl.setStyleSheet("background:#111;border-top:1px solid #1a1a1a;")
        ctrl.setFixedHeight(32)
        cl = QHBoxLayout(ctrl)
        cl.setContentsMargins(8, 0, 8, 0)
        cl.setSpacing(6)
        cl.addStretch()

        self._open_file_btn = QPushButton("📂")
        self._open_file_btn.setFixedSize(24, 24)
        self._open_file_btn.setToolTip("Ouvrir dans le lecteur système")
        self._open_file_btn.setStyleSheet(
            "QPushButton{background:none;border:none;color:#444;font-size:12px;}"
            "QPushButton:hover{color:#aaa;}"
        )
        self._open_file_btn.setVisible(False)
        self._open_file_btn.clicked.connect(self._open_local_file)
        cl.addWidget(self._open_file_btn)

        url = self._video.video_url
        if url:
            ob = QPushButton("↗")
            ob.setFixedSize(24, 24)
            ob.setToolTip("Ouvrir sur TikTok")
            ob.setStyleSheet(
                "QPushButton{background:none;border:none;color:#444;font-size:12px;}"
                "QPushButton:hover{color:#aaa;}"
            )
            ob.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url)))
            cl.addWidget(ob)

        v.addWidget(ctrl)
        return page

    def _make_fallback_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        preview = _GradientPreview(self._video, self._color1, self._color2)
        preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        v.addWidget(preview, 1)

        url = self._video.video_url
        if url:
            btn = QPushButton("↗  Ouvrir sur TikTok")
            btn.setFixedHeight(32)
            btn.setStyleSheet(
                "QPushButton{background:#111;color:#aaa;border:none;font-size:11px;"
                "border-top:1px solid #222;}"
                "QPushButton:hover{color:#fff;background:#1a1a1a;}"
            )
            btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url)))
            v.addWidget(btn)

        if not _YTDLP:
            lbl = QLabel("Installe yt-dlp pour voir les vidéos :\npip install yt-dlp")
            lbl.setAlignment(_AlignC)
            lbl.setStyleSheet(
                "color:#FE2C55;font-size:10px;padding:4px 6px;"
                "background:#1a0000;border-top:1px solid #330000;"
            )
            lbl.setWordWrap(True)
            v.addWidget(lbl)

        return page

    # ── Download ──────────────────────────────────────────────────────────────

    def _start_download(self, url: str) -> None:
        from utils.video_downloader import VideoDownloader
        from utils.config import DATA_DIR
        tmp = DATA_DIR / "video_tmp"
        tmp.mkdir(exist_ok=True)

        self._dl = VideoDownloader(url, tmp, parent=self)
        self._dl.progress.connect(self._on_progress)
        self._dl.finished.connect(self._on_finished)
        self._dl.error.connect(self._on_error)
        self._dl.start()

    def _on_progress(self, pct: int) -> None:
        self._dl_bar.setValue(pct)
        self._dl_pct.setText(f"{pct} %")

    def _open_local_file(self) -> None:
        if self._tmp_file and Path(self._tmp_file).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._tmp_file))

    def _on_finished(self, filepath: str) -> None:
        self._tmp_file = filepath
        sz = Path(filepath).stat().st_size if Path(filepath).exists() else 0
        log.info("Download complete: %s  (%.1f MB)", filepath, sz / 1e6)
        self._open_file_btn.setVisible(True)
        self._stack.setCurrentIndex(1)
        QTimer.singleShot(80, lambda: self._init_player(filepath))

    def _on_error(self, msg: str) -> None:
        log.warning("Video download error: %s", msg)
        self._stack.setCurrentIndex(2)

    # ── Player ────────────────────────────────────────────────────────────────

    def _init_player(self, filepath: str) -> None:
        log.info("Player loading: %s  (multimedia=%s webengine=%s)",
                 filepath, _MULTIMEDIA, _WEBENGINE)
        if _MULTIMEDIA:
            self._init_mediaplayer(filepath)
        elif _WEBENGINE:
            self._init_webengine_player(filepath)
        else:
            log.error("No player backend available")
            self._stack.setCurrentIndex(2)

    def _init_mediaplayer(self, filepath: str) -> None:
        """Primary player: QMediaPlayer + QVideoWidget."""
        self._vid_view = QVideoWidget()
        self._vid_view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._player_area_layout.addWidget(self._vid_view)

        self._audio = QAudioOutput()
        self._audio.setVolume(0.8)
        self._player = QMediaPlayer()
        self._player.setAudioOutput(self._audio)
        self._player.setVideoOutput(self._vid_view)
        self._player.mediaStatusChanged.connect(self._on_media_status)
        self._player.errorOccurred.connect(
            lambda err, msg: self._on_mediaplayer_error(err, msg, filepath)
        )
        self._player.setSource(QUrl.fromLocalFile(filepath))
        log.info("QMediaPlayer source set")

    def _on_mediaplayer_error(self, err, msg: str, filepath: str) -> None:
        log.error("QMediaPlayer error %s: %s", err, msg)
        if _WEBENGINE:
            log.info("Falling back to WebEngine")
            # Clean up failed QMediaPlayer
            if self._player:
                self._player.stop()
                self._player.setSource(QUrl())
                self._player = None
            self._audio = None
            if self._vid_view is not None:
                self._player_area_layout.removeWidget(self._vid_view)
                self._vid_view.deleteLater()
                self._vid_view = None
            self._init_webengine_player(filepath)

    def _init_webengine_player(self, filepath: str) -> None:
        """Fallback player: QWebEngineView via localhost HTTP."""
        self._uses_webengine = True
        self._vid_view = QWebEngineView()
        self._vid_view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._player_area_layout.addWidget(self._vid_view)

        try:
            from PyQt6.QtWebEngineCore import QWebEngineSettings
            self._vid_view.settings().setAttribute(
                QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False
            )
        except Exception:
            pass

        tmp_dir    = Path(filepath).parent
        port       = _ensure_video_server(tmp_dir)
        video_name = Path(filepath).name

        html = (
            "<!DOCTYPE html><html><head>"
            "<style>*{margin:0;padding:0;box-sizing:border-box}"
            "html,body{width:100%;height:100%;background:#000;overflow:hidden}"
            "video{width:100%;height:100%;object-fit:contain}"
            "</style></head><body>"
            f"<video id='v' src='{video_name}' autoplay loop playsinline controls></video>"
            "<script>document.getElementById('v').play().catch(()=>{})</script>"
            "</body></html>"
        )
        html_path = tmp_dir / "player.html"
        html_path.write_text(html, encoding="utf-8")
        self._html_file = str(html_path)

        url = QUrl(f"http://127.0.0.1:{port}/player.html")
        log.info("WebEngine loading: %s", url.toString())
        self._vid_view.loadFinished.connect(
            lambda ok: log.info("WebEngine loadFinished ok=%s", ok)
        )
        self._vid_view.load(url)

    def _on_media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if not self._player:
            return
        log.info("QMediaPlayer status → %s", status)
        if status == QMediaPlayer.MediaStatus.LoadedMedia:
            self._player.play()
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._player.setPosition(0)
            self._player.play()

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def cleanup(self) -> None:
        """Stop player and delete temp video. Must be called before deleteLater()."""
        if self._dl and self._dl.isRunning():
            self._dl.cancel()
            try:
                self._dl.progress.disconnect()
                self._dl.finished.disconnect()
                self._dl.error.disconnect()
            except Exception:
                pass

        if self._uses_webengine and self._vid_view is not None:
            try:
                self._vid_view.load(QUrl("about:blank"))
            except Exception:
                pass

        if self._player:
            self._player.stop()
            self._player.setSource(QUrl())
            self._player = None

        for attr in ("_tmp_file", "_html_file"):
            path = getattr(self, attr, "")
            if path:
                try:
                    Path(path).unlink(missing_ok=True)
                except OSError:
                    pass
                setattr(self, attr, "")


# ── Gradient fallback card ────────────────────────────────────────────────────

class _GradientPreview(QWidget):
    def __init__(self, video: GameVideo, c1: str, c2: str, parent=None) -> None:
        super().__init__(parent)
        self._video = video
        self._c1 = c1
        self._c2 = c2
        self.setMinimumSize(220, 300)
        self._build_content()

    def _build_content(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)

        tk = QLabel("TikTok")
        tk.setFont(QFont("Segoe UI", 18, QFont.Weight.ExtraBold))
        tk.setStyleSheet("color:rgba(255,255,255,0.95); background:transparent;")
        layout.addWidget(tk)
        layout.addStretch()

        play = QLabel("▶")
        play.setFont(QFont("Segoe UI", 56))
        play.setStyleSheet("color:rgba(255,255,255,0.75); background:transparent;")
        play.setAlignment(_AlignC)
        layout.addWidget(play)
        layout.addStretch()

        if self._video.author_username:
            author = QLabel(f"@{self._video.author_username}")
            author.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
            author.setStyleSheet("color:rgba(255,255,255,0.9); background:transparent;")
            author.setAlignment(_AlignC)
            layout.addWidget(author)

        if self._video.short_description:
            desc = QLabel(self._video.short_description)
            desc.setWordWrap(True)
            desc.setFont(QFont("Segoe UI", 11))
            desc.setStyleSheet("color:rgba(255,255,255,0.7); background:transparent;")
            desc.setAlignment(_AlignC)
            layout.addWidget(desc)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        grad = QLinearGradient(0, 0, rect.width(), rect.height())
        grad.setColorAt(0, QColor(self._c1))
        grad.setColorAt(1, QColor(self._c2))
        painter.setBrush(grad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, 16, 16)
        painter.end()
        super().paintEvent(event)
