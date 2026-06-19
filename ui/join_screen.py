"""Join game screen – enter a room code and find the host."""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QLineEdit,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from network.discovery import RoomFinder
from utils.config import RELAY_URL


class JoinScreen(QWidget):
    join_found     = pyqtSignal(str, str, int)  # room_code, host_ip, tcp_port
    back_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._finder: RoomFinder | None = None
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        hdr = QWidget()
        hdr.setStyleSheet("background:#0a0a0a;border-bottom:1px solid #1e1e1e;")
        hdr.setFixedHeight(64)
        row = QHBoxLayout(hdr)
        row.setContentsMargins(24, 0, 24, 0)
        back = QPushButton("← Back")
        back.setStyleSheet("background:transparent;border:none;color:#888;font-size:14px;")
        back.clicked.connect(self._on_back)
        row.addWidget(back)
        row.addStretch()
        row.addWidget(_h("Join a Game", 18))
        row.addStretch()
        root.addWidget(hdr)

        # Body
        body = QWidget()
        body.setStyleSheet("background:#0e0e0e;")
        b_layout = QVBoxLayout(body)
        b_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setFixedWidth(440)
        card.setStyleSheet(
            "QFrame{background:#161616;border:1px solid #2a2a2a;border-radius:18px;}"
        )
        c = QVBoxLayout(card)
        c.setContentsMargins(40, 40, 40, 40)
        c.setSpacing(20)

        c.addWidget(_h("Join a Room", 20))

        # ── Shared room code input ────────────────────────────────────────────
        self._code_input = QLineEdit()
        self._code_input.setPlaceholderText("Room code — e.g. X7KD92")
        self._code_input.setFixedHeight(52)
        self._code_input.setFont(QFont("Courier New", 20, QFont.Weight.Bold))
        self._code_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._code_input.setMaxLength(6)
        self._code_input.setStyleSheet(
            "QLineEdit{background:#1a1a1a;border:1px solid #333;border-radius:8px;"
            "padding:8px 14px;color:#FE2C55;letter-spacing:4px;}"
            "QLineEdit:focus{border-color:#FE2C55;}"
        )
        self._code_input.textChanged.connect(self._on_code_changed)
        self._code_input.returnPressed.connect(self._on_join_lan)
        c.addWidget(self._code_input)

        # ── LAN button ───────────────────────────────────────────────────────
        c.addWidget(_lbl("Same WiFi / local network", "#555"))
        self._join_lan_btn = QPushButton("🔍  Find Room (same WiFi)")
        self._join_lan_btn.setProperty("primary", True)
        self._join_lan_btn.setFixedHeight(46)
        self._join_lan_btn.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self._join_lan_btn.setEnabled(False)
        self._join_lan_btn.clicked.connect(self._on_join_lan)
        c.addWidget(self._join_lan_btn)

        # ── Separator ─────────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#2a2a2a; margin:4px 0;")
        c.addWidget(sep)

        if RELAY_URL:
            # ── Relay section (relay server is configured) ────────────────────
            c.addWidget(_lbl("Different network / different house", "#555"))

            self._join_inet_btn = QPushButton("🌐  Join via Internet  ←  use this one")
            self._join_inet_btn.setFixedHeight(52)
            self._join_inet_btn.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
            self._join_inet_btn.setEnabled(False)
            self._join_inet_btn.setStyleSheet("""
                QPushButton{background:#1a3a2a;border:1px solid #2ECC7144;border-radius:8px;
                            color:#2ECC71;font-weight:700;}
                QPushButton:hover{background:#1a4a2a;border-color:#2ECC71;}
                QPushButton:disabled{background:#1a1a1a;color:#333;border-color:#222;}
            """)
            self._join_inet_btn.clicked.connect(self._on_join_relay)
            c.addWidget(self._join_inet_btn)

            self._ip_input = None  # not used in relay mode

        else:
            # ── Direct IP:PORT section (no relay configured) ──────────────────
            c.addWidget(_lbl("Internet (other network)", "#555"))

            self._ip_input = QLineEdit()
            self._ip_input.setPlaceholderText("IP:PORT — ex: 92.184.1.23:5555")
            self._ip_input.setFixedHeight(46)
            self._ip_input.setFont(QFont("Courier New", 14))
            self._ip_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._ip_input.setStyleSheet(
                "QLineEdit{background:#1a1a1a;border:1px solid #333;border-radius:8px;"
                "padding:8px 14px;color:#25F4EE;}"
                "QLineEdit:focus{border-color:#25F4EE;}"
            )
            self._ip_input.textChanged.connect(self._on_ip_changed)
            self._ip_input.returnPressed.connect(self._on_join_internet)
            c.addWidget(self._ip_input)

            self._join_inet_btn = QPushButton("🌐  Join via Internet")
            self._join_inet_btn.setFixedHeight(46)
            self._join_inet_btn.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
            self._join_inet_btn.setEnabled(False)
            self._join_inet_btn.setStyleSheet("""
                QPushButton{background:#1a3a4a;border:1px solid #25F4EE44;border-radius:8px;
                            color:#25F4EE;font-weight:700;}
                QPushButton:hover{background:#1a4a5a;border-color:#25F4EE;}
                QPushButton:disabled{background:#1a1a1a;color:#333;border-color:#222;}
            """)
            self._join_inet_btn.clicked.connect(self._on_join_internet)
            c.addWidget(self._join_inet_btn)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color:#888;font-size:12px;")
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c.addWidget(self._status_lbl)

        b_layout.addWidget(card)
        root.addWidget(body, 1)

    # ── LAN ──────────────────────────────────────────────────────────────────

    def _on_code_changed(self, text: str) -> None:
        cleaned = text.upper().replace(" ", "")
        if cleaned != text:
            self._code_input.setText(cleaned)
        has_code = len(cleaned) == 6
        self._join_lan_btn.setEnabled(has_code)
        if RELAY_URL:
            self._join_inet_btn.setEnabled(has_code)
        self._status_lbl.setText("")

    def _on_join_lan(self) -> None:
        code = self._code_input.text().strip().upper()
        if len(code) != 6:
            return
        self._set_searching(True, "lan")
        self._finder = RoomFinder(code)
        self._finder.found.connect(lambda ip, port: self._on_found(code, ip, port))
        self._finder.not_found.connect(self._on_not_found)
        self._finder.start()

    # ── Relay join ────────────────────────────────────────────────────────────

    def _on_join_relay(self) -> None:
        code = self._code_input.text().strip().upper()
        if len(code) != 6:
            return
        self._set_searching(True, "inet")
        # Emit "RELAY" as the host_ip — MainWindow will switch GameClient to relay mode
        self.join_found.emit(code, "RELAY", 0)

    # ── Direct IP:PORT join (no relay) ────────────────────────────────────────

    def _on_ip_changed(self, text: str) -> None:
        parts = text.strip().split(":")
        ok = len(parts) == 2 and parts[1].isdigit() and "." in parts[0]
        self._join_inet_btn.setEnabled(ok)
        self._status_lbl.setText("")

    def _on_join_internet(self) -> None:
        raw = self._ip_input.text().strip()
        parts = raw.split(":")
        if len(parts) != 2 or not parts[1].isdigit():
            self._status_lbl.setText("❌ Invalid format — use IP:PORT")
            self._status_lbl.setStyleSheet("color:#FE2C55;font-size:12px;")
            return
        host_ip = parts[0]
        port    = int(parts[1])
        self._set_searching(True, "inet")
        self.join_found.emit("INET00", host_ip, port)

    def on_inet_failed(self, reason: str) -> None:
        """Called by MainWindow when the connection attempt fails."""
        self._set_searching(False, "inet")
        self._status_lbl.setText(f"❌ {reason}")
        self._status_lbl.setStyleSheet("color:#FE2C55;font-size:12px;")

    # ── Shared ────────────────────────────────────────────────────────────────

    def _on_found(self, code: str, host_ip: str, port: int) -> None:
        self._set_searching(False, "lan")
        self.join_found.emit(code, host_ip, port)

    def _on_not_found(self) -> None:
        self._set_searching(False, "lan")
        self._status_lbl.setText("❌ Room not found. Check the code and try again.")
        self._status_lbl.setStyleSheet("color:#FE2C55;font-size:12px;")

    def _set_searching(self, searching: bool, mode: str = "lan") -> None:
        self._join_lan_btn.setEnabled(not searching)
        self._code_input.setEnabled(not searching)
        if self._ip_input:
            self._ip_input.setEnabled(not searching)

        if searching and mode == "lan":
            self._join_lan_btn.setText("Searching…")
            self._status_lbl.setStyleSheet("color:#888;font-size:12px;")
            self._status_lbl.setText("Searching on local network…")
        elif searching and mode == "inet":
            self._join_inet_btn.setText("Connecting…")
            self._join_inet_btn.setEnabled(False)
            self._status_lbl.setStyleSheet("color:#888;font-size:12px;")
            self._status_lbl.setText("Connecting…")
        elif not searching:
            self._join_lan_btn.setText("🔍  Find Room (same WiFi)")
            self._join_inet_btn.setText("🌐  Join via Internet  ←  use this one" if RELAY_URL else "🌐  Join via Internet")
            code = self._code_input.text().strip().upper()
            has_code = len(code) == 6
            self._join_lan_btn.setEnabled(has_code)
            if RELAY_URL:
                self._join_inet_btn.setEnabled(has_code)
            else:
                # Re-enable based on IP:PORT validity
                if self._ip_input:
                    self._on_ip_changed(self._ip_input.text())
            self._status_lbl.setText("")

    def _on_back(self) -> None:
        if self._finder and self._finder.isRunning():
            self._finder.terminate()
        self.back_requested.emit()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._code_input.clear()
        if self._ip_input:
            self._ip_input.clear()
        self._status_lbl.setText("")
        self._join_lan_btn.setEnabled(False)
        self._join_inet_btn.setEnabled(False)
        self._code_input.setFocus()


def _h(text: str, size: int = 14) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(QFont("Segoe UI", size, QFont.Weight.Bold))
    return lbl


def _lbl(text: str, color: str = "#888") -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(QFont("Segoe UI", 11))
    lbl.setStyleSheet(f"color:{color};")
    return lbl
