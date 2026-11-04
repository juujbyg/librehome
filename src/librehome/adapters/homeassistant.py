# SPDX-License-Identifier: GPL-2.0-or-later
"""Home Assistant bridge: reaches hundreds of real appliances (Home Connect, SmartThings, Tuya,
Cosori, Miele, ...) over LAN or the internet via Home Assistant's REST API.

Config: {"type": "homeassistant", "url": "http://homeassistant.local:8123", "token": "<long-lived token>"}
Optional: "domains": [...] to limit which entity types are shown.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from .base import ActionError, Adapter

SAFE = re.compile(r"[a-z0-9_]{1,64}")
DOMAINS = {"switch", "light", "climate", "fan", "vacuum", "cover", "humidifier", "water_heater",
           "media_player", "lock"}
NAME_KINDS = (("dishwasher", "dishwasher"), ("washing", "washing_machine"), ("washer", "washing_machine"),
              ("dryer", "dryer"), ("fryer", "air_fryer"), ("oven", "oven"), ("printer", "printer"),
              ("fridge", "fridge"), ("coffee", "coffee_machine"))


class HomeAssistantAdapter(Adapter):
    def __init__(self, entry):
        super().__init__(entry)
        self.url = entry["url"].rstrip("/")
        self.token = entry["token"]
        self.domains = set(entry.get("domains") or DOMAINS)

    def _call(self, path: str, body: dict | None = None):
        req = urllib.request.Request(
            self.url + path, method="POST" if body is not None else "GET",
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read() or "null")
        except urllib.error.HTTPError as exc:
            raise ActionError(f"Home Assistant answered {exc.code} {exc.reason}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ActionError(f"cannot reach Home Assistant at {self.url}: {exc}") from None

    def devices(self):
        try:
            states = self._call("/api/states")
        except ActionError:
            return []
        out = []
        for s in states:
            domain = s["entity_id"].split(".")[0]
            if domain not in self.domains:
                continue
            attrs = s.get("attributes", {})
            name = attrs.get("friendly_name", s["entity_id"])
            kind = next((k for needle, k in NAME_KINDS if needle in name.lower()), domain)
            out.append({
                "id": s["entity_id"], "name": name, "kind": kind,
                "online": s["state"] not in ("unavailable", "unknown"),
                "state": {"status": s["state"]},
                "actions": [{"name": "start", "params": {}}, {"name": "stop", "params": {}},
                            {"name": "service", "params": {"service": {"type": "text"}}}],
            })
        return out

    def act(self, device_id, action, params):
        # Only entities this adapter lists, in the configured domains: a caller with the hub
        # token must not be able to reach other Home Assistant services (scripts, shell commands...).
        domain = device_id.split(".")[0]
        if domain not in self.domains or not SAFE.fullmatch(device_id.replace(".", "_")):
            raise ActionError(f"unknown device {device_id!r}")
        if device_id not in {d["id"] for d in self.devices()}:
            raise ActionError(f"unknown device {device_id!r}")
        if action == "start":
            service = "turn_on" if domain != "vacuum" else "start"
        elif action == "stop":
            service = "turn_off" if domain != "vacuum" else "stop"
        elif action == "service":
            service = str(params.get("service", ""))
            if not SAFE.fullmatch(service):
                raise ActionError("service must be a name like turn_on or set_temperature")
        else:
            raise ActionError(f"unknown action {action!r}")
        extra = {k: v for k, v in params.items()
                 if k not in ("service", "entity_id") and SAFE.fullmatch(str(k))
                 and isinstance(v, (str, int, float, bool))}
        self._call(f"/api/services/{domain}/{service}", {**extra, "entity_id": device_id})
        return next((d for d in self.devices() if d["id"] == device_id), {})
