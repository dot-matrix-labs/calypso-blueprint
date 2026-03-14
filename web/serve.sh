#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

python3 - <<'EOF'
import http.server, socketserver, os, sys

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # only log non-200s to keep output clean
        code = args[1] if len(args) > 1 else '?'
        if not str(code).startswith('2'):
            print(f"  {args[0]} {code}")

with socketserver.TCPServer(("0.0.0.0", 0), Handler) as httpd:
    port = httpd.server_address[1]
    print(f"")
    print(f"  Calypso State Machine Visualizer")
    print(f"  ─────────────────────────────────")
    print(f"  http://localhost:{port}/web/")
    print(f"  (all interfaces: 0.0.0.0:{port})")
    print(f"")
    print(f"  Ctrl+C to stop")
    print(f"")
    httpd.serve_forever()
EOF
