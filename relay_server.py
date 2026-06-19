"""
WhoLikedIt relay server.

Deploy for free on Render.com:
  1. Push this file to a GitHub repo
  2. Create a new "Web Service" on render.com
  3. Build command: pip install -r requirements-relay.txt
  4. Start command: python relay_server.py
  5. Copy the URL (e.g. https://wholikedit-relay.onrender.com)
  6. Put it in utils/config.py → RELAY_HOST / RELAY_PORT

The relay is a transparent TCP bridge:
  HOST sends  "HOST:<code>:<slot>\n"  → waits for a joiner to claim the slot
  JOINER sends "JOIN:<code>\n"        → relay pairs it with an available host slot
  After pairing, raw bytes flow both ways — game protocol unchanged.
"""
import asyncio
import logging
import os
from collections import defaultdict

log = logging.getLogger(__name__)
PORT = int(os.getenv("PORT", 8888))

# slot_key ("CODE:0", "CODE:1"…) → queue of (reader, writer, claimed_event)
_slots: dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)


async def _pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
    try:
        while chunk := await src.read(65536):
            dst.write(chunk)
            await dst.drain()
    except Exception:
        pass
    finally:
        try:
            dst.close()
        except Exception:
            pass


async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    addr = writer.get_extra_info("peername")
    try:
        line = await asyncio.wait_for(reader.readline(), timeout=15)
        cmd, _, rest = line.decode().strip().partition(":")
        code, _, slot_s = rest.partition(":")
        code = code.strip().upper()

        if cmd == "HOST":
            slot_key = f"{code}:{slot_s.strip()}"
            event = asyncio.Event()
            await _slots[slot_key].put((reader, writer, event))
            log.info("Host slot ready: %s from %s", slot_key, addr)
            try:
                await asyncio.wait_for(event.wait(), timeout=3600)
            except asyncio.TimeoutError:
                _slots[slot_key].get_nowait()  # clean up
                return
            # Piping is driven by the JOIN side — just keep this coroutine alive
            await asyncio.sleep(7200)

        elif cmd == "JOIN":
            # Find any free slot for this room code
            for key in list(_slots.keys()):
                if not key.startswith(code + ":"):
                    continue
                q = _slots[key]
                if q.empty():
                    continue
                host_r, host_w, event = await q.get()
                if q.empty():
                    _slots.pop(key, None)
                # Notify both sides before piping starts
                host_w.write(b"OK\n")
                await host_w.drain()
                event.set()
                writer.write(b"OK\n")
                await writer.drain()
                log.info("Paired joiner %s with slot %s", addr, key)
                await asyncio.gather(
                    _pipe(reader, host_w),
                    _pipe(host_r, writer),
                )
                return
            writer.write(b"NO_ROOM\n")
            await writer.drain()
            log.info("No slot for code %s (joiner %s)", code, addr)

    except asyncio.TimeoutError:
        log.debug("Timeout from %s", addr)
    except Exception as exc:
        log.debug("Error from %s: %s", addr, exc)
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def _main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
    )
    srv = await asyncio.start_server(_handle, "0.0.0.0", PORT)
    log.info("WhoLikedIt relay listening on port %d", PORT)
    async with srv:
        await srv.serve_forever()


if __name__ == "__main__":
    asyncio.run(_main())
