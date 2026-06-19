"""WebSocket relay helpers — shared by GameHost and GameClient."""
from __future__ import annotations
import json
import socket
import logging
from typing import Optional

log = logging.getLogger(__name__)


class _WsStream:
    """Wraps a synchronous WebSocket connection as a byte-stream socket.

    Exposes recv(n) / sendall(data) / settimeout(t) / close() so the existing
    game-protocol code (which expects a socket-like object) works unchanged.
    WebSocket frames are fetched one at a time and buffered; recv(n) returns
    up to n bytes immediately once any bytes are available.
    """

    def __init__(self, ws) -> None:
        self._ws      = ws
        self._buf     = bytearray()
        self._timeout: Optional[float] = 60.0

    def settimeout(self, t: Optional[float]) -> None:
        self._timeout = t

    def recv(self, n: int) -> bytes:
        if not self._buf:
            try:
                chunk = self._ws.recv(timeout=self._timeout)
            except TimeoutError:
                raise socket.timeout()
            except Exception:
                return b""
            if isinstance(chunk, str):
                chunk = chunk.encode()
            self._buf.extend(chunk)
        data = bytes(self._buf[:n])
        del self._buf[:n]
        return data

    def sendall(self, data: bytes) -> None:
        self._ws.send(data)

    def close(self) -> None:
        try:
            self._ws.close()
        except Exception:
            pass


def relay_connect_host(room_code: str, slot: int, on_registered=None, _err: list | None = None):
    """Open a host relay slot and block until a joiner arrives.

    on_registered(): called as soon as the relay confirms the slot is open,
    before any joiner arrives — use it to update the lobby status.

    Returns a _WsStream ready for game traffic, or None on failure.
    open_timeout=70 gives Render's free tier enough time to cold-start (~60s).

    Supports two server protocols:
      New: server sends {"registered": true} immediately, then {"ok": true} on pair.
      Old: server blocks and sends {"ok": true} only when joiner arrives.
    """
    from utils.config import RELAY_URL
    import websockets.sync.client

    try:
        ws = websockets.sync.client.connect(RELAY_URL, open_timeout=70)
        ws.send(json.dumps({"role": "host", "code": room_code, "slot": slot}))

        raw = ws.recv()
        resp = json.loads(raw)

        if resp.get("registered"):
            # New two-message protocol: immediate ack, then wait for joiner
            if on_registered:
                on_registered()
            raw = ws.recv()
            resp = json.loads(raw)
            if not resp.get("ok"):
                ws.close()
                return None
        elif resp.get("ok"):
            # Old single-message protocol: server blocked until joiner arrived
            if on_registered:
                on_registered()
        else:
            log.info("Relay slot %d unexpected first message: %s", slot, resp)
            ws.close()
            return None

        stream = _WsStream(ws)
        stream.settimeout(60.0)
        return stream
    except Exception as exc:
        log.info("Relay host slot %d failed: %s", slot, exc)
        if _err is not None:
            _err.append(str(exc))
        return None


def relay_connect_join(room_code: str):
    """Join a relay room.
    Returns a _WsStream ready for game traffic, or (None, error_message) on failure.
    """
    from utils.config import RELAY_URL
    import websockets.sync.client

    try:
        ws = websockets.sync.client.connect(RELAY_URL, open_timeout=70)
        ws.send(json.dumps({"role": "join", "code": room_code}))
        raw = ws.recv()
        resp = json.loads(raw)
        if not resp.get("ok"):
            ws.close()
            return None, resp.get("error", "Room not found. Make sure the host has started.")
        stream = _WsStream(ws)
        stream.settimeout(60.0)
        return stream, None
    except Exception as exc:
        return None, f"Could not reach relay: {exc}"
