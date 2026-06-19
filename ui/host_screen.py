"""Host game configuration screen."""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSpinBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from models.game import GameSettings
from utils.config import DEFAULT_ROUNDS, DEFAULT_TIMER_SEC, DEFAULT_VIDEO_COUNT


class HostScreen(QWidget):
    start_hosting = pyqtSignal(object)   # GameSettings
    back_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        hdr = self._header("Host a Game")
        root.addWidget(hdr)

        # Body
        body = QWidget()
        body.setStyleSheet("background:#0e0e0e;")
        b_layout = QVBoxLayout(body)
        b_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setFixedWidth(480)
        card.setStyleSheet(
            "QFrame{background:#161616;border:1px solid #2a2a2a;border-radius:18px;}"
        )
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(40, 40, 40, 40)
        c_layout.setSpacing(22)

        c_layout.addWidget(_h("Game Settings", 20))

        # Rounds
        c_layout.addLayout(self._spin_row(
            "Rounds", 3, 30, DEFAULT_ROUNDS,
            "Number of videos shown per game",
        ))
        self._rounds_spin = self._last_spin

        # Timer
        c_layout.addLayout(self._spin_row(
            "Timer (seconds)", 0, 120, DEFAULT_TIMER_SEC,
            "Seconds per round — set to 0 for no time limit",
        ))
        self._timer_spin = self._last_spin

        # Video pool
        c_layout.addLayout(self._spin_row(
            "Videos per player", 5, 50, DEFAULT_VIDEO_COUNT,
            "Max videos imported from each player's TikTok",
        ))
        self._video_spin = self._last_spin

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("border-color:#2a2a2a;")
        c_layout.addWidget(sep)

        c_layout.addWidget(_h(
            "Share the room code with friends after hosting starts.",
            12, color="#555",
        ))

        start_btn = QPushButton("🎮  Create Room")
        start_btn.setProperty("primary", True)
        start_btn.setFixedHeight(54)
        start_btn.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        start_btn.clicked.connect(self._on_start)
        c_layout.addWidget(start_btn)

        b_layout.addWidget(card)
        root.addWidget(body, 1)

    def _header(self, title: str) -> QWidget:
        hdr = QWidget()
        hdr.setStyleSheet("background:#0a0a0a;border-bottom:1px solid #1e1e1e;")
        hdr.setFixedHeight(64)
        row = QHBoxLayout(hdr)
        row.setContentsMargins(24, 0, 24, 0)
        back = QPushButton("← Back")
        back.setStyleSheet(
            "background:transparent;border:none;color:#888;font-size:14px;"
        )
        back.clicked.connect(self.back_requested)
        row.addWidget(back)
        row.addStretch()
        row.addWidget(_h(title, 18))
        row.addStretch()
        return hdr

    def _spin_row(
        self, label: str, min_v: int, max_v: int, default: int, hint: str
    ) -> QHBoxLayout:
        row = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(_h(label, 13))
        col.addWidget(_h(hint, 11, color="#555"))
        row.addLayout(col)
        row.addStretch()
        spin = QSpinBox()
        spin.setRange(min_v, max_v)
        spin.setValue(default)
        spin.setFixedSize(90, 44)
        row.addWidget(spin)
        self._last_spin = spin
        return row

    def _on_start(self) -> None:
        settings = GameSettings(
            total_rounds=  self._rounds_spin.value(),
            timer_seconds= self._timer_spin.value(),
            video_count=   self._video_spin.value(),
        )
        self.start_hosting.emit(settings)


def _h(text: str, size: int = 14, bold: bool = True, color: str = "#FFFFFF") -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(QFont("Segoe UI", size, QFont.Weight.Bold if bold else QFont.Weight.Normal))
    lbl.setStyleSheet(f"color:{color};")
    return lbl
