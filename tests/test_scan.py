# SPDX-License-Identifier: GPL-2.0-or-later
import json
import threading
import time
import urllib.request

import pytest
from fake_printer import serve as fake_printer
from fake_scanner import JPEG
from fake_scanner import serve as fake_scanner

from librehome.adapters import ActionError
from librehome.registry import Registry
from librehome.server import serve

ID = "printers/fake-printer"


@pytest.fixture
def reg():
    printer, _ = fake_printer()
    scanner, sstate = fake_scanner()
    entry = {"type": "ipp", "name": "printers", "discover": False,
             "printers": [{"name": "Fake Printer", "host": "127.0.0.1", "port": printer.server_address[1],
                           "secure": False, "escl": {"port": scanner.server_address[1], "secure": False}}]}
    reg = Registry({"adapters": [entry]})
    yield reg, sstate
    printer.shutdown()
    scanner.shutdown()


def wait_for_scan_action(reg):
    for _ in range(50):
        (dev,) = reg.devices()
        scan = next((a for a in dev["actions"] if a["name"] == "scan"), None)
        if scan:
            return scan
        time.sleep(0.1)
    raise AssertionError("scanner never found")


def test_scanner_is_found_and_offered(reg):
    scan = wait_for_scan_action(reg[0])
    assert scan["params"]["dpi"]["choices"] == ["150", "300"]
    assert scan["params"]["dpi"]["default"] == "300"
    assert scan["params"]["color"]["choices"] == ["color", "grey"]


def test_scan_returns_jpeg_with_chosen_settings(reg):
    r, state = reg
    wait_for_scan_action(r)
    assert r.scan(ID, 150, color=False) == JPEG
    assert "<scan:XResolution>150<" in state["settings"][0]
    assert "Grayscale8" in state["settings"][0]


def test_unsupported_resolution_is_explained(reg):
    wait_for_scan_action(reg[0])
    with pytest.raises(ActionError, match="150, 300"):
        reg[0].scan(ID, 1200)


def test_printer_without_scanner():
    printer, _ = fake_printer()
    entry = {"type": "ipp", "name": "printers", "discover": False,
             "printers": [{"name": "Fake Printer", "host": "127.0.0.1", "port": printer.server_address[1],
                           "secure": False, "escl": {"port": 9, "secure": False}}]}
    r = Registry({"adapters": [entry]})
    r.devices()
    for _ in range(100):  # a refused connection takes ~2 s on Windows
        try:
            r.scan(ID)
        except ActionError as exc:
            if "still looking" in str(exc):
                time.sleep(0.1)
                continue
            assert "no driverless" in str(exc)
            break
    else:
        raise AssertionError("scanner check never finished")
    printer.shutdown()


def test_scan_over_http_api(reg):
    r, _ = reg
    wait_for_scan_action(r)
    httpd = serve(r, "secret", "127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{httpd.server_address[1]}/api/scan/{ID}",
                                     data=json.dumps({}).encode(), method="POST",
                                     headers={"X-Token": "secret", "Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            assert resp.headers["Content-Type"] == "image/jpeg"
            assert 'filename="scan-' in resp.headers["Content-Disposition"]
            assert resp.read() == JPEG
    finally:
        httpd.shutdown()


def test_oversized_scanner_reply_is_refused():
    import http.server

    from librehome.protocols import escl

    class Flood(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            try:
                for _ in range(40):  # 2.5 MB, over the 1 MB cap for capabilities
                    self.wfile.write(b"x" * 65536)
            except OSError:
                pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Flood)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        scanner = {"host": "127.0.0.1", "port": server.server_address[1], "secure": False}
        with pytest.raises(escl.ScanError, match="more data"):
            escl._request(scanner, "GET", "/eSCL/ScannerCapabilities")
    finally:
        server.shutdown()
