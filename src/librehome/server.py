# SPDX-License-Identifier: GPL-2.0-or-later
"""HTTP API + web UI. Stdlib only, so it runs unchanged on Linux and Windows."""
from __future__ import annotations

import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from urllib.parse import parse_qs, unquote, urlparse

from . import jarvis
from .adapters import ActionError
from .registry import Registry

MAX_UPLOAD = 100 * 1024 * 1024


def make_handler(reg: Registry, token: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "LibreHome"

        def log_message(self, fmt, *args):
            pass

        # -- helpers ---------------------------------------------------
        def _authorized(self, query: dict) -> bool:
            if self.client_address[0] in ("127.0.0.1", "::1"):
                return True
            given = self.headers.get("X-Token") or (query.get("token") or [""])[0]
            return secrets.compare_digest(given, token)

        def _send(self, code: int, body, ctype="application/json"):
            raw = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def _json_body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if not n:
                return {}
            try:
                data = json.loads(self.rfile.read(n))
            except ValueError:
                raise ActionError("body must be JSON") from None
            if not isinstance(data, dict):
                raise ActionError("body must be a JSON object")
            return data

        def _dispatch(self, method: str):
            url = urlparse(self.path)
            query = parse_qs(url.query)
            path = unquote(url.path)
            if path == "/" and method == "GET":
                page = resources.files("librehome").joinpath("web/index.html").read_bytes()
                return self._send(200, page, "text/html; charset=utf-8")
            if not self._authorized(query):
                return self._send(401, {"error": "missing or wrong token"})
            try:
                if path == "/api/devices" and method == "GET":
                    return self._send(200, reg.devices())
                if path == "/api/command" and method == "POST":
                    text = str(self._json_body().get("text", ""))
                    return self._send(200, {"reply": jarvis.handle(text, reg)})
                if path.startswith("/api/print/") and method == "POST":
                    n = int(self.headers.get("Content-Length") or 0)
                    if not 0 < n <= MAX_UPLOAD:
                        raise ActionError("file missing or larger than 100 MB")
                    name = (query.get("name") or ["document"])[0]
                    return self._send(200, reg.print_file(path[len("/api/print/"):], name, self.rfile.read(n)))
                if path.startswith("/api/act/") and method == "POST":
                    device_id, _, action = path[len("/api/act/"):].rpartition("/")
                    return self._send(200, reg.act(device_id, action, self._json_body()))
                return self._send(404, {"error": "not found"})
            except ActionError as exc:
                return self._send(400, {"error": str(exc)})
            except Exception as exc:  # keep the server alive, tell the client
                return self._send(500, {"error": f"internal error: {exc}"})

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

    return Handler


def serve(reg: Registry, token: str, host: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(reg, token))
