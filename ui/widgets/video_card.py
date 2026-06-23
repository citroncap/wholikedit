"""Video card shown during a game round.

Loads the TikTok embed URL directly in QtWebEngine (no download, no transcoding).
Falls back to a gradient preview card if WebEngine is unavailable or the embed fails.
"""
from __future__ import annotations
import logging
import re
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QSizePolicy, QStackedWidget, QLabel,
)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QFont, QColor, QPainter, QLinearGradient, QDesktopServices
from models.game import GameVideo

log = logging.getLogger(__name__)

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    _WEBENGINE = True
except ImportError as _e:
    log.warning("PyQt6-WebEngine not available: %s", _e)
    _WEBENGINE = False

_GRADIENTS = [
    ("#FE2C55", "#FF6B35"), ("#25F4EE", "#0090FF"), ("#9B59B6", "#FE2C55"),
    ("#2ECC71", "#25F4EE"), ("#F39C12", "#FE2C55"), ("#3498DB", "#9B59B6"),
    ("#E74C3C", "#F39C12"), ("#1ABC9C", "#2ECC71"),
]
_AlignC = Qt.AlignmentFlag.AlignCenter

# Pretend to be Chrome so TikTok doesn't serve a "watch in app" page
_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
_TIKTOK_ID_RE = re.compile(r"^\d{8,}$")
_ua_applied = False


def _apply_chrome_ua() -> None:
    """Set Chrome user agent on the default WebEngine profile (once)."""
    global _ua_applied
    if _ua_applied or not _WEBENGINE:
        return
    try:
        from PyQt6.QtWebEngineCore import QWebEngineProfile
        QWebEngineProfile.defaultProfile().setHttpUserAgent(_CHROME_UA)
        _ua_applied = True
    except Exception as exc:
        log.warning("Could not set WebEngine user agent: %s", exc)


class VideoCard(QWidget):
    """Displays a TikTok video via the official embed URL.

    Stack:
      0 – TikTok embed  (QWebEngineView loading tiktok.com/embed/v2/{id})
      1 – Gradient fallback (WebEngine unavailable or load error)
    """

    def __init__(
        self,
        video: GameVideo,
        color1: str = "#FE2C55",
        color2: str = "#25F4EE",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._video  = video
        self._color1 = color1
        self._color2 = color2
        self._view: "QWebEngineView | None" = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._build()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget()
        root.addWidget(self._stack)

        self._stack.addWidget(self._make_player_page())   # 0
        self._stack.addWidget(self._make_fallback_page()) # 1

        video_id = self._video.video_id
        if _WEBENGINE and video_id and _TIKTOK_ID_RE.match(video_id):
            _apply_chrome_ua()
            self._load_embed(video_id)
            self._stack.setCurrentIndex(0)
        else:
            log.info(
                "VideoCard fallback: webengine=%s video_id=%r",
                _WEBENGINE, video_id,
            )
            self._stack.setCurrentIndex(1)

    def _make_player_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background:#000;")
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        if _WEBENGINE:
            self._view = QWebEngineView()
            self._view.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            v.addWidget(self._view, 1)

        ctrl = self._make_ctrl_bar()
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

    # ── Embed loading ─────────────────────────────────────────────────────────

    def _load_embed(self, video_id: str) -> None:
        if not self._view:
            return
        try:
            from PyQt6.QtWebEngineCore import QWebEngineSettings
            self._view.settings().setAttribute(
                QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False
            )
        except Exception as exc:
            log.warning("WebEngine settings: %s", exc)

        embed_url = f"https://www.tiktok.com/embed/v2/{video_id}"
        log.info("Loading TikTok embed: %s", embed_url)
        self._view.loadFinished.connect(self._on_load_finished)
        self._view.load(QUrl(embed_url))

    def _on_load_finished(self, ok: bool) -> None:
        log.info("TikTok embed loadFinished ok=%s", ok)
        if not ok:
            log.warning("Embed failed — showing gradient fallback")
            self._stack.setCurrentIndex(1)
            return
        # Nudge autoplay — TikTok's player should handle it, but just in case
        try:
            self._view.page().runJavaScript(
                "var v=document.querySelector('video');"
                "if(v){v.muted=false;v.play().catch(function(){});}"
            )
        except Exception:
            pass

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def cleanup(self) -> None:
        """Stop embed. Must be called before deleteLater()."""
        if self._view:
            try:
                self._view.loadFinished.disconnect()
            except Exception:
                pass
            try:
                self._view.load(QUrl("about:blank"))
            except Exception:
                pass


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
