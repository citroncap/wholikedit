"""Settings screen."""
from __future__ import annotations
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSpinBox, QLineEdit, QMessageBox, QScrollArea,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from services.local_player import LocalPlayer
from utils.config import Settings
from utils.helpers import validate_display_name, avatar_color_for

log = logging.getLogger(__name__)


class SettingsScreen(QWidget):
    back_requested = pyqtSignal()
    name_changed   = pyqtSignal(str)

    def __init__(
        self,
        local_player: LocalPlayer,
        settings: Settings,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._player   = local_player
        self._settings = settings
        self._build()

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
        h_row.addWidget(_h("Settings", 18))
        h_row.addStretch()
        root.addWidget(hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        body = QWidget()
        body.setStyleSheet("background:#0e0e0e;")
        b = QVBoxLayout(body)
        b.setContentsMargins(40, 40, 40, 40)
        b.setSpacing(24)
        b.setAlignment(Qt.AlignmentFlag.AlignTop)

        b.addWidget(self._build_profile_card())
        b.addWidget(self._build_game_card())
        b.addWidget(self._build_about_card())
        b.addStretch()

        scroll.setWidget(body)
        root.addWidget(scroll, 1)

    # ── Cards ─────────────────────────────────────────────────────────────────

    def _build_profile_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        layout.addWidget(_h("Your Profile", 16))
        layout.addWidget(_h("Display Name", 12, color="#888"))

        self._name_edit = QLineEdit()
        self._name_edit.setFixedHeight(48)
        self._name_edit.setMaxLength(20)
        layout.addWidget(self._name_edit)

        self._name_err = QLabel("")
        self._name_err.setStyleSheet("color:#FE2C55;font-size:12px;")
        layout.addWidget(self._name_err)

        save = QPushButton("Save Name")
        save.setProperty("primary", True)
        save.setFixedHeight(46)
        save.clicked.connect(self._save_name)
        layout.addWidget(save)
        return card

    def _build_game_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        layout.addWidget(_h("Game Defaults", 16))

        row1 = QHBoxLayout()
        row1.addWidget(_h("Default rounds", 13, color="#aaa"))
        row1.addStretch()
        self._rounds_spin = QSpinBox()
        self._rounds_spin.setRange(3, 30)
        self._rounds_spin.setValue(self._settings.get("rounds_per_game"))
        self._rounds_spin.setFixedSize(90, 44)
        row1.addWidget(self._rounds_spin)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(_h("Round timer (s)", 13, color="#aaa"))
        row2.addStretch()
        self._timer_spin = QSpinBox()
        self._timer_spin.setRange(5, 60)
        self._timer_spin.setValue(self._settings.get("round_timer"))
        self._timer_spin.setFixedSize(90, 44)
        row2.addWidget(self._timer_spin)
        layout.addLayout(row2)

        save = QPushButton("Save Game Settings")
        save.setProperty("primary", True)
        save.setFixedHeight(46)
        save.clicked.connect(self._save_game)
        layout.addWidget(save)
        return card

    def _build_about_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(8)
        layout.addWidget(_h("About", 16))
        for text, color in [
            ("WhoLikedIt?  v2.0.0", "#FFFFFF"),
            ("Peer-to-peer TikTok guessing game", "#888"),
            ("Python 3.12  ·  PyQt6  ·  SQLite", "#555"),
        ]:
            lbl = QLabel(text)
            lbl.setStyleSheet(f"color:{color};font-size:13px;")
            layout.addWidget(lbl)
        return card

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        self._name_edit.setText(self._player.display_name)
        self._name_err.setText("")
        self._rounds_spin.setValue(self._settings.get("rounds_per_game"))
        self._timer_spin.setValue(self._settings.get("round_timer"))

    # ── Save handlers ─────────────────────────────────────────────────────────

    def _save_name(self) -> None:
        self._name_err.setText("")
        name = self._name_edit.text().strip()
        ok, err = validate_display_name(name)
        if not ok:
            self._name_err.setText(err)
            return
        self._player.display_name = name
        self._player.avatar_color = avatar_color_for(name)
        self._player.save()
        self.name_changed.emit(name)
        QMessageBox.information(self, "Saved", "Display name updated.")

    def _save_game(self) -> None:
        self._settings.set("rounds_per_game", self._rounds_spin.value())
        self._settings.set("round_timer",     self._timer_spin.value())
        QMessageBox.information(self, "Saved", "Game settings saved.")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _h(
    text: str, size: int = 14, bold: bool = True, color: str = "#FFFFFF"
) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(
        QFont("Segoe UI", size, QFont.Weight.Bold if bold else QFont.Weight.Normal)
    )
    lbl.setStyleSheet(f"color:{color};")
    lbl.setWordWrap(True)
    return lbl


def _card() -> QFrame:
    f = QFrame()
    f.setStyleSheet(
        "QFrame{background:#161616;border:1px solid #2a2a2a;border-radius:16px;}"
    )
    return f
