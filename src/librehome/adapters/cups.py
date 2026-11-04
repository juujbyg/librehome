# SPDX-License-Identifier: GPL-2.0-or-later
"""System print queues: CUPS on Linux/macOS, PowerShell on Windows. Use "ipp" for driverless printing."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile

from .base import ActionError, Adapter

WIN = sys.platform == "win32"


def _run(cmd: list[str], timeout: int = 20) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ActionError(f"{cmd[0]} failed: {exc}") from None
    if r.returncode != 0:
        raise ActionError((r.stderr or r.stdout).strip() or f"{cmd[0]} exited {r.returncode}")
    return r.stdout


class CupsAdapter(Adapter):
    def devices(self):
        return self._windows() if WIN else self._cups()

    # -- CUPS ----------------------------------------------------------
    def _cups(self):
        if not shutil.which("lpstat"):
            return []
        try:
            out = _run(["lpstat", "-p"])
        except ActionError:
            return []
        devices = []
        for line in out.splitlines():
            m = re.match(r"printer (\S+) (.*)", line)
            if not m:
                continue
            queue, rest = m.groups()
            status = "idle" if "idle" in rest else "printing" if "now printing" in rest else "disabled"
            jobs = self._cups_jobs(queue)
            devices.append({
                "id": queue, "name": queue.replace("_", " "), "kind": "printer",
                "online": status != "disabled",
                "state": {"status": status, "queue": jobs},
                "actions": [{"name": "cancel_all", "params": {}},
                            {"name": "test_page", "params": {}}],
            })
        return devices

    def _cups_jobs(self, queue):
        try:
            out = _run(["lpstat", "-o", queue])
        except ActionError:
            return []
        return [line.split()[0] for line in out.splitlines() if line.strip()]

    def act(self, device_id, action, params):
        if action == "cancel_all":
            if WIN:
                raise ActionError("cancel_all is not supported on Windows yet")
            _run(["cancel", "-a", device_id])
        elif action == "test_page":
            self.print_file(device_id, "test.txt", b"LibreHome test page\n" + b"0123456789 " * 8)
        else:
            raise ActionError(f"printers have no action {action!r}")
        return next((d for d in self.devices() if d["id"] == device_id), {})

    def print_file(self, device_id, filename, data):
        if not data:
            raise ActionError("empty file")
        suffix = os.path.splitext(os.path.basename(filename))[1][:10]
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(data)
        try:
            if WIN:
                ps = f"Start-Process -FilePath '{tmp.name}' -Verb PrintTo -ArgumentList '\"{device_id}\"' -Wait"
                _run(["powershell", "-NoProfile", "-Command", ps], timeout=120)
                return {"submitted": True}
            out = _run(["lp", "-d", device_id, "-t", os.path.basename(filename), tmp.name])
            return {"submitted": True, "detail": out.strip()}
        finally:
            # CUPS has copied the file by the time lp returns.
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    # -- Windows -------------------------------------------------------
    def _windows(self):
        try:
            out = _run(["powershell", "-NoProfile", "-Command",
                        "Get-Printer | ForEach-Object { $_.Name + '|' + $_.PrinterStatus }"])
        except ActionError:
            return []
        devices = []
        for line in out.splitlines():
            name, _, status = line.partition("|")
            if name.strip():
                devices.append({"id": name.strip(), "name": name.strip(), "kind": "printer",
                                "online": True,
                                "state": {"status": status.strip().lower() or "idle", "queue": []},
                                "actions": []})
        return devices
