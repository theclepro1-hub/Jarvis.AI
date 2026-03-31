from __future__ import annotations

import argparse
import functools
import socket
import sys
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PORT = 8765


class PrototypeHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str | None = None, **kwargs):
        super().__init__(*args, directory=directory or str(ROOT), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        sys.stdout.write(f"[http] {self.address_string()} - {fmt % args}\n")


def find_port(preferred: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            probe.bind(("127.0.0.1", 0))
            return int(probe.getsockname()[1])


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the JARVIS NEXT prototype locally.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Preferred local port.")
    parser.add_argument("--no-open", action="store_true", help="Do not open the browser automatically.")
    args = parser.parse_args()

    port = find_port(args.port)
    url = f"http://127.0.0.1:{port}/next_core/prototype_web/index.html"

    handler = functools.partial(PrototypeHandler, directory=str(ROOT))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)

    print("JARVIS NEXT prototype server is live.")
    print(f"Root: {ROOT}")
    print(f"URL:  {url}")
    print("Press Ctrl+C to stop.")

    if not args.no_open:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping prototype server...")
    finally:
        server.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
