"""Video card shown during a game round — preview placeholder + open in browser."""
from __future__ import annotations
import re
import webbrowser
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QSizePolicy
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPixmap, QColor, QPainter, QLinearGradient, QGradient
from models.game import GameVideo

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


def _extract_video_id(video: GameVideo) -> str:
    if video.video_url:
        m = re.search(r"/video/(\d+)", video.video_url)
        if m:
            return m.group(1)
    return video.video_id


class VideoCard(QWidget):
    """Shows a styled preview placeholder with a Watch button below."""

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
        layout.setContentsMargins(0, 0, 0, 12)
        layout.setSpacing(10)

        # ── Gradient preview (fills available height) ────────────────────────
        preview = _GradientPreview(self._video, self._color1, self._color2)
        preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(preview, stretch=1)

        # ── Watch button ─────────────────────────────────────────────────────
        has_url = bool(self._video.video_url)
        watch_btn = QPushButton("▶  Watch on TikTok")
        watch_btn.setFixedHeight(44)
        watch_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        watch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        watch_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {self._color1}, stop:1 {self._color2});
                color: #fff;
                border: none;
                border-radius: 10px;
                font-weight: 700;
                letter-spacing: 0.5px;
            }}
            QPushButton:hover  {{ opacity: 0.88; }}
            QPushButton:pressed {{ opacity: 0.70; }}
            QPushButton:disabled {{
                background: #2a2a2a;
                color: #555;
            }}
        """)
        if has_url:
            url = self._video.video_url
            watch_btn.clicked.connect(lambda: webbrowser.open(url))
        else:
            watch_btn.setEnabled(False)
            watch_btn.setText("No link available")
        layout.addWidget(watch_btn)


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

        # TikTok label top-left
        tk = QLabel("TikTok")
        tk.setFont(QFont("Segoe UI", 18, QFont.Weight.ExtraBold))
        tk.setStyleSheet("color:rgba(255,255,255,0.95); background:transparent;")
        layout.addWidget(tk)

        layout.addStretch()

        # Play icon
        play = QLabel("▶")
        play.setFont(QFont("Segoe UI", 56))
        play.setStyleSheet("color:rgba(255,255,255,0.75); background:transparent;")
        play.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(play)

        layout.addStretch()

        # Author name
        if self._video.author_username:
            author = QLabel(f"@{self._video.author_username}")
            author.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
            author.setStyleSheet("color:rgba(255,255,255,0.9); background:transparent;")
            author.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(author)

        # Description snippet
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
