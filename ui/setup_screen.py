"""First-launch setup screen: ask the player for a display name."""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from utils.helpers import validate_display_name


class SetupScreen(QWidget):
    setup_complete = pyqtSignal(str)  # display_name

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setFixedWidth(460)
        card.setStyleSheet(
            "QFrame{background:#161616;border:1px solid #2a2a2a;border-radius:20px;}"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(48, 48, 48, 48)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Logo
        logo = QLabel("❤️")
        logo.setFont(QFont("Segoe UI", 52))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)

        # Title
        title = QLabel("WhoLikedIt?")
        title.setFont(QFont("Segoe UI", 28, QFont.Weight.ExtraBold))
        title.setStyleSheet("color:#FE2C55;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Subtitle
        sub = QLabel("First, what should we call you?")
        sub.setFont(QFont("Segoe UI", 14))
        sub.setStyleSheet("color:#888;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub)

        layout.addSpacing(8)

        # Name input
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("Your display name")
        self._name_input.setFixedHeight(52)
        self._name_input.setFont(QFont("Segoe UI", 15))
        self._name_input.setMaxLength(20)
        self._name_input.returnPressed.connect(self._on_confirm)
        layout.addWidget(self._name_input)

        self._error_lbl = QLabel("")
        self._error_lbl.setStyleSheet("color:#FE2C55;font-size:12px;")
        self._error_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._error_lbl)

        # Confirm button
        btn = QPushButton("Let's Play!")
        btn.setProperty("primary", True)
        btn.setFixedHeight(52)
        btn.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        btn.clicked.connect(self._on_confirm)
        layout.addWidget(btn)

        # Note
        note = QLabel("This name is visible to other players.\nYou can change it later in Settings.")
        note.setStyleSheet("color:#444;font-size:11px;")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(note)

        outer.addWidget(card)

    def _on_confirm(self) -> None:
        self._error_lbl.setText("")
        name = self._name_input.text().strip()
        ok, err = validate_display_name(name)
        if not ok:
            self._error_lbl.setText(err)
            return
        self.setup_complete.emit(name)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._name_input.setFocus()
