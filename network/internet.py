"""Network helpers — local IP and Tailscale detection."""
from __future__ import annotations
import socket
import subprocess
from typing import Optional


def get_local_ip() -> str:
    """Return this machine's LAN IP (instant, no network traffic)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def get_tailscale_ip() -> Optional[str]:
    """Return the Tailscale IPv4 (100.x.x.x) if installed and connected."""
    try:
        r = subprocess.run(
            ["tailscale", "ip", "-4"],
            capture_output=True, text=True, timeout=2,
            creationflags=0x08000000,  # CREATE_NO_WINDOW on Windows
        )
        ip = r.stdout.strip()
        if r.returncode == 0 and ip.startswith("100."):
            return ip
    except Exception:
        pass
    return None
