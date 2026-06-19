"""UDP-based room discovery for LAN play.

Host: broadcasts {type, code, port, host_name} every DISCOVERY_INTERVAL seconds.
      Also listens for directed queries and responds immediately.

Client: sends a broadcast query {type, code}, waits for a response,
        resolves the host's IP + TCP port.
"""
from __future__ import annotations
import json
import logging
import socket
import threading
import time
from PyQt6.QtCore import QThread, pyqtSignal
from utils.config import DISCOVERY_PORT, DISCOVERY_INTERVAL, DISCOVERY_TIMEOUT

log = logging.getLogger(__name__)

_MSG_ANNOUNCE  = "host_announce"
_MSG_QUERY     = "client_query"
_MSG_RESPONSE  = "host_response"
BROADCAST_ADDR = "255.255.255.255"


def _udp_socket() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    return sock


class RoomBroadcaster(threading.Thread):
    """Background thread: broadcasts room presence via UDP and answers queries."""

    def __init__(self, room_code: str, tcp_port: int, host_name: str) -> None:
        super().__init__(daemon=True)
        self._code      = room_code.upper()
        self._tcp_port  = tcp_port
        self._host_name = host_name
        self._running   = False

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        self._running = True
        sock = _udp_socket()
        try:
            sock.bind(("", DISCOVERY_PORT))
        except OSError:
            # Port in use (another room on same machine) – still broadcast
            sock.bind(("", 0))

        sock.settimeout(DISCOVERY_INTERVAL)

        announce = json.dumps({
            "type":      _MSG_ANNOUNCE,
            "code":      self._code,
            "port":      self._tcp_port,
            "host_name": self._host_name,
        }).encode()

        while self._running:
            # Broadcast our presence
            try:
                sock.sendto(announce, (BROADCAST_ADDR, DISCOVERY_PORT))
            except Exception:
                pass

            # Listen for queries during the interval
            deadline = time.monotonic() + DISCOVERY_INTERVAL
            while self._running and time.monotonic() < deadline:
                sock.settimeout(max(0.1, deadline - time.monotonic()))
                try:
                    data, addr = sock.recvfrom(512)
                    msg = json.loads(data.decode())
                    if msg.get("type") == _MSG_QUERY and msg.get("code") == self._code:
                        response = json.dumps({
                            "type": _MSG_RESPONSE,
                            "code": self._code,
                            "port": self._tcp_port,
                        }).encode()
                        sock.sendto(response, addr)
                except socket.timeout:
                    break
                except Exception:
                    break

        sock.close()


class RoomFinder(QThread):
    """Client thread: discovers a room by code via UDP broadcast.

    Signals:
      found(host_ip, tcp_port)
      not_found()
    """
    found     = pyqtSignal(str, int)
    not_found = pyqtSignal()

    def __init__(self, room_code: str) -> None:
        super().__init__()
        self._code = room_code.upper()

    def run(self) -> None:
        sock = _udp_socket()
        sock.settimeout(1.0)
        try:
            sock.bind(("", 0))
        except OSError:
            self.not_found.emit()
            return

        query = json.dumps({"type": _MSG_QUERY, "code": self._code}).encode()
        deadline = time.monotonic() + DISCOVERY_TIMEOUT

        while time.monotonic() < deadline:
            try:
                sock.sendto(query, (BROADCAST_ADDR, DISCOVERY_PORT))
            except Exception:
                pass

            # Wait up to 1 second for response
            sock.settimeout(1.0)
            try:
                while True:
                    data, addr = sock.recvfrom(512)
                    try:
                        msg = json.loads(data.decode())
                        mtype = msg.get("type")
                        code  = msg.get("code", "").upper()

                        if mtype in (_MSG_ANNOUNCE, _MSG_RESPONSE) and code == self._code:
                            port = msg.get("port", 0)
                            if port:
                                sock.close()
                                self.found.emit(addr[0], port)
                                return
                    except (json.JSONDecodeError, KeyError):
                        pass
            except socket.timeout:
                pass

        sock.close()
        self.not_found.emit()
