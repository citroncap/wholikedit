"""Video card shown during a game round.

Downloads the video as VP8/WebM (works on Windows N/KN without WMF),
then plays it from a local file:// URL in QtWebEngine.
Falls back to a gradient preview if download fails or WebEngine is unavailable.
"""
from __future__ import annotations
import logging
import os
import time
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QProgressBar, QSizePolicy, QStackedWidget,
)
from PyQt6.QtCore import Qt, QUrl, QTimer
from PyQt6.QtGui import QFont, QColor, QPainter, QLinearGradient, QDesktopServices
from models.game import GameVideo

log = logging.getLogger(__name__)

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    _WEBENGINE = True
except ImportError as _e:
    log.warning("PyQt6-WebEngine not available: %s", _e)
    _WEBENGINE = False

try:
    import yt_dlp  # noqa: F401
    _YTDLP = True
except ImportError:
    _YTDLP = False

_GRADIENTS = [
    ("#FE2C55", "#FF6B35"), ("#25F4EE", "#0090FF"), ("#9B59B6", "#FE2C55"),
    ("#2ECC71", "#25F4EE"), ("#F39C12", "#FE2C55"), ("#3498DB", "#9B59B6"),
    ("#E74C3C", "#F39C12"), ("#1ABC9C", "#2ECC71"),
]
_AlignC = Qt.AlignmentFlag.AlignCenter


class VideoCard(QWidget):
    """Downloads and plays a TikTok video locally via VP8/WebM + file:// URL.

    Stack pages:
      0 – downloading  (gradient preview + progress bar)
      1 – playing      (QWebEngineView loading a local HTML file)
      2 – fallback     (gradient preview + "Open on TikTok" button)
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
        self._dl        = None
        self._tmp_file  = ""
        self._html_file = ""
        self._view: "QWebEngineView | None" = None
        self._player_area: QVBoxLayout | None = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._build()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget()
        root.addWidget(self._stack)

        self._stack.addWidget(self._make_download_page()) # 0
        self._stack.addWidget(self._make_player_page())   # 1
        self._stack.addWidget(self._make_fallback_page()) # 2

        url = self._video.video_url
        if url and _YTDLP and _WEBENGINE:
            self._start_download(url)
            self._stack.setCurrentIndex(0)
        else:
            log.info("VideoCard fallback: yt-dlp=%s webengine=%s url=%s",
                     _YTDLP, _WEBENGINE, bool(url))
            self._stack.setCurrentIndex(2)

    def _make_download_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        preview = _GradientPreview(self._video, self._color1, self._color2)
        preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._dl_bar = QProgressBar()
        self._dl_bar.setRange(0, 100)
        self._dl_bar.setValue(0)
        self._dl_bar.setTextVisible(False)
        self._dl_bar.setFixedHeight(6)
        self._dl_bar.setStyleSheet(
            "QProgressBar{background:rgba(0,0,0,0.4);border-radius:3px;border:none;}"
            "QProgressBar::chunk{background:#FE2C55;border-radius:3px;}"
        )
        self._dl_pct = QLabel("Chargement…")
        self._dl_pct.setStyleSheet("color:rgba(255,255,255,0.55);font-size:11px;")
        self._dl_pct.setAlignment(_AlignC)

        preview.add_extra(self._dl_bar)
        preview.add_extra(self._dl_pct)

        layout.addWidget(preview)
        return page

    def _make_player_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background:#000;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        area = QWidget()
        area.setStyleSheet("background:#000;")
        self._player_area = QVBoxLayout(area)
        self._player_area.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(area, 1)
        layout.addWidget(self._make_ctrl_bar())
        return page

    def _make_fallback_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        preview = _GradientPreview(self._video, self._color1, self._color2)
        preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(preview, 1)

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
            layout.addWidget(btn)

        return page

    def _make_ctrl_bar(self) -> QWidget:
        ctrl = QWidget()
        ctrl.setStyleSheet("background:#111;border-top:1px solid #1a1a1a;")
        ctrl.setFixedHeight(32)
        cl = QHBoxLayout(ctrl)
        cl.setContentsMargins(8, 0, 8, 0)
        cl.addStretch()
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
        return ctrl

    # ── Download ──────────────────────────────────────────────────────────────

    def _start_download(self, url: str) -> None:
        from utils.video_downloader import VideoDownloader
        from utils.config import DATA_DIR
        # Per-PID temp dir so two instances on the same machine don't clobber each other
        tmp = DATA_DIR / "video_tmp" / str(os.getpid())
        tmp.mkdir(parents=True, exist_ok=True)

        self._dl = VideoDownloader(url, tmp, transcode_webm=True, parent=self)
        self._dl.progress.connect(self._on_progress)
        self._dl.finished.connect(self._on_finished)
        self._dl.error.connect(self._on_error)
        self._dl.start()

    def _on_progress(self, pct: int) -> None:
        self._dl_bar.setValue(pct)
        self._dl_pct.setText(f"{pct} %")

    def _on_finished(self, filepath: str) -> None:
        self._tmp_file = filepath
        sz = Path(filepath).stat().st_size if Path(filepath).exists() else 0
        log.info("Download complete: %s  (%.1f MB)", filepath, sz / 1e6)

        # Transcoding to WebM might have failed (ffmpeg not installed) and the
        # downloader returned the original H.264 file. That won't play on
        # Windows N/KN without WMF — show the fallback card instead.
        if not filepath.endswith(".webm"):
            log.warning("Non-WebM file after transcode step (%s) — showing fallback", filepath)
            self._stack.setCurrentIndex(2)
            return

        # Write a canvas-based HTML player next to the video and load via file://.
        # Using <canvas> + drawImage() instead of a bare <video> element works around
        # the GPU compositing bug on Windows where the video track is silent-black
        # (audio plays but frames never appear in the WebEngine widget).
        ts = int(time.time() * 1000)
        video_name = Path(filepath).name
        html = f"""<!DOCTYPE html>
<html><head><style>
*{{margin:0;padding:0}}
html,body{{width:100%;height:100%;background:#000;overflow:hidden}}
canvas{{display:block;width:100%;height:100%}}
</style></head><body>
<canvas id="c"></canvas>
<video id="v" src="{video_name}" autoplay loop playsinline style="display:none"></video>
<script>
(function(){{
    var v=document.getElementById('v');
    var c=document.getElementById('c');
    var ctx=c.getContext('2d');
    function frame(){{
        if(v.videoWidth>0){{
            var vw=v.videoWidth,vh=v.videoHeight;
            var cw=c.offsetWidth,ch=c.offsetHeight;
            if(c.width!==cw)c.width=cw;
            if(c.height!==ch)c.height=ch;
            var s=Math.min(cw/vw,ch/vh);
            var x=(cw-vw*s)/2,y=(ch-vh*s)/2;
            ctx.fillStyle='#000';ctx.fillRect(0,0,cw,ch);
            ctx.drawImage(v,x,y,vw*s,vh*s);
        }}
        requestAnimationFrame(frame);
    }}
    v.play().catch(function(){{}});
    frame();
}})();
</script>
</body></html>"""
        html_path = Path(filepath).parent / f"player_{ts}.html"
        html_path.write_text(html, encoding="utf-8")
        self._html_file = str(html_path)

        self._stack.setCurrentIndex(1)
        QTimer.singleShot(80, lambda: self._load_local_player(self._html_file))

    def _on_error(self, msg: str) -> None:
        log.warning("Video download error: %s", msg)
        self._stack.setCurrentIndex(2)

    # ── Local player ──────────────────────────────────────────────────────────

    def _load_local_player(self, html_path: str) -> None:
        if not _WEBENGINE or not Path(html_path).exists():
            self._stack.setCurrentIndex(2)
            return

        self._view = QWebEngineView()
        self._view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        try:
            from PyQt6.QtWebEngineCore import QWebEngineSettings
            self._view.settings().setAttribute(
                QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False
            )
        except Exception as exc:
            log.warning("WebEngine settings: %s", exc)

        if self._player_area:
            self._player_area.addWidget(self._view)

        url = QUrl.fromLocalFile(html_path)
        log.info("Loading local player: %s", url.toString())
        self._view.load(url)

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def cleanup(self) -> None:
        """Stop download/playback and delete temp files. Call before deleteLater()."""
        if self._dl and self._dl.isRunning():
            self._dl.cancel()
            try:
                self._dl.progress.disconnect()
                self._dl.finished.disconnect()
                self._dl.error.disconnect()
            except Exception:
                pass

        if self._view:
            try:
                self._view.load(QUrl("about:blank"))
            except Exception:
                pass

        for path in (self._tmp_file, self._html_file):
            if path:
                try:
                    Path(path).unlink(missing_ok=True)
                except OSError:
                    pass
        self._tmp_file = ""
        self._html_file = ""


# ── Gradient preview card ─────────────────────────────────────────────────────

class _GradientPreview(QWidget):
    def __init__(self, video: GameVideo, c1: str, c2: str, parent=None) -> None:
        super().__init__(parent)
        self._video = video
        self._c1 = c1
        self._c2 = c2
        self.setMinimumSize(220, 300)
        self._inner = QVBoxLayout(self)
        self._inner.setContentsMargins(20, 20, 20, 20)
        self._inner.setSpacing(8)
        self._build()

    def _build(self) -> None:
        tk = QLabel("TikTok")
        tk.setFont(QFont("Segoe UI", 18, QFont.Weight.ExtraBold))
        tk.setStyleSheet("color:rgba(255,255,255,0.95);background:transparent;")
        self._inner.addWidget(tk)
        self._inner.addStretch()

        play = QLabel("▶")
        play.setFont(QFont("Segoe UI", 56))
        play.setStyleSheet("color:rgba(255,255,255,0.75);background:transparent;")
        play.setAlignment(_AlignC)
        self._inner.addWidget(play)
        self._inner.addStretch()

        if self._video.author_username:
            auth = QLabel(f"@{self._video.author_username}")
            auth.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
            auth.setStyleSheet("color:rgba(255,255,255,0.9);background:transparent;")
            auth.setAlignment(_AlignC)
            self._inner.addWidget(auth)

        if self._video.short_description:
            desc = QLabel(self._video.short_description)
            desc.setWordWrap(True)
            desc.setFont(QFont("Segoe UI", 11))
            desc.setStyleSheet("color:rgba(255,255,255,0.7);background:transparent;")
            desc.setAlignment(_AlignC)
            self._inner.addWidget(desc)

    def add_extra(self, widget: QWidget) -> None:
        """Append a widget below the fixed content (used for progress bar etc.)."""
        self._inner.addWidget(widget)

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
