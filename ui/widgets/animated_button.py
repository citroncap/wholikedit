"""Choice button for game rounds."""
from __future__ import annotations
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class ChoiceButton(QPushButton):
    """A player-choice button used during a game round."""

    def __init__(self, text: str = "", player_id: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.player_id = player_id
        self.setMinimumHeight(58)
        self.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_default()

    def _apply_default(self) -> None:
        self.setStyleSheet("""
            QPushButton {
                background:#242424; border:2px solid #3a3a3a; border-radius:12px;
                padding:12px 20px; color:#FFFFFF; text-align:left;
                font-size:14px; font-weight:600;
            }
            QPushButton:hover {
                background:rgba(254,44,85,0.12); border-color:#FE2C55;
            }
            QPushButton:pressed { background:rgba(254,44,85,0.25); }
        """)

    def mark_correct(self) -> None:
        self.setStyleSheet("""
            QPushButton {
                background:rgba(46,204,113,0.2); border:2px solid #2ECC71;
                border-radius:12px; padding:12px 20px;
                color:#2ECC71; font-size:14px; font-weight:700;
            }
        """)

    def mark_wrong(self) -> None:
        self.setStyleSheet("""
            QPushButton {
                background:rgba(231,76,60,0.15); border:2px solid #E74C3C;
                border-radius:12px; padding:12px 20px;
                color:#E74C3C; font-size:14px; font-weight:600;
            }
        """)

    def mark_selected(self) -> None:
        self.setStyleSheet("""
            QPushButton {
                background:rgba(254,44,85,0.18); border:2px solid #FE2C55;
                border-radius:12px; padding:12px 20px;
                color:#FE2C55; font-size:14px; font-weight:700;
            }
        """)

    def reset(self) -> None:
        self._apply_default()
