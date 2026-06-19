"""Main menu screen."""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from services.local_player import LocalPlayer
from utils.helpers import make_avatar_pixmap, round_pixmap


class MainMenuScreen(QWidget):
    host_requested    = pyqtSignal()
    join_requested    = pyqtSignal()
    tiktok_requested  = pyqtSignal()
    settings_requested= pyqtSignal()

    def __init__(self, local_player: LocalPlayer, parent=None) -> None:
        super().__init__(parent)
        self._player = local_player
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top bar ───────────────────────────────────────────────────────────
        bar = QWidget()
        bar.setStyleSheet("background:#0a0a0a;border-bottom:1px solid #1e1e1e;")
        bar.setFixedHeight(64)
        bar_row = QHBoxLayout(bar)
        bar_row.setContentsMargins(24, 0, 24, 0)
        bar_row.setSpacing(12)

        logo = QLabel("❤️  WhoLikedIt?")
        logo.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        logo.setStyleSheet("color:#FE2C55;")
        bar_row.addWidget(logo)
        bar_row.addStretch()

        self._avatar_lbl = QLabel()
        self._avatar_lbl.setFixedSize(34, 34)
        bar_row.addWidget(self._avatar_lbl)

        self._player_name_lbl = QLabel("")
        self._player_name_lbl.setFont(QFont("Segoe UI", 13))
        bar_row.addWidget(self._player_name_lbl)

        settings_btn = QPushButton("⚙️")
        settings_btn.setFixedSize(36, 36)
        settings_btn.setStyleSheet(
            "QPushButton{background:transparent;border:none;font-size:18px;}"
            "QPushButton:hover{background:#1e1e1e;border-radius:8px;}"
        )
        settings_btn.clicked.connect(self.settings_requested)
        bar_row.addWidget(settings_btn)

        root.addWidget(bar)

        # ── Content ───────────────────────────────────────────────────────────
        content = QWidget()
        content.setStyleSheet("background:#0e0e0e;")
        c_layout = QVBoxLayout(content)
        c_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c_layout.setSpacing(0)

        # Hero text
        hero_w = QWidget()
        hero_l = QVBoxLayout(hero_w)
        hero_l.setSpacing(10)
        hero_l.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._greeting = QLabel("Hey, Player! 👋")
        self._greeting.setFont(QFont("Segoe UI", 30, QFont.Weight.ExtraBold))
        self._greeting.setAlignment(Qt.AlignmentFlag.AlignCenter)

        tagline = QLabel(
            "The TikTok guessing game your friend group deserves.\n"
            "Host a game or join one to get started."
        )
        tagline.setFont(QFont("Segoe UI", 14))
        tagline.setStyleSheet("color:#666;")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setWordWrap(True)

        hero_l.addWidget(self._greeting)
        hero_l.addWidget(tagline)
        c_layout.addSpacing(60)
        c_layout.addWidget(hero_w)
        c_layout.addSpacing(48)

        # ── Menu tiles ────────────────────────────────────────────────────────
        tiles = QHBoxLayout()
        tiles.setSpacing(20)
        tiles.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        tiles.addWidget(self._tile(
            "🎮", "Host Game",
            "Create a new room and invite friends",
            self.host_requested, primary=True,
        ))
        tiles.addWidget(self._tile(
            "🔗", "Join Game",
            "Enter a room code to join",
            self.join_requested,
        ))

        c_layout.addLayout(tiles)
        c_layout.addSpacing(20)

        # ── Secondary row ─────────────────────────────────────────────────────
        sec_row = QHBoxLayout()
        sec_row.setSpacing(16)
        sec_row.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self._tiktok_btn = QPushButton("📱  Connect TikTok")
        self._tiktok_btn.setProperty("secondary", True)
        self._tiktok_btn.setFixedHeight(46)
        self._tiktok_btn.setMinimumWidth(200)
        self._tiktok_btn.clicked.connect(self.tiktok_requested)
        sec_row.addWidget(self._tiktok_btn)

        c_layout.addLayout(sec_row)
        c_layout.addStretch()
        root.addWidget(content, 1)

    def _tile(
        self,
        icon: str,
        title: str,
        subtitle: str,
        signal,
        primary: bool = False,
    ) -> QFrame:
        tile = QFrame()
        tile.setFixedSize(220, 160)
        base = (
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #1e0810,stop:1 #1a0010);"
            if primary else
            "background:#1e1e1e;"
        )
        border = "#FE2C55" if primary else "#2a2a2a"
        tile.setStyleSheet(
            f"QFrame{{background:{base}border:1px solid {border};"
            f"border-radius:16px;}}"
            f"QFrame:hover{{border-color:#FE2C55;background:#2a1020;}}"
        )
        tile.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(tile)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)

        icon_lbl = QLabel(icon)
        icon_lbl.setFont(QFont("Segoe UI", 34))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_lbl = QLabel(title)
        title_lbl.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if primary:
            title_lbl.setStyleSheet("color:#FE2C55;")

        sub_lbl = QLabel(subtitle)
        sub_lbl.setStyleSheet("color:#555;font-size:11px;")
        sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_lbl.setWordWrap(True)

        layout.addWidget(icon_lbl)
        layout.addWidget(title_lbl)
        layout.addWidget(sub_lbl)

        tile.mousePressEvent = lambda _: signal.emit()
        return tile

    def refresh(self) -> None:
        name = self._player.display_name or "Player"
        self._greeting.setText(f"Hey, {name}! 👋")
        self._player_name_lbl.setText(name)

        pix = make_avatar_pixmap(name[:2], 34, self._player.avatar_color)
        self._avatar_lbl.setPixmap(round_pixmap(pix, 34))

        if self._player.has_tiktok:
            self._tiktok_btn.setText(f"✅  @{self._player.tiktok_username}")
            self._tiktok_btn.setProperty("secondary", False)
            self._tiktok_btn.setStyleSheet(
                "QPushButton{background:rgba(37,244,238,0.08);"
                "border:2px solid #25F4EE;border-radius:8px;"
                "color:#25F4EE;padding:10px 22px;font-size:14px;font-weight:600;}"
                "QPushButton:hover{background:rgba(37,244,238,0.14);}"
            )
        else:
            self._tiktok_btn.setText("📱  Connect TikTok")
