# SPDX-License-Identifier: GPL-2.0-or-later
"""HTTP API + web UI. Stdlib only, so it runs unchanged on Linux and Windows.

Security model:
- Every /api request needs the token in the X-Token header, from any address. A custom header
  can't be sent cross-site without a CORS preflight, which this server never approves, so other
  websites open in the user's browser can't drive the appliances.
- The Host header must be an IP address, localhost, this machine's name or a configured name.
  That defeats DNS rebinding (an attacker's domain pointed at 127.0.0.1 or the LAN address).
- The token is put in the page only when it is loaded from this machine via a loopback address.
  Other devices pair once with the ?token= URL that `librehome config` prints.
"""
from __future__ import annotations

import ipaddress
import json
import secrets
import socket
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from urllib.parse import parse_qs, unquote, urlparse

from . import jarvis
from .adapters import ActionError
from .registry import Registry

MAX_UPLOAD = 100 * 1024 * 1024
LOOPBACK_NAMES = {"localhost", "127.0.0.1", "::1"}


def _host_name(header: str) -> str:
    host = header.strip().lower()
    if host.startswith("["):  # [::1]:8484
        return host[1:].split("]")[0]
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def _is_ip(name: str) -> bool:
    try:
        ipaddress.ip_address(name)
        return True
    except ValueError:
        return False


def make_handler(reg: Registry, token: str, extra_hosts=()):
    me = socket.gethostname().lower()
    allowed_names = LOOPBACK_NAMES | {me, me + ".local"} | {h.lower() for h in extra_hosts}

    class Handler(BaseHTTPRequestHandler):
        server_version = "LibreHome"

        def log_message(self, format, *args):  # noqa: A002 (stdlib signature)
            pass

        # -- helpers ---------------------------------------------------
        def _host_ok(self) -> bool:
            name = _host_name(self.headers.get("Host", ""))
            return _is_ip(name) or name in allowed_names

        def _local_page(self) -> bool:
            client_loopback = ipaddress.ip_address(self.client_address[0].split("%")[0]).is_loopback
            return client_loopback and _host_name(self.headers.get("Host", "")) in LOOPBACK_NAMES

        def _authorized(self) -> bool:
            return secrets.compare_digest(self.headers.get("X-Token", ""), token)

        def _send(self, code: int, body, ctype="application/json", headers=None):
            raw = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")  # pairing URLs carry the token
            self.end_headers()
            self.wfile.write(raw)

        def _json_body(self) -> dict:
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                raise ActionError("Content-Type must be application/json")
            n = int(self.headers.get("Content-Length") or 0)
            if not n:
                return {}
            if n > 64 * 1024:
                raise ActionError("request too large")
            try:
                data = json.loads(self.rfile.read(n))
            except ValueError:
                raise ActionError("body must be JSON") from None
            if not isinstance(data, dict):
                raise ActionError("body must be a JSON object")
            return data

        def _dispatch(self, method: str):
            if not self._host_ok():
                return self._send(403, {"error": "unknown Host"})
            url = urlparse(self.path)
            query = parse_qs(url.query)
            path = unquote(url.path)
            if path == "/" and method == "GET":
                page = resources.files("librehome").joinpath("web/index.html").read_text(encoding="utf-8")
                if self._local_page():
                    page = page.replace('content="__TOKEN__"', f'content="{token}"')
                return self._send(200, page.encode(), "text/html; charset=utf-8")
            if not self._authorized():
                return self._send(401, {"error": "missing or wrong token: open the pairing URL "
                                                 "that `librehome config` prints"})
            try:
                if path == "/api/devices" and method == "GET":
                    return self._send(200, reg.devices())
                if path == "/api/command" and method == "POST":
                    text = str(self._json_body().get("text", ""))[:500]
                    return self._send(200, {"reply": jarvis.handle(text, reg)})
                if path.startswith("/api/print/") and method == "POST":
                    n = int(self.headers.get("Content-Length") or 0)
                    if not 0 < n <= MAX_UPLOAD:
                        raise ActionError("file missing or larger than 100 MB")
                    name = (query.get("name") or ["document"])[0][:200]
                    return self._send(200, reg.print_file(path[len("/api/print/"):], name, self.rfile.read(n)))
                if path.startswith("/api/scan/") and method == "POST":
                    opts = self._json_body()
                    color = str(opts.get("color", "color")) != "grey"
                    jpeg = reg.scan(path[len("/api/scan/"):], opts.get("dpi"), color)
                    name = time.strftime("scan-%Y%m%d-%H%M%S.jpg")
                    return self._send(200, jpeg, "image/jpeg",
                                      {"Content-Disposition": f'attachment; filename="{name}"'})
                if path.startswith("/api/act/") and method == "POST":
                    device_id, _, action = path[len("/api/act/"):].rpartition("/")
                    return self._send(200, reg.act(device_id, action, self._json_body()))
                return self._send(404, {"error": "not found"})
            except ActionError as exc:
                return self._send(400, {"error": str(exc)})
            except Exception as exc:  # keep the server alive, tell the client
                return self._send(500, {"error": f"internal error: {type(exc).__name__}"})

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

    return Handler


def serve(reg: Registry, token: str, host: str, port: int, extra_hosts=()) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(reg, token, extra_hosts))
