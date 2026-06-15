"""Stub web server — phase 0 placeholder (web role of the app image).

Declared mock, replaced by the real FastAPI app in 1.B2: stdlib only,
no framework, no dependencies, and /api/health always answers 200
regardless of any real state.
"""

import json
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


class StubHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def do_GET(self):
        if self.path == "/api/health":
            body = json.dumps({"status": "ok", "stub": True}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def log_message(self, fmt, *args):
        print("stub-web: " + fmt % args, flush=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    print(f"stub-web: placeholder on :{port} — mock, replaced by 1.B2", flush=True)
    HTTPServer(("0.0.0.0", port), StubHandler).serve_forever()
