#!/usr/bin/env python3
"""
Local dev server for Fake Basketball web port.

Sets Cross-Origin-Opener-Policy + Cross-Origin-Embedder-Policy on every
response so SharedArrayBuffer / Atomics.wait work without a service worker.

Usage:
    python3 serve.py
Then open: http://localhost:8000
"""
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler


class COIHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy",   "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        super().end_headers()

    def log_message(self, fmt, *args):
        # Suppress noisy request logs; only show startup message.
        pass


port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
print(f"Serving at http://localhost:{port}  (Ctrl+C to stop)")
HTTPServer(("localhost", port), COIHandler).serve_forever()
