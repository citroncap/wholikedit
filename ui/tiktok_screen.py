"""Liked Videos screen — import TikTok liked videos via browser console script."""
from __future__ import annotations
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from services.local_player import LocalPlayer
from services.video_store import VideoStore
from database.db_manager import DatabaseManager
from utils.config import Settings

log = logging.getLogger(__name__)


class TikTokScreen(QWidget):
    back_requested = pyqtSignal()
    connected      = pyqtSignal()   # kept for main_window compatibility
    open_settings  = pyqtSignal()   # kept for main_window compatibility

    def __init__(
        self,
        local_player: LocalPlayer,
        db: DatabaseManager,
        settings: Settings,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._player      = local_player
        self._db          = db
        self._settings    = settings
        self._video_store = VideoStore()
        self._build()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        hdr = QWidget()
        hdr.setStyleSheet("background:#0a0a0a;border-bottom:1px solid #1e1e1e;")
        hdr.setFixedHeight(64)
        h_row = QHBoxLayout(hdr)
        h_row.setContentsMargins(24, 0, 24, 0)
        back = QPushButton("← Back")
        back.setStyleSheet("background:transparent;border:none;color:#888;font-size:14px;")
        back.clicked.connect(self.back_requested)
        h_row.addWidget(back)
        h_row.addStretch()
        h_row.addWidget(_h("Liked Videos", 18))
        h_row.addStretch()
        root.addWidget(hdr)

        # Body
        body = QWidget()
        body.setStyleSheet("background:#0e0e0e;")
        b = QVBoxLayout(body)
        b.setAlignment(Qt.AlignmentFlag.AlignCenter)
        b.setSpacing(20)
        b.setContentsMargins(40, 40, 40, 40)

        b.addWidget(self._build_status_card())
        b.addWidget(self._build_import_card())

        root.addWidget(body, 1)

    def _build_status_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(10)

        row = QHBoxLayout()
        row.addWidget(_h("Imported Videos", 16))
        row.addStretch()
        self._count_badge = QLabel("0 videos")
        self._count_badge.setStyleSheet(
            "background:#2a2a2a;color:#888;font-size:12px;"
            "padding:4px 12px;border-radius:10px;"
        )
        row.addWidget(self._count_badge)
        layout.addLayout(row)

        self._status_lbl = QLabel(
            "No liked videos imported yet.\n"
            "Use the Import button below to get started."
        )
        self._status_lbl.setStyleSheet("color:#666;font-size:13px;")
        self._status_lbl.setWordWrap(True)
        layout.addWidget(self._status_lbl)

        return card

    def _build_import_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        layout.addWidget(_h("Import from TikTok", 16))

        desc = QLabel(
            "No API key required. A small script runs in your browser "
            "where you are already logged in to TikTok — your data never "
            "leaves your machine."
        )
        desc.setStyleSheet("color:#888;font-size:12px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        for step, text in [
            ("1", "Click Import — your browser opens TikTok"),
            ("2", "Go to Profile → Liked tab, open F12 console, paste the script"),
            ("3", "Page scrolls automatically, a JSON file downloads"),
            ("4", "Come back here and select the downloaded file"),
        ]:
            row = QHBoxLayout()
            num = QLabel(step)
            num.setFixedSize(24, 24)
            num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            num.setStyleSheet(
                "background:#FE2C55;color:#fff;border-radius:12px;"
                "font-size:11px;font-weight:700;"
            )
            lbl = QLabel(text)
            lbl.setStyleSheet("color:#888;font-size:12px;")
            row.addWidget(num)
            row.addSpacing(8)
            row.addWidget(lbl)
            row.addStretch()
            layout.addLayout(row)

        btn_row = QHBoxLayout()

        import_btn = QPushButton("Import Liked Videos")
        import_btn.setProperty("primary", True)
        import_btn.setFixedHeight(50)
        import_btn.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        import_btn.clicked.connect(self._on_import_clicked)
        btn_row.addWidget(import_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.setProperty("danger", True)
        clear_btn.setFixedHeight(50)
        clear_btn.clicked.connect(self._on_clear)
        btn_row.addWidget(clear_btn)

        layout.addLayout(btn_row)
        return card

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        count = self._video_store.count()
        if count:
            self._count_badge.setText(f"{count} videos")
            self._count_badge.setStyleSheet(
                "background:rgba(37,244,238,0.12);color:#25F4EE;"
                "font-size:12px;padding:4px 12px;border-radius:10px;"
            )
            self._status_lbl.setText(
                f"{count} liked videos ready for the game.\n"
                "Click Import again to update your collection."
            )
            self._status_lbl.setStyleSheet("color:#aaa;font-size:13px;")
        else:
            self._count_badge.setText("0 videos")
            self._count_badge.setStyleSheet(
                "background:#2a2a2a;color:#888;"
                "font-size:12px;padding:4px 12px;border-radius:10px;"
            )
            self._status_lbl.setText(
                "No liked videos imported yet.\n"
                "Use the Import button below to get started."
            )
            self._status_lbl.setStyleSheet("color:#666;font-size:13px;")

    def get_liked_videos(self) -> list[dict]:
        return self._video_store.get_videos()

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _on_import_clicked(self) -> None:
        from ui.import_dialog import ImportLikesDialog
        dlg = ImportLikesDialog(self)
        dlg.videos_imported.connect(self._on_videos_imported)
        dlg.exec()

    def _on_videos_imported(self, videos: list) -> None:
        self._video_store.set_videos(videos)
        self.refresh()
        log.info("Stored %d liked videos", len(videos))

    def _on_clear(self) -> None:
        count = self._video_store.count()
        if count == 0:
            return
        reply = QMessageBox.question(
            self, "Clear Liked Videos",
            f"Delete all {count} imported liked videos?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._video_store.clear()
            self.refresh()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _h(
    text: str, size: int = 14, bold: bool = True, color: str = "#FFFFFF"
) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(
        QFont("Segoe UI", size, QFont.Weight.Bold if bold else QFont.Weight.Normal)
    )
    lbl.setStyleSheet(f"color:{color};")
    return lbl


def _card() -> QFrame:
    f = QFrame()
    f.setFixedWidth(560)
    f.setStyleSheet(
        "QFrame{background:#161616;border:1px solid #2a2a2a;border-radius:16px;}"
    )
    return f
