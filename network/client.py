"""TCP game client – connects to the host server."""
from __future__ import annotations
import logging
import socket
from collections import deque
from typing import Optional
from PyQt6.QtCore import QThread, pyqtSignal
from network.protocol import (
    MessageReader, encode,
    MSG_JOIN_REQUEST, MSG_VIDEO_SYNC, MSG_PLAYER_READY,
    MSG_ANSWER, MSG_PING,
    MSG_JOIN_ACCEPT, MSG_JOIN_REJECT, MSG_LOBBY_UPDATE,
    MSG_PLAYER_KICKED, MSG_GAME_START, MSG_ROUND_BEGIN,
    MSG_ROUND_RESULT, MSG_GAME_END, MSG_PONG,
)

log = logging.getLogger(__name__)


class GameClient(QThread):
    """Connects to a host and receives game events via signals."""

    # ── Signals ───────────────────────────────────────────────────────────────
    join_accepted    = pyqtSignal(dict)   # {your_player_id, players, settings}
    join_rejected    = pyqtSignal(str)    # reason
    lobby_updated    = pyqtSignal(list)   # [Player dict]
    kicked           = pyqtSignal()
    game_started     = pyqtSignal(dict)   # settings dict
    round_begun      = pyqtSignal(dict)   # {round_number, total_rounds, video}
    round_result     = pyqtSignal(dict)   # full result dict
    game_ended       = pyqtSignal(list)   # [LeaderboardEntry dict]
    connection_lost  = pyqtSignal(str)    # reason

    def __init__(self) -> None:
        super().__init__()
        self._sock:       Optional[socket.socket] = None
        self._running     = False
        self._host_ip     = ""
        self._host_port   = 0
        self._relay_code  = ""   # non-empty → connect via relay instead of direct
        # Queued outbound messages (deque for O(1) popleft)
        self._send_queue: deque[dict] = deque()

        # Join parameters (set before start())
        self.player_id:        str = ""
        self.display_name:     str = ""
        self.avatar_color:     str = ""
        self.tiktok_connected: bool = False
        self.tiktok_username:  Optional[str] = None

    # ── Public API ────────────────────────────────────────────────────────────

    def connect_to(self, host_ip: str, port: int) -> None:
        self._host_ip   = host_ip
        self._host_port = port

    def use_relay(self, room_code: str) -> None:
        """Switch to relay mode: connect via the relay server instead of directly."""
        self._relay_code = room_code

    def send_video_sync(self, videos: list[dict]) -> None:
        self._queue({"type": MSG_VIDEO_SYNC, "videos": videos})

    def send_ready(self, ready: bool) -> None:
        self._queue({"type": MSG_PLAYER_READY, "ready": ready})

    def send_answer(self, guessed_player_id: str, elapsed_ms: int) -> None:
        self._queue({"type": MSG_ANSWER,
                     "guessed_player_id": guessed_player_id,
                     "elapsed_ms": elapsed_ms})

    def disconnect(self) -> None:
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass

    # ── QThread.run ───────────────────────────────────────────────────────────

    def run(self) -> None:
        try:
            if self._relay_code:
                stream, err = self._connect_via_relay()
                if err:
                    self.connection_lost.emit(err)
                    return
                self._sock = stream
            else:
                self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._sock.settimeout(10.0)
                self._sock.connect((self._host_ip, self._host_port))
                self._sock.settimeout(60.0)
            self._running = True

            # Send join request immediately
            self._flush({
                "type":             MSG_JOIN_REQUEST,
                "player_id":        self.player_id,
                "display_name":     self.display_name,
                "avatar_color":     self.avatar_color,
                "tiktok_connected": self.tiktok_connected,
                "tiktok_username":  self.tiktok_username,
            })

            reader = MessageReader()
            while self._running:
                # Flush queued outbound messages
                while self._send_queue:
                    self._flush(self._send_queue.popleft())

                try:
                    data = self._sock.recv(65536)
                except socket.timeout:
                    continue
                if not data:
                    break

                for msg in reader.feed(data):
                    self._dispatch(msg)

        except ConnectionRefusedError:
            self.connection_lost.emit("Connection refused. Host may not be running.")
        except socket.timeout:
            self.connection_lost.emit("Connection timed out.")
        except OSError as exc:
            if self._running:  # Not a deliberate disconnect
                self.connection_lost.emit(str(exc))
        finally:
            self._running = False
            if self._sock:
                try:
                    self._sock.close()
                except Exception:
                    pass

    # ── Dispatch ─────────────────────────────────────────────────────────────

    def _dispatch(self, msg: dict) -> None:
        mtype = msg.get("type")
        if   mtype == MSG_JOIN_ACCEPT:  self.join_accepted.emit(msg)
        elif mtype == MSG_JOIN_REJECT:  self.join_rejected.emit(msg.get("reason", "Rejected"))
        elif mtype == MSG_LOBBY_UPDATE: self.lobby_updated.emit(msg.get("players", []))
        elif mtype == MSG_PLAYER_KICKED:self.kicked.emit()
        elif mtype == MSG_GAME_START:   self.game_started.emit(msg.get("settings", {}))
        elif mtype == MSG_ROUND_BEGIN:  self.round_begun.emit(msg)
        elif mtype == MSG_ROUND_RESULT: self.round_result.emit(msg)
        elif mtype == MSG_GAME_END:     self.game_ended.emit(msg.get("leaderboard", []))
        elif mtype == MSG_PONG:         pass

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _connect_via_relay(self):
        """Connect to the relay via WebSocket. Returns (stream, None) or (None, error_str)."""
        from network.relay import relay_connect_join
        return relay_connect_join(self._relay_code)

    def _queue(self, msg: dict) -> None:
        if self._running:
            self._send_queue.append(msg)  # deque.append is thread-safe under GIL

    def _flush(self, msg: dict) -> None:
        if self._sock:
            try:
                self._sock.sendall(encode(msg))
            except Exception as exc:
                log.error("Send failed: %s", exc)
