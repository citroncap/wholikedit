"""
WhoLikedIt relay server — aiohttp WebSocket edition.

Works on Render.com free tier (HTTPS web service):
  Build command: pip install aiohttp
  Start command: python relay_server.py

Render's health checks send HEAD / — aiohttp handles that transparently.

Protocol (unchanged from client's perspective):
  HOST sends: {"role": "host", "code": "ABC123", "slot": 0}
  JOINER sends: {"role": "join", "code": "ABC123"}
  After pairing, server sends {"ok": true} to both, then raw bytes flow.
"""
import asyncio
import json
import logging
import os
from collections import defaultdict

from aiohttp import web, WSMsgType

log = logging.getLogger(__name__)
PORT = int(os.getenv("PORT", 8888))

_SENTINEL = object()


class _Slot:
    """Queue-based bridge between two WebSocket handlers."""
    def __init__(self):
        self.h2j: asyncio.Queue = asyncio.Queue()
        self.j2h: asyncio.Queue = asyncio.Queue()
        self.ready = asyncio.Event()


# slot_key ("CODE:0") → asyncio.Queue of _Slot
_slots: dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)


async def _drain(src_ws, queue: asyncio.Queue) -> None:
    """Read frames from a WebSocket and put them into a queue."""
    try:
        async for msg in src_ws:
            if msg.type in (WSMsgType.TEXT, WSMsgType.BINARY):
                await queue.put(msg)
            else:
                break
    except Exception:
        pass
    finally:
        await queue.put(_SENTINEL)


async def _fill(queue: asyncio.Queue, dst_ws) -> None:
    """Read from a queue and forward frames to a WebSocket."""
    try:
        while True:
            item = await queue.get()
            if item is _SENTINEL:
                break
            if item.type == WSMsgType.TEXT:
                await dst_ws.send_str(item.data)
            elif item.type == WSMsgType.BINARY:
                await dst_ws.send_bytes(item.data)
    except Exception:
        pass


async def _handle(request: web.Request) -> web.StreamResponse:
    # Render health checks: HEAD / or GET / without WebSocket upgrade
    if request.headers.get("Upgrade", "").lower() != "websocket":
        return web.Response(text="WhoLikedIt relay OK")

    ws = web.WebSocketResponse()
    await ws.prepare(request)
    addr = request.remote or "?"

    try:
        first = await asyncio.wait_for(ws.receive(), timeout=15)
        if first.type != WSMsgType.TEXT:
            return ws

        data = json.loads(first.data)
        role = data.get("role")
        code = data.get("code", "").strip().upper()

        if role == "host":
            slot_num = int(data.get("slot", 0))
            key = f"{code}:{slot_num}"
            s = _Slot()
            await _slots[key].put(s)
            log.info("Host slot ready: %s  peer=%s", key, addr)
            # Immediately acknowledge so the host client knows the relay is up
            await ws.send_str(json.dumps({"registered": True}))

            try:
                await asyncio.wait_for(s.ready.wait(), timeout=3600)
            except asyncio.TimeoutError:
                try:
                    _slots[key].get_nowait()
                except Exception:
                    pass
                return ws

            # Joiner arrived — notify host client, then pipe via queues
            await ws.send_str(json.dumps({"ok": True}))
            await asyncio.gather(
                _drain(ws, s.h2j),
                _fill(s.j2h, ws),
            )

        elif role == "join":
            for key in list(_slots.keys()):
                if not key.startswith(code + ":"):
                    continue
                q = _slots[key]
                if q.empty():
                    continue
                s: _Slot = await q.get()
                if q.empty():
                    _slots.pop(key, None)
                s.ready.set()
                log.info("Paired joiner  peer=%s  slot=%s", addr, key)
                await ws.send_str(json.dumps({"ok": True}))
                await asyncio.gather(
                    _drain(ws, s.j2h),
                    _fill(s.h2j, ws),
                )
                return ws

            await ws.send_str(json.dumps({"ok": False, "error": "Room not found"}))
            log.info("No slot for code=%s  peer=%s", code, addr)

    except asyncio.TimeoutError:
        log.debug("Timeout  peer=%s", addr)
    except Exception as exc:
        log.debug("Error  peer=%s: %s", addr, exc)

    return ws


async def _main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
    )
    app = web.Application()
    app.router.add_route("*", "/", _handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    log.info("WhoLikedIt relay listening on port %d (aiohttp)", PORT)
    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(_main())
