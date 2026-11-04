# SPDX-License-Identifier: GPL-2.0-or-later
"""Natural-language commands ("start the dishwasher on eco", "air fryer 200 for 12 minutes").

Rule-based on purpose: works offline, instantly, and never does something surprising.
Returns a reply string; raises ActionError when it understood but the action failed.
"""
from __future__ import annotations

import re

from .adapters import ActionError
from .registry import Registry

KIND_WORDS = {
    "dishwasher": "dishwasher", "dish washer": "dishwasher",
    "washing machine": "washing_machine", "washer": "washing_machine", "laundry": "washing_machine",
    "air fryer": "air_fryer", "airfryer": "air_fryer", "fryer": "air_fryer",
    "printer": "printer", "oven": "oven", "dryer": "dryer",
}
START = ("start", "run", "begin", "turn on", "switch on", "cook", "fry", "wash")
STOP = ("stop", "cancel", "abort", "turn off", "switch off", "kill")


def _find_device(text: str, devices: list[dict]) -> dict | None:
    t = text.lower()
    for dev in devices:  # exact device name wins
        if dev["name"].lower().split(" (")[0] in t:
            return dev
    for word, kind in sorted(KIND_WORDS.items(), key=lambda kv: -len(kv[0])):
        if word in t:
            matches = [d for d in devices if d["kind"] == kind]
            if matches:
                return matches[0]
    return None


def _describe(dev: dict) -> str:
    s = dev["state"]
    if not dev["online"]:
        return f"{dev['name']}: offline"
    if s.get("remaining_s"):
        return f"{dev['name']}: {s['program']}, {s['remaining_s'] // 60 + 1} min left"
    if dev["kind"] == "printer" and s.get("queue"):
        return f"{dev['name']}: printing {len(s['queue'])} job(s)"
    return f"{dev['name']}: {s.get('status', 'ok')}"


def handle(text: str, reg: Registry) -> str:
    t = text.lower().strip().rstrip(".!?")
    devices = reg.devices()
    if not t:
        raise ActionError("say something like: start the dishwasher")
    overview = re.fullmatch(r"(status|what'?s running|how is everything|report|hello|hi|jarvis)", t)
    if overview or ("status" in t and not _find_device(t, devices)):
        return "\n".join(_describe(d) for d in devices if d["kind"] != "error") or "No devices connected."
    if re.search(r"\bscan", t):
        scanners = [d for d in devices if any(a["name"] == "scan" for a in d["actions"])]
        if not scanners:
            raise ActionError("no scanner found: printers need driverless (eSCL / AirPrint) scanning")
        return f"Put the page on {scanners[0]['name']}'s glass and press scan, or run: librehome scan"
    dev = _find_device(t, devices)
    if dev is None:
        raise ActionError("I don't know which appliance you mean")
    if "status" in t or "how long" in t or "time left" in t:
        return _describe(dev)
    if any(w in t for w in STOP):
        reg.act(dev["id"], "cancel_all" if dev["kind"] == "printer" else "stop")
        return f"Stopped {dev['name']}."
    if any(w in t for w in START) or dev["kind"] == "air_fryer":
        params: dict = {}
        names = {a["name"] for a in dev["actions"]}
        if m := re.search(r"(\d{2,3})\s*(?:°|degrees|deg|c\b)?", t):
            if dev["kind"] == "air_fryer" and 80 <= int(m.group(1)) <= 200:
                params["temperature_c"] = int(m.group(1))
        if m := re.search(r"(?:for\s*)?(\d{1,3})\s*(?:min|minutes|m\b)", t):
            params["minutes"] = int(m.group(1))
        for action in dev["actions"]:
            for choice in action["params"].get("program", {}).get("choices", []):
                if choice in t:
                    params["program"] = choice
        if "start" not in names:
            raise ActionError(f"{dev['name']} can't be started")
        reg.act(dev["id"], "start", params)
        detail = ", ".join(f"{k}={v}" for k, v in params.items())
        return f"Started {dev['name']}" + (f" ({detail})." if detail else ".")
    raise ActionError("I understood the appliance but not what to do. Try: start, stop, status")
