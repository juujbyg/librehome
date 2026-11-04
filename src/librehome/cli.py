# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import webbrowser

from . import __version__, config, jarvis
from .adapters import ActionError
from .registry import Registry
from .server import serve


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="librehome", description="Jarvis-style hub for your home appliances")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("serve", help="start the hub and web UI (default)")
    s.add_argument("--host", default="0.0.0.0", help="0.0.0.0 lets your phone connect (default)")
    s.add_argument("--port", type=int, default=8484)
    s.add_argument("--no-browser", action="store_true")
    sub.add_parser("devices", help="list devices as JSON")
    c = sub.add_parser("say", help='talk to Jarvis, e.g. librehome say "start the dishwasher"')
    c.add_argument("text", nargs="+")
    sub.add_parser("config", help="print the config path and phone pairing URL")
    args = p.parse_args(argv)

    cfg = config.load()
    reg = Registry(cfg)
    if args.cmd == "devices":
        print(json.dumps(reg.devices(), indent=2))
        return 0
    if args.cmd == "say":
        try:
            print(jarvis.handle(" ".join(args.text), reg))
            return 0
        except ActionError as exc:
            print(f"Jarvis: {exc}", file=sys.stderr)
            return 1
    if args.cmd == "config":
        print(f"config file: {config.config_path()}")
        print(f"phone URL:   http://{lan_ip()}:8484/?token={cfg['token']}")
        return 0

    host = getattr(args, "host", "0.0.0.0")
    port = getattr(args, "port", 8484)
    httpd = serve(reg, cfg["token"], host, port)
    print(f"LibreHome {__version__} running")
    print(f"  this computer: http://127.0.0.1:{port}/")
    print(f"  phone / other: http://{lan_ip()}:{port}/?token={cfg['token']}")
    print("Stop with Ctrl+C.")
    if not getattr(args, "no_browser", False):
        threading.Timer(0.5, lambda: webbrowser.open(f"http://127.0.0.1:{port}/")).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
