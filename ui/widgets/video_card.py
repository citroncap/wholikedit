"""Video card shown during a game round — embeds TikTok player in-app."""
from __future__ import annotations
import re
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QSizePolicy
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QFont, QColor, QPainter, QLinearGradient, QDesktopServices
from models.game import GameVideo

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    _WEBENGINE = True
except ImportError:
    _WEBENGINE = False

# Cycling gradient pairs (index by hash of video_id)
_GRADIENTS = [
    ("#FE2C55", "#FF6B35"),
    ("#25F4EE", "#0090FF"),
    ("#9B59B6", "#FE2C55"),
    ("#2ECC71", "#25F4EE"),
    ("#F39C12", "#FE2C55"),
    ("#3498DB", "#9B59B6"),
    ("#E74C3C", "#F39C12"),
    ("#1ABC9C", "#2ECC71"),
]


def _video_id_from(video: GameVideo) -> str | None:
    """Extract numeric TikTok video ID from video_url, or use video_id if it looks real."""
    if video.video_url:
        m = re.search(r"/video/(\d+)", video.video_url)
        if m:
            return m.group(1)
    vid = video.video_id or ""
    if vid.isdigit() and len(vid) > 10:
        return vid
    return None


class VideoCard(QWidget):
    """Shows TikTok embed player if a real video ID is available, else a gradient placeholder."""

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
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        vid_id = _video_id_from(self._video)

        # Prefer the direct video URL (full TikTok mobile page) — far more reliable
        # than the embed URL which crashes on Qt WebEngine with a prod TypeError.
        if self._video.video_url:
            load_url = self._video.video_url
        elif vid_id:
            load_url = f"https://www.tiktok.com/embed/v2/{vid_id}"
        else:
            load_url = None

        if load_url and _WEBENGINE:
            self._web = QWebEngineView()
            self._web.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self._web.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            try:
                from PyQt6.QtWebEngineCore import (
                    QWebEngineSettings, QWebEnginePage, QWebEngineScript
                )
                self._web.settings().setAttribute(
                    QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False
                )
                # Auto-grant media permissions so video autoplays without a dialog
                self._web.page().featurePermissionRequested.connect(
                    lambda url, feat: self._web.page().setFeaturePermission(
                        url, feat, QWebEnginePage.PermissionPolicy.PermissionGrantedByUser
                    )
                )
                # Bypass TikTok's webdriver/bot detection so the player renders
                bypass = QWebEngineScript()
                bypass.setName("tiktok_bypass")
                bypass.setSourceCode(
                    "try{"
                    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
                    "Object.defineProperty(window,'chrome',{"
                    "  get:()=>({runtime:{},app:{},csi:function(){},loadTimes:function(){}}),"
                    "  configurable:true});"
                    # Suppress all uncaught JS errors (TikTok has several on Qt WebEngine)
                    "window.onerror=function(){return true;};"
                    "window.addEventListener('unhandledrejection',function(e){e.preventDefault();});"
                    "}catch(e){}"
                )
                bypass.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
                bypass.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
                self._web.page().scripts().insert(bypass)
            except Exception:
                pass
            self._web.loadFinished.connect(lambda _ok: self._web.setFocus())
            self._web.load(QUrl(load_url))
            layout.addWidget(self._web)
            # Fallback button: opens video in system browser if the embedded player fails
            if load_url:
                btn = QPushButton("↗  Ouvrir sur TikTok")
                btn.setFixedHeight(32)
                btn.setStyleSheet(
                    "QPushButton{background:#111;color:#aaa;border:none;"
                    "font-size:11px;border-top:1px solid #222;}"
                    "QPushButton:hover{color:#fff;background:#1a1a1a;}"
                )
                btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(load_url)))
                layout.addWidget(btn)
        else:
            # No WebEngine or no video URL — gradient placeholder + open button
            preview = _GradientPreview(self._video, self._color1, self._color2)
            preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            layout.addWidget(preview)
            if load_url:
                btn = QPushButton("↗  Ouvrir sur TikTok")
                btn.setFixedHeight(36)
                btn.setStyleSheet(
                    "QPushButton{background:#1a1a1a;color:#ccc;border:none;"
                    "font-size:12px;border-radius:4px;margin:6px;}"
                    "QPushButton:hover{color:#fff;background:#222;}"
                )
                btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(load_url)))
                layout.addWidget(btn)
            elif not _WEBENGINE:
                lbl = QLabel("Installe PyQt6-WebEngine pour voir la vidéo\npip install PyQt6-WebEngine")
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setStyleSheet("color:#555;font-size:11px;padding:6px;")
                layout.addWidget(lbl)


class _GradientPreview(QWidget):
    """Gradient card showing TikTok branding, author, and description."""

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
        play.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(play)

        layout.addStretch()

        if self._video.author_username:
            author = QLabel(f"@{self._video.author_username}")
            author.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
            author.setStyleSheet("color:rgba(255,255,255,0.9); background:transparent;")
            author.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(author)

        if self._video.short_description:
            desc = QLabel(self._video.short_description)
            desc.setWordWrap(True)
            desc.setFont(QFont("Segoe UI", 11))
            desc.setStyleSheet("color:rgba(255,255,255,0.7); background:transparent;")
            desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
