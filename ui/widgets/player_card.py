"""Player card widgets."""
from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from models.player import Player
from models.score import LeaderboardEntry
from utils.helpers import make_avatar_pixmap, round_pixmap, format_score


class PlayerCard(QFrame):
    """Lobby player card."""
    kick_requested = pyqtSignal(str)  # player_id

    def __init__(
        self,
        player: Player,
        show_kick: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._player = player
        self._build(show_kick)

    def _build(self, show_kick: bool) -> None:
        self.setStyleSheet(
            "QFrame{background:#1e1e1e;border:1px solid #2a2a2a;border-radius:10px;}"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(12)

        # Avatar
        pix = make_avatar_pixmap(self._player.initials, 44, self._player.avatar_color)
        av  = QLabel()
        av.setPixmap(round_pixmap(pix, 44))
        av.setFixedSize(44, 44)
        row.addWidget(av)

        # Name + status
        col = QVBoxLayout()
        col.setSpacing(3)
        name = QLabel(self._player.display_name)
        name.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        col.addWidget(name)

        status_parts = []
        if self._player.is_host:
            status_parts.append("🎮 Host")
        if self._player.tiktok_connected:
            tt = self._player.tiktok_username or "TikTok"
            status_parts.append(f"✅ @{tt}")
            if self._player.video_count:
                status_parts.append(f"{self._player.video_count} videos")
        else:
            status_parts.append("⚠️ No TikTok")

        sub = QLabel("  ·  ".join(status_parts))
        sub.setStyleSheet("color:#888;font-size:11px;")
        col.addWidget(sub)
        row.addLayout(col)
        row.addStretch()

        # Ready badge
        self._ready_lbl = QLabel()
        self._set_ready(self._player.is_ready)
        row.addWidget(self._ready_lbl)

        if show_kick and not self._player.is_host:
            kick = QPushButton("✕")
            kick.setFixedSize(28, 28)
            kick.setStyleSheet(
                "QPushButton{background:transparent;border:1px solid #444;"
                "border-radius:14px;color:#888;font-size:12px;}"
                "QPushButton:hover{border-color:#FE2C55;color:#FE2C55;}"
            )
            kick.clicked.connect(lambda: self.kick_requested.emit(self._player.player_id))
            row.addWidget(kick)

    def _set_ready(self, ready: bool) -> None:
        if ready:
            self._ready_lbl.setText("READY")
            self._ready_lbl.setStyleSheet(
                "background:#2ECC71;color:#000;font-size:10px;font-weight:700;"
                "padding:3px 8px;border-radius:4px;"
            )
        else:
            self._ready_lbl.setText("WAITING")
            self._ready_lbl.setStyleSheet(
                "background:#2a2a2a;color:#666;font-size:10px;font-weight:600;"
                "padding:3px 8px;border-radius:4px;"
            )

    def update_player(self, player: Player) -> None:
        self._player = player
        self._set_ready(player.is_ready)


class LeaderboardRow(QFrame):
    """One entry in the end-game leaderboard."""

    def __init__(
        self,
        rank:   int,
        entry:  LeaderboardEntry,
        is_me:  bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        bg     = "rgba(254,44,85,0.08)" if is_me else "#1a1a1a"
        border = "#FE2C55" if is_me else "#2a2a2a"
        self.setStyleSheet(
            f"QFrame{{background:{bg};border:1px solid {border};border-radius:10px;}}"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 12, 16, 12)
        row.setSpacing(14)

        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        rank_lbl = QLabel(medals.get(rank, f"#{rank}"))
        rank_lbl.setFont(QFont("Segoe UI", 18))
        rank_lbl.setFixedWidth(40)
        rank_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(rank_lbl)

        pix = make_avatar_pixmap(entry.display_name[:2], 40, entry.avatar_color)
        av  = QLabel()
        av.setPixmap(round_pixmap(pix, 40))
        av.setFixedSize(40, 40)
        row.addWidget(av)

        col = QVBoxLayout()
        col.setSpacing(2)
        name_lbl = QLabel(entry.display_name + ("  (you)" if is_me else ""))
        name_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        if is_me:
            name_lbl.setStyleSheet("color:#FE2C55;")
        acc_lbl = QLabel(
            f"{entry.correct_answers}/{entry.total_rounds} correct  ·  {entry.accuracy_pct}"
        )
        acc_lbl.setStyleSheet("color:#888;font-size:11px;")
        col.addWidget(name_lbl)
        col.addWidget(acc_lbl)
        row.addLayout(col)
        row.addStretch()

        score_lbl = QLabel(format_score(entry.total_points))
        score_lbl.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        score_lbl.setStyleSheet("color:#FE2C55;")
        row.addWidget(score_lbl)
