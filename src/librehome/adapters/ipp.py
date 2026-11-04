# SPDX-License-Identifier: GPL-2.0-or-later
"""Driverless printers: IPP Everywhere / AirPrint, found with mDNS. No CUPS, no drivers,
same code on Linux, Windows and macOS.

Config: {"type": "ipp", "name": "printers"}  -> discovers printers on the network.
Optional: "printers": [{"name": "Office", "host": "192.168.1.30"}] for networks where mDNS
is blocked (port 631, path /ipp/print and ipps are the defaults).

Scanning: each online printer's address is checked once, in the background, for an eSCL
(AirPrint) scanner. If one answers, the printer gets a "scan" action. A printer entry may
pin the scanner with "escl": {"port": 443, "secure": true}.
"""
from __future__ import annotations

import mimetypes
import re
import threading
import time

from ..protocols import escl, ipp, mdns
from .base import ActionError, Adapter

DISCOVERY_EVERY = 120  # seconds; discovery takes a few seconds, so don't do it on every refresh
STATE_ATTRS = ["printer-state", "printer-state-reasons", "printer-make-and-model",
               "marker-names", "marker-levels", "marker-low-levels", "document-format-supported"]
# What we can send without rendering anything ourselves, in order of preference.
DIRECT_FORMATS = {
    ".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".txt": "text/plain", ".pwg": "image/pwg-raster", ".urf": "image/urf",
}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "printer"


class IppAdapter(Adapter):
    def __init__(self, entry):
        super().__init__(entry)
        self.static = [{"port": 631, "path": "/ipp/print", "secure": True, **p}
                       for p in entry.get("printers", [])]
        self.discover = entry.get("discover", True)
        self.found: dict[str, dict] = {}
        self.found_at = 0.0
        self.lock = threading.Lock()
        # host -> scanner dict, None (none there), or "checking"
        self.scanners: dict[str, dict | str | None] = {}

    # -- discovery -----------------------------------------------------
    def _printers(self) -> dict[str, dict]:
        with self.lock:
            if time.monotonic() - self.found_at > DISCOVERY_EVERY or not self.found_at:
                found = list(self.static)
                if self.discover:
                    try:
                        found += mdns.discover(timeout=2.5)
                    except OSError:
                        pass  # no network / multicast blocked: keep the static ones
                self.found = {_slug(p["name"]): p for p in found}
                self.found_at = time.monotonic()
            return dict(self.found)

    def _client(self, device_id: str, timeout=8) -> ipp.Printer:
        p = self._printers().get(device_id)
        if p is None:
            raise ActionError(f"printer {device_id!r} not found on the network")
        return ipp.Printer(p["host"], p["port"], p["path"], p["secure"], timeout=timeout)

    # -- scanning ------------------------------------------------------
    def _scanner(self, p: dict) -> dict | str | None:
        """The printer's scanner if known; starts a background check the first time."""
        host = p["host"]
        with self.lock:
            if host in self.scanners:
                return self.scanners[host]
            self.scanners[host] = "checking"
        pinned = p.get("escl")
        endpoints = [(pinned.get("secure", True), pinned["port"])] if pinned else escl.ENDPOINTS

        def check():
            try:
                found = escl.survey(host, endpoints)[0]
            except Exception:  # a strange device must not kill the hub
                found = None
            with self.lock:
                self.scanners[host] = found
        threading.Thread(target=check, daemon=True).start()
        return "checking"

    def scan(self, device_id, dpi=None, color=True) -> bytes:
        p = self._printers().get(device_id)
        if p is None:
            raise ActionError(f"printer {device_id!r} not found on the network")
        scanner = self._scanner(p)
        if scanner == "checking":
            raise ActionError("still looking for this printer's scanner; try again in a few seconds")
        if not scanner:
            raise ActionError(f"{p['name']} has no driverless (eSCL / AirPrint) scanner")
        if dpi in (None, ""):
            dpi = 300 if 300 in scanner["dpis"] else scanner["dpis"][0]
        try:
            dpi = int(dpi)
        except (TypeError, ValueError):
            raise ActionError("resolution must be a number") from None
        if dpi not in scanner["dpis"]:
            raise ActionError(f"choose a resolution of {', '.join(map(str, scanner['dpis']))} dpi")
        try:
            return escl.scan_page(scanner, dpi, color)
        except (escl.ScanError, OSError) as exc:
            raise ActionError(f"scan failed: {exc}") from None

    # -- adapter -------------------------------------------------------
    def devices(self):
        out = []
        for pid, p in self._printers().items():
            client = ipp.Printer(p["host"], p["port"], p["path"], p["secure"], timeout=5)
            dev = {"id": pid, "name": p["name"], "kind": "printer", "online": False,
                   "state": {"status": "offline", "queue": []},
                   "actions": [{"name": "cancel_all", "params": {}},
                               {"name": "test_page", "params": {}}]}
            try:
                attrs = client.call(ipp.OP_GET_PRINTER_ATTRIBUTES,
                                    [(ipp.TAG_KEYWORD, "requested-attributes", STATE_ATTRS)])[1]
                jobs = client.jobs()
            except (ipp.IppError, OSError) as exc:
                dev["state"]["error"] = str(exc)
                out.append(dev)
                continue
            reasons = [r for r in attrs.get("printer-state-reasons", []) if r != "none"]
            ink = dict(zip(attrs.get("marker-names", []), attrs.get("marker-levels", []), strict=False))
            dev["online"] = True
            scanner = self._scanner(p)
            if isinstance(scanner, dict):
                dev["actions"].append({"name": "scan", "params": {
                    "dpi": {"type": "choice", "choices": [str(d) for d in scanner["dpis"]],
                            "default": "300" if 300 in scanner["dpis"] else str(scanner["dpis"][0])},
                    "color": {"type": "choice", "choices": ["color", "grey"]
                              if "RGB24" in scanner["modes"] else ["grey"]},
                }})
            dev["state"] = {
                "status": ipp.PRINTER_STATES.get(attrs.get("printer-state", [3])[0], "unknown"),
                "model": attrs.get("printer-make-and-model", [""])[0],
                "ink": ink,
                "warnings": reasons,
                "queue": [{"id": j.get("job-id", [0])[0], "name": j.get("job-name", [""])[0],
                           "state": ipp.JOB_STATES.get(j.get("job-state", [0])[0], "?")}
                          for j in jobs],
            }
            out.append(dev)
        return out

    def act(self, device_id, action, params):
        client = self._client(device_id)
        try:
            if action == "cancel_all":
                for job in client.jobs():
                    client.cancel(job.get("job-id", [0])[0])
            elif action == "test_page":
                text = "LibreHome test page\n\nIf you can read this, driverless printing works.\n"
                client.print_document(text.encode(), self._pick_format(client, ".txt"), "LibreHome test page")
            else:
                raise ActionError(f"printers have no action {action!r}")
        except (ipp.IppError, OSError) as exc:
            raise ActionError(str(exc)) from None
        return next((d for d in self.devices() if d["id"] == device_id), {})

    def _pick_format(self, client: ipp.Printer, ext: str) -> str:
        wanted = DIRECT_FORMATS.get(ext) or mimetypes.guess_type("x" + ext)[0]
        supported = client.call(ipp.OP_GET_PRINTER_ATTRIBUTES, [
            (ipp.TAG_KEYWORD, "requested-attributes", ["document-format-supported"])])[1].get(
            "document-format-supported", [])
        if wanted in supported:
            return wanted
        if "application/octet-stream" in supported and wanted in ("application/pdf", "image/jpeg"):
            return "application/octet-stream"  # printer auto-detects
        raise ActionError(
            f"this printer can't read {ext or 'this file'} directly "
            f"(it accepts: {', '.join(s for s in supported if s != 'application/octet-stream')}). "
            "Convert it to PDF or JPEG, or use LibrePrint, which renders documents for any printer.")

    def print_file(self, device_id, filename, data):
        if not data:
            raise ActionError("empty file")
        client = self._client(device_id, timeout=120)
        ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
        try:
            mime = self._pick_format(client, ext)
            job = client.print_document(data, mime, filename)
        except (ipp.IppError, OSError) as exc:
            raise ActionError(str(exc)) from None
        return {"submitted": True, "job_id": job, "format": mime}
