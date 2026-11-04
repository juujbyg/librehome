# SPDX-License-Identifier: GPL-2.0-or-later
"""Generic web-API appliance: map actions to HTTP calls in the config file.

{"type": "http", "name": "garage-airfryer", "device": {"id": "fryer", "name": "Air fryer", "kind": "air_fryer"},
 "status": {"url": "http://192.168.1.50/status"},
 "actions": {"start": {"method": "POST", "url": "http://192.168.1.50/start", "body": {"t": "{temperature_c}"}},
             "stop":  {"method": "POST", "url": "http://192.168.1.50/stop"}}}
Placeholders {param} in url/body are filled from the action's parameters.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from .base import ActionError, Adapter


def _fill(value, params, url=False):
    """Fill {param} placeholders. In URLs every value is percent-encoded, so a parameter can
    never change the host, path or query structure the config file set."""
    if isinstance(value, str):
        for k, v in params.items():
            text = str(v)
            value = value.replace("{" + k + "}", urllib.parse.quote(text, safe="") if url else text)
        return value
    if isinstance(value, dict):
        return {k: _fill(v, params) for k, v in value.items()}
    return value


class HttpAdapter(Adapter):
    def _req(self, method, url, body=None):
        req = urllib.request.Request(
            url, method=method, data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json", **self.entry.get("headers", {})})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ActionError(f"{self.name}: request failed: {exc}") from None
        try:
            return json.loads(raw)
        except ValueError:
            return {"response": raw.decode(errors="replace")[:200]}

    def devices(self):
        dev = dict(self.entry["device"])
        try:
            state = self._req("GET", self.entry["status"]["url"]) if "status" in self.entry else {}
            online = True
        except ActionError:
            state, online = {}, False
        dev.update(online=online, state=state,
                   actions=[{"name": n, "params": {}} for n in self.entry.get("actions", {})])
        return [dev]

    def act(self, device_id, action, params):
        spec = self.entry.get("actions", {}).get(action)
        if spec is None:
            raise ActionError(f"{self.name} has no action {action!r}")
        self._req(spec.get("method", "POST"), _fill(spec["url"], params, url=True), _fill(spec.get("body"), params))
        return self.devices()[0]
