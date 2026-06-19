"""Video card shown during a game round — preview placeholder + download/browser options."""
from __future__ import annotations
import os
import re
import tempfile
import threading
import urllib.request
import webbrowser
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy
from PyQt6.QtCore import Qt, QMetaObject, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QColor, QPainter, QLinearGradient
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

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.tiktok.com/",
}


def _extract_video_id(video: GameVideo) -> str:
    if video.video_url:
        m = re.search(r"/video/(\d+)", video.video_url)
        if m:
            return m.group(1)
    return video.video_id


class VideoCard(QWidget):
    """Shows a styled preview placeholder with Watch and Download-Preview buttons."""

    # Emitted with the local temp file path after a successful download
    video_downloaded = pyqtSignal(str)

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
        self._preview_btn = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.setSpacing(8)

        # ── Gradient preview ─────────────────────────────────────────────────
        preview = _GradientPreview(self._video, self._color1, self._color2)
        preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(preview, stretch=1)

        has_url = bool(self._video.video_url)

        # ── Download & preview locally ───────────────────────────────────────
        prev_btn = QPushButton("📥  Preview (télécharger)")
        prev_btn.setFixedHeight(40)
        prev_btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        prev_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {self._color1}, stop:1 {self._color2});
                color: #fff; border: none; border-radius: 10px;
                font-weight: 700; letter-spacing: 0.5px;
            }}
            QPushButton:hover  {{ opacity: 0.88; }}
            QPushButton:pressed {{ opacity: 0.70; }}
            QPushButton:disabled {{ background: #2a2a2a; color: #555; }}
        """)
        if has_url:
            prev_btn.clicked.connect(self._on_preview_click)
        else:
            prev_btn.setEnabled(False)
            prev_btn.setText("Pas de lien disponible")
        self._preview_btn = prev_btn
        layout.addWidget(prev_btn)

        # ── Open in browser (secondary) ───────────────────────────────────────
        if has_url:
            watch_btn = QPushButton("↗  Ouvrir dans le navigateur")
            watch_btn.setFixedHeight(32)
            watch_btn.setFont(QFont("Segoe UI", 10))
            watch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            watch_btn.setStyleSheet("""
                QPushButton {
                    background: transparent; color: #888;
                    border: 1px solid #333; border-radius: 8px;
                }
                QPushButton:hover { color: #fff; border-color: #666; }
            """)
            url = self._video.video_url
            watch_btn.clicked.connect(lambda: webbrowser.open(url))
            layout.addWidget(watch_btn)

    # ── Download logic ────────────────────────────────────────────────────────

    def _on_preview_click(self) -> None:
        if not self._preview_btn:
            return
        self._preview_btn.setEnabled(False)
        self._preview_btn.setText("⏳  Téléchargement…")
        url = self._video.video_url
        threading.Thread(target=self._download_thread, args=(url,), daemon=True).start()

    def _download_thread(self, url: str) -> None:
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            suffix = ".mp4"
            fd, path = tempfile.mkstemp(suffix=suffix)
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            self.video_downloaded.emit(path)
            self._set_preview_done(path)
        except Exception as exc:
            self._set_preview_error(str(exc))

    def _set_preview_done(self, path: str) -> None:
        self._pending_path = path
        QMetaObject.invokeMethod(
            self, "_open_and_label", Qt.ConnectionType.QueuedConnection,
        )

    def _set_preview_error(self, msg: str) -> None:
        self._pending_error = msg
        QMetaObject.invokeMethod(
            self, "_show_error", Qt.ConnectionType.QueuedConnection,
        )

    @pyqtSlot()
    def _open_and_label(self) -> None:
        path = getattr(self, "_pending_path", None)
        if path and os.path.exists(path):
            os.startfile(path)
            if self._preview_btn:
                self._preview_btn.setText("✅  Ouvert !")
        if self._preview_btn:
            self._preview_btn.setEnabled(True)

    @pyqtSlot()
    def _show_error(self) -> None:
        if self._preview_btn:
            self._preview_btn.setText("❌  Échec — ouvre dans le navigateur")
            self._preview_btn.setEnabled(True)


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
