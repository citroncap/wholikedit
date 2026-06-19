"""Step-by-step dialog for importing liked videos via browser console script."""
from __future__ import annotations
import logging
import webbrowser
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QFileDialog, QFrame, QMessageBox, QApplication, QWidget,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from tiktok.scraper import JS_SNIPPET, parse_likes_file

log = logging.getLogger(__name__)

_TIKTOK_URL = "https://www.tiktok.com"


class ImportLikesDialog(QDialog):
    """Guides the user through the 3-step liked-video import flow."""

    videos_imported = pyqtSignal(list)  # emits list[dict] on success

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import Liked Videos — WhoLikedIt?")
        self.setMinimumWidth(660)
        self.setStyleSheet("background:#0e0e0e;color:#fff;")
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(18)

        # Title
        title = QLabel("Import your TikTok Liked Videos")
        title.setFont(QFont("Segoe UI", 17, QFont.Weight.Bold))
        title.setStyleSheet("color:#fff;")
        root.addWidget(title)

        sub = QLabel(
            "No TikTok API required. Run a script in your browser where you are "
            "already logged in — your data never leaves your machine."
        )
        sub.setStyleSheet("color:#666;font-size:12px;")
        sub.setWordWrap(True)
        root.addWidget(sub)

        root.addWidget(_divider())

        # ── Step 1 ────────────────────────────────────────────────────────────
        root.addWidget(_step_header("1", "Open TikTok and navigate to your Liked Videos"))
        root.addWidget(_note(
            "Click the button below, then go to your Profile → 'Liked' tab.\n"
            "Make sure you are logged in."
        ))
        btn_open = QPushButton("Open TikTok.com in Browser  ↗")
        btn_open.setProperty("primary", True)
        btn_open.setFixedHeight(44)
        btn_open.clicked.connect(lambda: webbrowser.open(_TIKTOK_URL))
        root.addWidget(btn_open)

        root.addWidget(_divider())

        # ── Step 2 ────────────────────────────────────────────────────────────
        root.addWidget(_step_header("2", "Open the browser console and run the script"))
        root.addWidget(_note(
            "Press F12 → go to the Console tab → paste the script below → press Enter.\n"
            "The page will scroll automatically. A file will download when done."
        ))

        snippet = QTextEdit()
        snippet.setReadOnly(True)
        snippet.setPlainText(JS_SNIPPET)
        snippet.setFixedHeight(120)
        snippet.setStyleSheet(
            "background:#0a0a0a;color:#25F4EE;"
            "font-family:Consolas,Courier New,monospace;font-size:11px;"
            "border:1px solid #2a2a2a;border-radius:8px;padding:6px;"
        )
        root.addWidget(snippet)

        self._copy_btn = QPushButton("Copy Script to Clipboard")
        self._copy_btn.setFixedHeight(42)
        self._copy_btn.clicked.connect(self._copy_script)
        root.addWidget(self._copy_btn)

        root.addWidget(_divider())

        # ── Step 3 ────────────────────────────────────────────────────────────
        root.addWidget(_step_header("3", "Import the downloaded file into the app"))
        root.addWidget(_note(
            "Once the script finishes it will download 'wholikedit_likes.json'.\n"
            "Click Import below and select that file."
        ))

        self._import_btn = QPushButton("Import  wholikedit_likes.json")
        self._import_btn.setProperty("primary", True)
        self._import_btn.setFixedHeight(48)
        self._import_btn.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self._import_btn.clicked.connect(self._import_file)
        root.addWidget(self._import_btn)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color:#2ECC71;font-size:12px;")
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setVisible(False)
        root.addWidget(self._status_lbl)

        root.addWidget(_divider())

        # Close
        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(40)
        close_btn.setStyleSheet(
            "background:#1e1e1e;color:#888;border:1px solid #2a2a2a;border-radius:8px;"
        )
        close_btn.clicked.connect(self.accept)
        root.addWidget(close_btn)

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _copy_script(self) -> None:
        QApplication.clipboard().setText(JS_SNIPPET)
        self._copy_btn.setText("Copied!")
        self._copy_btn.setStyleSheet(
            "background:rgba(46,204,113,0.15);color:#2ECC71;"
            "border:1px solid rgba(46,204,113,0.3);border-radius:8px;"
        )
        log.debug("JS snippet copied to clipboard")

    def _import_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select wholikedit_likes.json", "", "JSON Files (*.json)"
        )
        if not path:
            return

        videos = parse_likes_file(Path(path))
        if not videos:
            QMessageBox.warning(
                self, "Import Failed",
                "No videos found in the file.\n\n"
                "Make sure you selected the correct 'wholikedit_likes.json' file "
                "that was downloaded by the browser script.",
            )
            return

        self._status_lbl.setText(
            f"✓  {len(videos)} liked videos imported successfully!"
        )
        self._status_lbl.setVisible(True)
        self._import_btn.setEnabled(False)
        log.info("Import dialog: %d videos imported", len(videos))
        self.videos_imported.emit(videos)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _step_header(number: str, text: str) -> QWidget:
    w = QWidget()
    row = QHBoxLayout(w)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(10)

    badge = QLabel(number)
    badge.setFixedSize(26, 26)
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setStyleSheet(
        "background:#FE2C55;color:#fff;border-radius:13px;"
        "font-size:12px;font-weight:700;"
    )
    lbl = QLabel(text)
    lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
    lbl.setStyleSheet("color:#fff;")

    row.addWidget(badge)
    row.addWidget(lbl)
    row.addStretch()
    return w


def _note(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("color:#888;font-size:12px;padding-left:36px;")
    lbl.setWordWrap(True)
    return lbl


def _divider() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet("color:#1e1e1e;")
    return f
