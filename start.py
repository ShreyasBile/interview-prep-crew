"""Start Interview Prep Crew and open it in the browser.

    python start.py [--port 8010] [--no-browser]

Port 8010 is used unless PORT is set in .env or --port is given. If the port is taken,
the next free one is used. If Interview Prep Crew itself is already running on it, the
browser is opened on that copy instead of starting a second server.
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Callable

import httpx

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import app.config  # noqa: E402,F401  (loads .env before PORT is read)

HOST = "127.0.0.1"
PORT_ATTEMPTS = 20


def is_this_app(port: int) -> bool:
    """True if the server on this port is Interview Prep Crew."""
    try:
        resp = httpx.get(f"http://{HOST}:{port}/api/config", timeout=2.0)
        return resp.status_code == 200 and "agents" in resp.json()
    except (httpx.HTTPError, ValueError):
        return False


def bind(port: int) -> socket.socket | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows: stop other sockets sharing the port
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        sock.bind((HOST, port))
    except OSError:  # in use, or reserved by Windows
        sock.close()
        return None
    return sock


def find_port(
    start: int, attempts: int = PORT_ATTEMPTS, is_ours: Callable[[int], bool] = is_this_app
) -> tuple[socket.socket | None, int]:
    """Bind the first free port from `start` on.

    Returns (socket, port) for a free port, or (None, port) when this app is already
    running on that port. Raises RuntimeError when nothing in the range is usable.
    """
    for port in range(start, start + attempts):
        sock = bind(port)
        if sock is not None:
            return sock, port
        if is_ours(port):
            return None, port
    raise RuntimeError(f"Ports {start}-{start + attempts - 1} are all in use. Set PORT in .env to another number.")


def open_when_ready(server, url: str) -> None:
    def wait() -> None:
        for _ in range(300):  # up to 30 s for the app to load
            if server.started:
                webbrowser.open(url)
                return
            time.sleep(0.1)

    threading.Thread(target=wait, daemon=True).start()


def main() -> int:
    parser = argparse.ArgumentParser(description="Start Interview Prep Crew")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8010")))
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    args = parser.parse_args()

    try:
        sock, port = find_port(args.port)
    except RuntimeError as exc:
        print(exc, flush=True)
        return 1
    url = f"http://{HOST}:{port}"

    if sock is None:
        print(f"Interview Prep Crew is already running at {url}", flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        return 0
    if port != args.port:
        print(f"Port {args.port} is in use, so using port {port} instead.", flush=True)

    import uvicorn

    from app.main import app

    server = uvicorn.Server(uvicorn.Config(app, log_level="info"))
    print(f"Interview Prep Crew: {url}  (close this window to stop it)", flush=True)
    if not args.no_browser:
        open_when_ready(server, url)
    server.run(sockets=[sock])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
