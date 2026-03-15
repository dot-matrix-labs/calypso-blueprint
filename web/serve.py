#!/usr/bin/env python3
"""
Calypso dev server.
  / → web/index.html
  /* → files under repo root (files only, no directories, no path traversal)
"""
import http.server
import os
import socket
import socketserver
import sys
from urllib.parse import unquote

REPO = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))

MIME = {
    ".html": "text/html; charset=utf-8",
    ".yaml": "text/yaml; charset=utf-8",
    ".yml":  "text/yaml; charset=utf-8",
    ".js":   "text/javascript; charset=utf-8",
    ".css":  "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg":  "image/svg+xml",
    ".png":  "image/png",
    ".ico":  "image/x-icon",
}


def local_ip() -> str:
    """Best-effort: the IP used to reach external networks."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return socket.gethostbyname(socket.gethostname())


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        raw = unquote(self.path.split("?")[0])

        # Root → index
        if raw in ("/", ""):
            raw = "/web/index.html"

        candidate = os.path.realpath(os.path.join(REPO, raw.lstrip("/")))

        # Reject path traversal
        if not candidate.startswith(REPO + os.sep):
            return self._err(403, "Forbidden")

        if not os.path.exists(candidate):
            return self._err(404, "Not Found")

        if os.path.isdir(candidate):
            return self._err(403, "Directory listing not allowed")

        ext = os.path.splitext(candidate)[1].lower()
        ct  = MIME.get(ext, "application/octet-stream")

        try:
            with open(candidate, "rb") as f:
                body = f.read()
        except OSError:
            return self._err(500, "Read error")

        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _err(self, code: int, msg: str):
        body = msg.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        code = str(args[1]) if len(args) > 1 else "?"
        if not code.startswith("2"):
            print(f"  {args[0]}  [{code}]", flush=True)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    ip   = local_ip()

    with socketserver.TCPServer(("0.0.0.0", port), Handler) as httpd:
        port = httpd.server_address[1]
        print()
        print("  Calypso State Machine Visualizer")
        print("  ─────────────────────────────────")
        print(f"  http://localhost:{port}/")
        print(f"  http://{ip}:{port}/")
        print()
        print("  Ctrl+C to stop")
        print()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  Stopped.")


if __name__ == "__main__":
    main()
