"""
WhoLikedIt relay server — WebSocket edition.

Works on Render.com free tier (HTTPS web service):
  Start command: python relay_server.py
  No build command needed.

Protocol:
  HOST connects, sends: {"role": "host", "code": "ABC123", "slot": 0}
  JOINER connects, sends: {"role": "join", "code": "ABC123"}

  Relay pairs joiner with an available host slot.
  After pairing, raw bytes flow both ways as binary WebSocket frames.
  The game protocol (length-prefixed JSON) is transparent to the relay.
"""
import asyncio
import json
import logging
import os
from collections import defaultdict

import websockets

log = logging.getLogger(__name__)
PORT = int(os.getenv("PORT", 8888))

# slot_key ("CODE:0", "CODE:1"…) → queue of (ws, claimed_event)
_slots: dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)


async def _pipe(src, dst) -> None:
    try:
        async for msg in src:
            await dst.send(msg)
    except Exception:
        pass
    finally:
        try:
            await dst.close()
        except Exception:
            pass


async def _handle(ws) -> None:
    addr = ws.remote_address
    try:
        raw = await asyncio.wait_for(ws.recv(), timeout=15)
        data = json.loads(raw)
        role = data["role"]
        code = data["code"].strip().upper()

        if role == "host":
            slot     = int(data.get("slot", 0))
            slot_key = f"{code}:{slot}"
            event    = asyncio.Event()
            await _slots[slot_key].put((ws, event))
            log.info("Host slot ready: %s from %s", slot_key, addr)
            try:
                await asyncio.wait_for(event.wait(), timeout=3600)
            except asyncio.TimeoutError:
                try:
                    _slots[slot_key].get_nowait()
                except Exception:
                    pass
                return
            # Keep coroutine alive while JOIN side handles piping
            await asyncio.sleep(7200)

        elif role == "join":
            for key in list(_slots.keys()):
                if not key.startswith(code + ":"):
                    continue
                q = _slots[key]
                if q.empty():
                    continue
                host_ws, event = await q.get()
                if q.empty():
                    _slots.pop(key, None)
                event.set()
                log.info("Paired joiner %s with slot %s", addr, key)
                # Notify both sides
                await host_ws.send(json.dumps({"ok": True}))
                await ws.send(json.dumps({"ok": True}))
                # Pipe game data transparently
                await asyncio.gather(
                    _pipe(ws, host_ws),
                    _pipe(host_ws, ws),
                )
                return
            await ws.send(json.dumps({"ok": False, "error": "Room not found"}))
            log.info("No slot for code %s (joiner %s)", code, addr)

    except asyncio.TimeoutError:
        log.debug("Timeout from %s", addr)
    except Exception as exc:
        log.debug("Error from %s: %s", addr, exc)


async def _main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
    )
    async with websockets.serve(_handle, "0.0.0.0", PORT):
        log.info("WhoLikedIt relay listening on port %d (WebSocket)", PORT)
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(_main())
