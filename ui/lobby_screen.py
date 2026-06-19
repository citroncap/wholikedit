"""Lobby screen – shows connected players, ready status, room code.
Works for both the host (has extra controls) and joining clients.
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QLineEdit, QApplication,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont
from models.player import Player
from ui.widgets.player_card import PlayerCard
from utils.config import AVATAR_COLORS, RELAY_URL


class LobbyScreen(QWidget):
    # Host signals
    start_game_requested = pyqtSignal()
    kick_player_requested = pyqtSignal(str)   # player_id
    # Client signal
    ready_toggled = pyqtSignal(bool)          # ready state
    # Both
    leave_requested = pyqtSignal()
    # Identity change (display_name, avatar_color)
    identity_changed = pyqtSignal(str, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._is_host       = False
        self._my_player_id  = ""
        self._my_color      = AVATAR_COLORS[0]
        self._players:  list[Player] = []
        self._cards:    dict[str, PlayerCard] = {}
        self._color_btns: list[QPushButton] = []
        self._lan_code:    str = ""
        self._direct_addr: str = ""
        self._ready_state: bool = False
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = QWidget()
        hdr.setStyleSheet("background:#0a0a0a;border-bottom:1px solid #1e1e1e;")
        hdr.setFixedHeight(64)
        h_row = QHBoxLayout(hdr)
        h_row.setContentsMargins(24, 0, 24, 0)
        h_row.setSpacing(16)

        leave_btn = QPushButton("✕  Leave")
        leave_btn.setProperty("danger", True)
        leave_btn.setFixedHeight(34)
        leave_btn.clicked.connect(self.leave_requested)
        h_row.addWidget(leave_btn)

        h_row.addStretch()

        self._room_code_lbl = QLabel("Room —")
        self._room_code_lbl.setFont(QFont("Courier New", 22, QFont.Weight.Bold))
        self._room_code_lbl.setStyleSheet("color:#FE2C55;letter-spacing:4px;")
        h_row.addWidget(self._room_code_lbl)

        h_row.addStretch()

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color:#888;font-size:13px;")
        h_row.addWidget(self._status_lbl)

        root.addWidget(hdr)

        # ── Main content ──────────────────────────────────────────────────────
        body = QWidget()
        body.setStyleSheet("background:#0e0e0e;")
        b_row = QHBoxLayout(body)
        b_row.setContentsMargins(32, 32, 32, 32)
        b_row.setSpacing(24)

        # Left: player list
        b_row.addWidget(self._build_player_panel(), 3)
        # Right: info + controls
        b_row.addWidget(self._build_side_panel(), 2)

        root.addWidget(body, 1)

    def _build_player_panel(self) -> QWidget:
        panel = QFrame()
        panel.setStyleSheet(
            "QFrame{background:#161616;border:1px solid #2a2a2a;border-radius:16px;}"
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self._player_count_lbl = QLabel("Players  0 / 8")
        self._player_count_lbl.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        layout.addWidget(self._player_count_lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._players_container = QWidget()
        self._players_container.setStyleSheet("background:transparent;")
        self._players_vbox = QVBoxLayout(self._players_container)
        self._players_vbox.setSpacing(8)
        self._players_vbox.addStretch()
        scroll.setWidget(self._players_container)
        layout.addWidget(scroll, 1)
        return panel

    def _build_side_panel(self) -> QWidget:
        panel = QFrame()
        panel.setStyleSheet(
            "QFrame{background:#161616;border:1px solid #2a2a2a;border-radius:16px;}"
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Connection codes block
        code_frame = QFrame()
        code_frame.setStyleSheet(
            "QFrame{background:#1a1a1a;border:1px solid #2a2a2a;border-radius:12px;}"
        )
        cf = QVBoxLayout(code_frame)
        cf.setContentsMargins(16, 12, 16, 12)
        cf.setSpacing(6)

        # ── LAN discovery code ───────────────────────────────────────────────
        cf.addWidget(_lbl("Room code (same WiFi)", 11, color="#555"))
        lan_row = QHBoxLayout()
        self._big_code_lbl = QLabel("——")
        self._big_code_lbl.setFont(QFont("Courier New", 22, QFont.Weight.Bold))
        self._big_code_lbl.setStyleSheet("color:#FE2C55;letter-spacing:4px;")
        lan_row.addWidget(self._big_code_lbl)
        lan_row.addStretch()
        self._copy_lan_btn = self._make_copy_btn()
        self._copy_lan_btn.clicked.connect(self._on_copy_lan)
        lan_row.addWidget(self._copy_lan_btn)
        cf.addLayout(lan_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#2a2a2a; margin:4px 0;")
        cf.addWidget(sep)

        # ── Relay / Direct IP ────────────────────────────────────────────────
        if RELAY_URL:
            self._relay_badge = QLabel("⏳  Relay connecting…")
            self._relay_badge.setStyleSheet(
                "color:#888;font-size:10px;background:#1a1a1a;"
                "border:1px solid #2a2a2a;border-radius:6px;padding:4px 8px;"
            )
            self._relay_badge.setWordWrap(True)
            cf.addWidget(self._relay_badge)
            # Hide ip-related widgets (relay handles internet)
            self._ip_type_lbl = _lbl("", 11)   # placeholder kept for set_direct_address compat
            self._ip_type_lbl.setVisible(False)
            self._ip_addr_lbl = QLabel()
            self._ip_addr_lbl.setVisible(False)
            self._copy_ip_btn = self._make_copy_btn()
            self._copy_ip_btn.setVisible(False)
            self._ip_hint_lbl = QLabel()
            self._ip_hint_lbl.setVisible(False)
            self._ts_btn = QPushButton()
            self._ts_btn.setVisible(False)
        else:
            self._relay_badge = None
            self._ip_type_lbl = _lbl("Direct IP (same WiFi only)", 11, color="#555")
            cf.addWidget(self._ip_type_lbl)
            ip_row = QHBoxLayout()
            self._ip_addr_lbl = QLabel("—")
            self._ip_addr_lbl.setFont(QFont("Courier New", 13, QFont.Weight.Bold))
            self._ip_addr_lbl.setStyleSheet("color:#25F4EE;")
            ip_row.addWidget(self._ip_addr_lbl)
            ip_row.addStretch()
            self._copy_ip_btn = self._make_copy_btn()
            self._copy_ip_btn.setEnabled(False)
            self._copy_ip_btn.clicked.connect(self._on_copy_ip)
            ip_row.addWidget(self._copy_ip_btn)
            cf.addLayout(ip_row)

            self._ip_hint_lbl = QLabel("⚠️ Same WiFi only — install Tailscale for other networks")
            self._ip_hint_lbl.setStyleSheet("color:#664400;font-size:10px;")
            self._ip_hint_lbl.setWordWrap(True)
            cf.addWidget(self._ip_hint_lbl)

            self._ts_btn = QPushButton("🌐  Get Tailscale (free — works across any network)")
            self._ts_btn.setFixedHeight(28)
            self._ts_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._ts_btn.setStyleSheet("""
                QPushButton{background:transparent;border:1px solid #2a2a2a;border-radius:6px;
                            color:#555;font-size:10px;padding:2px 8px;text-align:left;}
                QPushButton:hover{border-color:#25F4EE;color:#25F4EE;}
            """)
            self._ts_btn.clicked.connect(
                lambda: __import__("webbrowser").open("https://tailscale.com/download")
            )
            cf.addWidget(self._ts_btn)

        layout.addWidget(code_frame)

        # ── Identity block ────────────────────────────────────────────────────
        id_frame = QFrame()
        id_frame.setStyleSheet(
            "QFrame{background:#1a1a1a;border:1px solid #2a2a2a;border-radius:12px;}"
        )
        idf = QVBoxLayout(id_frame)
        idf.setContentsMargins(16, 14, 16, 14)
        idf.setSpacing(10)
        idf.addWidget(_lbl("Your Identity", 12, color="#888"))

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Display name…")
        self._name_edit.setFixedHeight(38)
        self._name_edit.setStyleSheet("""
            QLineEdit {
                background:#242424; border:1px solid #3a3a3a; border-radius:8px;
                padding:6px 12px; color:#fff; font-size:14px; font-weight:600;
            }
            QLineEdit:focus { border-color:#FE2C55; }
        """)
        self._name_edit.returnPressed.connect(self._on_identity_confirm)
        idf.addWidget(self._name_edit)

        idf.addWidget(_lbl("Color", 11, color="#666"))
        colors_row = QHBoxLayout()
        colors_row.setSpacing(6)
        self._color_btns = []
        for color in AVATAR_COLORS:
            cb = QPushButton()
            cb.setFixedSize(28, 28)
            cb.setCursor(Qt.CursorShape.PointingHandCursor)
            cb.setStyleSheet(f"""
                QPushButton {{
                    background:{color}; border:2px solid transparent; border-radius:14px;
                }}
                QPushButton:hover {{ border-color:#fff; }}
            """)
            cb.clicked.connect(lambda _, c=color: self._on_color_pick(c))
            self._color_btns.append(cb)
            colors_row.addWidget(cb)
        colors_row.addStretch()
        idf.addLayout(colors_row)

        confirm_btn = QPushButton("✔  Update")
        confirm_btn.setFixedHeight(34)
        confirm_btn.setStyleSheet("""
            QPushButton {
                background:#FE2C55; color:#fff; border:none; border-radius:8px;
                font-size:13px; font-weight:700; padding:4px 16px;
            }
            QPushButton:hover { background:#ff4d6a; }
        """)
        confirm_btn.clicked.connect(self._on_identity_confirm)
        idf.addWidget(confirm_btn)
        layout.addWidget(id_frame)

        # Video status summary
        self._tiktok_summary = QLabel("Waiting for players…")
        self._tiktok_summary.setStyleSheet("color:#666;font-size:12px;")
        self._tiktok_summary.setWordWrap(True)
        layout.addWidget(self._tiktok_summary)

        layout.addStretch()

        # Host: start button
        self._start_btn = QPushButton("🎮  Start Game")
        self._start_btn.setProperty("primary", True)
        self._start_btn.setFixedHeight(54)
        self._start_btn.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        self._start_btn.setEnabled(False)
        self._start_btn.setVisible(False)
        self._start_btn.clicked.connect(self.start_game_requested)
        layout.addWidget(self._start_btn)

        # Client: ready button
        self._ready_btn = QPushButton("✔  Ready")
        self._ready_btn.setProperty("secondary", True)
        self._ready_btn.setFixedHeight(54)
        self._ready_btn.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        self._ready_btn.setVisible(False)
        self._ready_btn.clicked.connect(self._toggle_ready)
        layout.addWidget(self._ready_btn)

        self._waiting_lbl = QLabel("Waiting for host to start…")
        self._waiting_lbl.setStyleSheet("color:#555;font-size:13px;")
        self._waiting_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._waiting_lbl.setVisible(False)
        layout.addWidget(self._waiting_lbl)

        return panel

    # ── Public API ────────────────────────────────────────────────────────────

    def setup(
        self,
        room_code: str,
        my_player_id: str,
        is_host: bool,
        display_name: str = "",
        avatar_color: str = "",
    ) -> None:
        self._is_host       = is_host
        self._my_player_id  = my_player_id
        self._ready_state   = False
        if avatar_color:
            self._my_color = avatar_color

        self._lan_code = room_code
        self._room_code_lbl.setText(f"Room  {room_code}")
        self._big_code_lbl.setText(room_code)

        # Pre-fill identity
        self._name_edit.setText(display_name)
        self._update_color_selection(self._my_color)

        # Show correct controls
        self._start_btn.setVisible(is_host)
        self._ready_btn.setVisible(not is_host)
        self._waiting_lbl.setVisible(not is_host)

        self._clear_players()

    def update_players(self, players: list[Player]) -> None:
        self._players = list(players)
        self._rebuild_player_list()
        self._update_start_eligibility()

    def _rebuild_player_list(self) -> None:
        # Clear existing cards
        self._clear_players()

        for p in self._players:
            show_kick = self._is_host and p.player_id != self._my_player_id
            card = PlayerCard(p, show_kick=show_kick)
            card.kick_requested.connect(self.kick_player_requested)
            self._players_vbox.insertWidget(
                self._players_vbox.count() - 1, card
            )
            self._cards[p.player_id] = card

        n = len(self._players)
        self._player_count_lbl.setText(f"Players  {n} / 8")

        videos_ok = sum(1 for p in self._players if p.video_count > 0)
        total_vids = sum(p.video_count for p in self._players)
        if videos_ok == n and n >= 2:
            summary = f"✅ {total_vids} videos loaded — ready to play!"
        elif videos_ok == 0:
            summary = "⚠️ No videos loaded yet.\nImport your TikTok likes first."
        else:
            summary = (
                f"{videos_ok} of {n} players have videos loaded "
                f"({total_vids} total).\n⚠️ Others will use demo videos."
            )
        self._tiktok_summary.setText(summary)

    def _clear_players(self) -> None:
        while self._players_vbox.count() > 1:
            item = self._players_vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cards.clear()

    def _update_start_eligibility(self) -> None:
        if not self._is_host:
            return
        n = len(self._players)
        can_start = n >= 2
        self._start_btn.setEnabled(can_start)
        self._status_lbl.setText(
            "Ready to start!" if can_start
            else f"Need {2 - n} more player(s)"
        )

    def _toggle_ready(self) -> None:
        self._ready_state = not self._ready_state
        if self._ready_state:
            self._ready_btn.setText("✔  Ready  (click to unready)")
            self._ready_btn.setStyleSheet(
                "QPushButton{background:rgba(46,204,113,0.15);border:2px solid #2ECC71;"
                "border-radius:8px;color:#2ECC71;padding:10px 22px;font-size:15px;"
                "font-weight:700;}"
                "QPushButton:hover{background:rgba(46,204,113,0.25);}"
            )
        else:
            self._ready_btn.setText("✔  Ready")
            self._ready_btn.setProperty("secondary", True)
            self._ready_btn.style().unpolish(self._ready_btn)
            self._ready_btn.style().polish(self._ready_btn)
        self.ready_toggled.emit(self._ready_state)

    @staticmethod
    def _make_copy_btn() -> QPushButton:
        btn = QPushButton("📋 Copy")
        btn.setFixedHeight(26)
        btn.setStyleSheet("""
            QPushButton{background:#222;border:1px solid #333;border-radius:6px;
                        color:#aaa;font-size:11px;padding:2px 10px;}
            QPushButton:hover{background:#2a2a2a;color:#fff;}
            QPushButton:disabled{color:#444;}
        """)
        return btn

    def _flash_copy(self, btn: QPushButton) -> None:
        btn.setText("✅ Copied!")
        QTimer.singleShot(2000, lambda: btn.setText("📋 Copy"))

    def _on_copy_lan(self) -> None:
        code = getattr(self, "_lan_code", "")
        if code:
            QApplication.clipboard().setText(code)
            self._flash_copy(self._copy_lan_btn)

    def set_relay_status(self, ok: bool, message: str) -> None:
        if self._relay_badge is None:
            return
        if ok:
            self._relay_badge.setText(message)
            self._relay_badge.setStyleSheet(
                "color:#2ECC71;font-size:10px;background:#0d2a1a;"
                "border:1px solid #1a4a2a;border-radius:6px;padding:4px 8px;"
            )
        else:
            self._relay_badge.setText(message)
            self._relay_badge.setStyleSheet(
                "color:#888;font-size:10px;background:#1a1a1a;"
                "border:1px solid #2a2a2a;border-radius:6px;padding:4px 8px;"
            )

    def set_direct_address(self, ip: str, port: int, is_tailscale: bool = False) -> None:
        """Called by MainWindow with the IP and port right after hosting starts."""
        self._direct_addr = f"{ip}:{port}"
        self._ip_addr_lbl.setText(self._direct_addr)
        self._copy_ip_btn.setEnabled(True)
        if is_tailscale:
            self._ip_type_lbl.setText("Tailscale IP (any network ✅)")
            self._ip_type_lbl.setStyleSheet("color:#2ECC71; font-size:11px;")
            self._ip_hint_lbl.setText("✅ Tailscale detected — share this IP with anyone, anywhere.")
            self._ip_hint_lbl.setStyleSheet("color:#2ECC71; font-size:10px;")
            self._ts_btn.setVisible(False)
        else:
            self._ip_type_lbl.setText("Direct IP (same WiFi only)")
            self._ip_type_lbl.setStyleSheet("color:#555; font-size:11px;")
            self._ip_hint_lbl.setText("⚠️ Same WiFi only — install Tailscale for other networks")
            self._ip_hint_lbl.setStyleSheet("color:#664400; font-size:10px;")

    def _on_copy_ip(self) -> None:
        addr = getattr(self, "_direct_addr", "")
        if addr:
            QApplication.clipboard().setText(addr)
            self._flash_copy(self._copy_ip_btn)

    def _on_color_pick(self, color: str) -> None:
        self._my_color = color
        self._update_color_selection(color)

    def _update_color_selection(self, selected: str) -> None:
        for btn, color in zip(self._color_btns, AVATAR_COLORS):
            is_sel = color == selected
            btn.setStyleSheet(f"""
                QPushButton {{
                    background:{color};
                    border:{("3px solid #fff" if is_sel else "2px solid transparent")};
                    border-radius:14px;
                }}
                QPushButton:hover {{ border-color:#fff; }}
            """)

    def _on_identity_confirm(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            return
        self.identity_changed.emit(name, self._my_color)


def _lbl(text: str, size: int = 13, color: str = "#FFFFFF") -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(QFont("Segoe UI", size))
    lbl.setStyleSheet(f"color:{color};")
    return lbl
