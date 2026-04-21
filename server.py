#!/usr/bin/env python3
"""
SOPSearch Vision - Web Server
Serves the app and proxies Anthropic API calls.
API key is set via environment variable ANTHROPIC_API_KEY.
"""

import http.server
import urllib.request
import urllib.error
import json
import os
import sys
import socketserver

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
PORT    = int(os.environ.get("PORT", 8765))
DIR     = os.path.dirname(os.path.abspath(__file__))

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIR, **kwargs)

    def log_message(self, fmt, *args):
        print(f"  {self.command} {self.path} -> {args[1] if len(args)>1 else ''}")

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        # Serve index for root
        if self.path == "/" or self.path == "":
            self.path = "/sopsearch-vision.html"
        super().do_GET()

    def do_POST(self):
        if self.path == "/api/analyze":
            self.handle_analyze()
        else:
            self.send_error(404)

    def handle_analyze(self):
        if not API_KEY:
            self.send_json(500, {"error": {"type": "config_error",
                "message": "ANTHROPIC_API_KEY environment variable not set"}})
            return

        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)

        # Parse body and inject correct model if missing
        try:
            req_data = json.loads(body)
            if "model" not in req_data:
                req_data["model"] = "claude-sonnet-4-5"
            body = json.dumps(req_data).encode()
        except Exception:
            pass

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers={
                "Content-Type":      "application/json",
                "anthropic-version": "2023-06-01",
                "x-api-key":         API_KEY,
            },
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                resp_body = resp.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(resp_body)
        except urllib.error.HTTPError as e:
            err_body = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(err_body)
            print(f"  Anthropic error {e.code}: {err_body[:300]}")
        except Exception as e:
            self.send_json(500, {"error": {"type": "proxy_error", "message": str(e)}})
            print(f"  Proxy error: {e}")

    def send_json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    if not API_KEY:
        # Local mode — prompt for key
        print("=" * 52)
        print("  No ANTHROPIC_API_KEY environment variable found.")
        print("  Set it with:")
        print("  export ANTHROPIC_API_KEY='sk-ant-...'")
        print("  then run: python3 server.py")
        print("=" * 52)
        sys.exit(1)

    print("=" * 52)
    print("  SOPSearch Vision")
    print(f"  http://localhost:{PORT}")
    print("  Ctrl+C to stop")
    print("=" * 52)

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")
