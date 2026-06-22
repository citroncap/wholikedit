"""TCP host server – manages connected clients and relays game events."""
from __future__ import annotations
import logging
import socket
import threading
from typing import Optional
from PyQt6.QtCore import QThread, pyqtSignal
from network.protocol import (
    MessageReader, encode,
    MSG_JOIN_REQUEST, MSG_VIDEO_SYNC, MSG_PLAYER_READY,
    MSG_ANSWER, MSG_VIDEO_READY, MSG_PING,
    MSG_JOIN_ACCEPT, MSG_JOIN_REJECT, MSG_LOBBY_UPDATE,
    MSG_PLAYER_KICKED, MSG_GAME_START, MSG_ROUND_BEGIN,
    MSG_ROUND_RESULT, MSG_GAME_END, MSG_PONG,
    MSG_YOUR_ROUND, MSG_IDENTITY_UPDATE, MSG_PLAY_VIDEO,
)
from utils.config import TCP_PORT_RANGE, MAX_PLAYERS, RELAY_URL

log = logging.getLogger(__name__)


class _ClientConn:
    """Thin wrapper around a single client socket."""

    def __init__(self, sock: socket.socket, addr: tuple) -> None:
        self.sock   = sock
        self.addr   = addr
        self.reader = MessageReader()

    def send(self, msg: dict) -> bool:
        try:
            self.sock.sendall(encode(msg))
            return True
        except Exception:
            return False

    def close(self) -> None:
        try:
            self.sock.close()
        except Exception:
            pass


class GameHost(QThread):
    """Runs a TCP server; one thread per connected client.

    All signals are emitted on the main thread via Qt's cross-thread mechanism.
    """

    # ── Signals ───────────────────────────────────────────────────────────────
    client_joined       = pyqtSignal(dict)          # Player.to_dict()
    client_left         = pyqtSignal(str)           # player_id
    video_sync_received = pyqtSignal(str, list)     # player_id, [video dict]
    ready_changed       = pyqtSignal(str, bool)     # player_id, ready
    answer_received     = pyqtSignal(str, str, int) # player_id, guessed_player_id, elapsed_ms
    client_video_ready  = pyqtSignal(str)           # player_id
    identity_updated    = pyqtSignal(str, str, str) # player_id, display_name, avatar_color
    error_occurred      = pyqtSignal(str)
    relay_status        = pyqtSignal(bool, str)     # ok, message

    def __init__(self) -> None:
        super().__init__()
        self._server:       Optional[socket.socket] = None
        self._clients:      dict[str, _ClientConn]  = {}  # player_id → conn
        self._relay_socks:  list[socket.socket]     = []  # pending relay slots
        self._lock          = threading.Lock()
        self._running       = False
        self._port          = 0

    @property
    def port(self) -> int:
        return self._port

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start_server(self) -> int:
        """Bind and start listening. Returns the bound port."""
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # Pick a free port from the configured range
        low, high = TCP_PORT_RANGE
        for candidate in range(low, high):
            try:
                self._server.bind(("0.0.0.0", candidate))
                self._port = candidate
                break
            except OSError:
                continue
        else:
            # Fallback: let OS choose
            self._server.bind(("0.0.0.0", 0))
            self._port = self._server.getsockname()[1]

        self._server.listen(MAX_PLAYERS)
        self._running = True
        self.start()  # Start QThread accept loop
        log.info("Host server listening on port %d", self._port)
        return self._port

    def open_relay_slots(self, room_code: str) -> None:
        """Open MAX_PLAYERS-1 WebSocket relay slots so friends can join from any network."""
        if not RELAY_URL:
            return
        # One coordinator thread manages all slots and emits the relay_status signal
        t = threading.Thread(
            target=self._relay_coordinator,
            args=(room_code,),
            daemon=True,
        )
        t.start()

    def _relay_coordinator(self, room_code: str) -> None:
        """Connect to relay (70s timeout covers Render cold-start) then open per-slot threads."""
        from network.relay import relay_connect_host

        self.relay_status.emit(False, "⏳ Relay waking up… (may take ~60s first time)")

        _registered = threading.Event()

        def _on_registered():
            # Relay confirmed slot 0 is open — update UI and open remaining slots
            self.relay_status.emit(True, "✅ Relay ready — friends can join with the room code")
            _registered.set()
            for slot in range(1, MAX_PLAYERS - 1):
                t = threading.Thread(
                    target=self._open_relay_slot,
                    args=(room_code, slot),
                    daemon=True,
                )
                t.start()
            log.info("Relay slots open for room %s → %s", room_code, RELAY_URL)

        _err: list[str] = []
        probe = relay_connect_host(room_code, 0, on_registered=_on_registered, _err=_err)

        if probe is None:
            if not _registered.is_set():
                detail = f"\n{_err[0]}" if _err else ""
                self.relay_status.emit(False, f"⚠️ Relay offline — internet play unavailable{detail}")
            return

        self._start_slot_thread(room_code, 0, probe)

    def _start_slot_thread(self, room_code: str, slot: int, stream) -> None:
        t = threading.Thread(
            target=self._run_slot,
            args=(stream, slot),
            daemon=True,
        )
        t.start()

    def _open_relay_slot(self, room_code: str, slot: int) -> None:
        from network.relay import relay_connect_host
        stream = relay_connect_host(room_code, slot)
        if stream is not None:
            self._run_slot(stream, slot)

    def _run_slot(self, stream, slot: int) -> None:
        with self._lock:
            self._relay_socks.append(stream)
        try:
            conn = _ClientConn(stream, (RELAY_URL, slot))
            self._client_loop(conn)
        except Exception as exc:
            log.debug("Relay slot %d error: %s", slot, exc)
        finally:
            with self._lock:
                try:
                    self._relay_socks.remove(stream)
                except ValueError:
                    pass
            stream.close()

    def stop(self) -> None:
        self._running = False
        if self._server:
            try:
                self._server.close()
            except Exception:
                pass
        with self._lock:
            for conn in list(self._clients.values()):
                conn.close()
            self._clients.clear()
            for stream in self._relay_socks:
                try:
                    stream.close()
                except Exception:
                    pass
            self._relay_socks.clear()

    # ── Accept loop (QThread.run) ─────────────────────────────────────────────

    def run(self) -> None:
        self._server.settimeout(1.0)
        while self._running:
            try:
                sock, addr = self._server.accept()
                sock.settimeout(60.0)
                conn = _ClientConn(sock, addr)
                t = threading.Thread(
                    target=self._client_loop,
                    args=(conn,),
                    daemon=True,
                )
                t.start()
            except socket.timeout:
                continue
            except OSError:
                break

    # ── Per-client receive loop ───────────────────────────────────────────────

    def _client_loop(self, conn: _ClientConn) -> None:
        player_id: Optional[str] = None
        try:
            while self._running:
                try:
                    data = conn.sock.recv(8192)
                except socket.timeout:
                    continue
                if not data:
                    break
                for msg in conn.reader.feed(data):
                    player_id = self._dispatch(msg, conn, player_id)
        except Exception as exc:
            log.debug("Client loop error (%s): %s", conn.addr, exc)
        finally:
            conn.close()
            if player_id:
                with self._lock:
                    self._clients.pop(player_id, None)
                self.client_left.emit(player_id)
                log.info("Player disconnected: %s", player_id)

    def _dispatch(
        self, msg: dict, conn: _ClientConn, player_id: Optional[str]
    ) -> Optional[str]:
        mtype = msg.get("type")

        if mtype == MSG_JOIN_REQUEST:
            return self._handle_join(msg, conn)

        if player_id is None:
            return None  # Not yet joined – ignore other messages

        if mtype == MSG_VIDEO_SYNC:
            self.video_sync_received.emit(player_id, msg.get("videos", []))

        elif mtype == MSG_PLAYER_READY:
            self.ready_changed.emit(player_id, bool(msg.get("ready", False)))

        elif mtype == MSG_ANSWER:
            guessed = msg.get("guessed_player_id", "")
            elapsed = int(msg.get("elapsed_ms", 0))
            self.answer_received.emit(player_id, guessed, elapsed)

        elif mtype == MSG_VIDEO_READY:
            self.client_video_ready.emit(player_id)

        elif mtype == MSG_IDENTITY_UPDATE:
            self.identity_updated.emit(
                player_id,
                msg.get("display_name", ""),
                msg.get("avatar_color", ""),
            )

        elif mtype == MSG_PING:
            conn.send({"type": MSG_PONG})

        return player_id

    def _handle_join(self, msg: dict, conn: _ClientConn) -> Optional[str]:
        pid   = msg.get("player_id", "")
        name  = msg.get("display_name", "Player")[:20]
        color = msg.get("avatar_color", "#FE2C55")

        with self._lock:
            if len(self._clients) >= MAX_PLAYERS:
                conn.send({"type": MSG_JOIN_REJECT, "reason": "Room is full."})
                conn.close()
                return None
            self._clients[pid] = conn

        player_dict = {
            "player_id":         pid,
            "display_name":      name,
            "avatar_color":      color,
            "is_host":           False,
            "is_ready":          False,
            "tiktok_connected":  msg.get("tiktok_connected", False),
            "tiktok_username":   msg.get("tiktok_username"),
            "video_count":       0,
        }
        self.client_joined.emit(player_dict)
        log.info("Player joined: %s (%s)", name, pid)
        return pid

    # ── Outbound helpers ──────────────────────────────────────────────────────

    def accept_player(self, player_id: str, all_players: list[dict], settings: dict) -> None:
        self._send_to(player_id, {
            "type":          MSG_JOIN_ACCEPT,
            "your_player_id": player_id,
            "players":       all_players,
            "settings":      settings,
        })

    def broadcast_lobby(self, players: list[dict]) -> None:
        self.broadcast({"type": MSG_LOBBY_UPDATE, "players": players})

    def kick_player(self, player_id: str) -> None:
        self._send_to(player_id, {"type": MSG_PLAYER_KICKED})
        with self._lock:
            conn = self._clients.pop(player_id, None)
        if conn:
            conn.close()

    def broadcast_game_start(self, settings: dict) -> None:
        self.broadcast({"type": MSG_GAME_START, "settings": settings})

    def broadcast_round_begin(
        self, round_number: int, total_rounds: int, video_dict: dict
    ) -> None:
        self.broadcast({
            "type":         MSG_ROUND_BEGIN,
            "round_number": round_number,
            "total_rounds": total_rounds,
            "video":        video_dict,
        })

    def broadcast_round_result(
        self,
        round_number: int,
        correct_player_id: str,
        correct_display_name: str,
        answers: list[dict],
        scores: dict[str, int],
    ) -> None:
        self.broadcast({
            "type":                 MSG_ROUND_RESULT,
            "round_number":         round_number,
            "correct_player_id":    correct_player_id,
            "correct_display_name": correct_display_name,
            "answers":              answers,
            "scores":               scores,
        })

    def send_your_round(self, player_id: str) -> None:
        self._send_to(player_id, {"type": MSG_YOUR_ROUND})

    def broadcast_play_video(self) -> None:
        self.broadcast({"type": MSG_PLAY_VIDEO})

    def broadcast_game_end(self, leaderboard: list[dict]) -> None:
        self.broadcast({"type": MSG_GAME_END, "leaderboard": leaderboard})

    def broadcast(self, msg: dict) -> None:
        with self._lock:
            conns = list(self._clients.items())
        for pid, conn in conns:
            if not conn.send(msg):
                log.debug("Failed to send to %s", pid)

    def _send_to(self, player_id: str, msg: dict) -> None:
        with self._lock:
            conn = self._clients.get(player_id)
        if conn:
            conn.send(msg)
