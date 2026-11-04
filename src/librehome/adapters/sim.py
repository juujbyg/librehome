# SPDX-License-Identifier: GPL-2.0-or-later
"""Simulated appliances so the whole app works before real devices are connected."""
from __future__ import annotations

import os
import threading
import time

from .base import ActionError, Adapter

SPEED = float(os.environ.get("LIBREHOME_SIM_SPEED", "1"))  # >1 makes cycles run faster


class Machine:
    kind = "machine"
    label = ""
    programs: dict[str, int] = {}  # program -> minutes

    def __init__(self, ident: str, name: str):
        self.id, self.name = ident, name
        self.program: str | None = None
        self.started: float | None = None
        self.duration = 0.0  # seconds
        self.extra: dict = {}

    def remaining(self) -> int:
        if self.started is None:
            return 0
        left = self.duration - (time.time() - self.started) * SPEED
        if left <= 0:
            self.started = None
            self.program = None
            return 0
        return int(left)

    def device(self) -> dict:
        left = self.remaining()
        state = {"status": "running" if left else "idle", "program": self.program,
                 "remaining_s": left, **self.extra}
        return {"id": self.id, "name": self.name, "kind": self.kind, "online": True,
                "state": state, "actions": self.actions()}

    def actions(self) -> list[dict]:
        return [
            {"name": "start", "params": {"program": {"type": "choice", "choices": list(self.programs)}}},
            {"name": "stop", "params": {}},
        ]

    def act(self, action: str, params: dict) -> None:
        if action == "start":
            program = params.get("program") or next(iter(self.programs))
            if program not in self.programs:
                raise ActionError(f"unknown program {program!r}; choose {', '.join(self.programs)}")
            if self.remaining():
                raise ActionError(f"{self.name} is already running")
            self.program, self.started = program, time.time()
            self.duration = self.programs[program] * 60
        elif action == "stop":
            self.started = self.program = None
        else:
            raise ActionError(f"{self.name} has no action {action!r}")


class Dishwasher(Machine):
    kind = "dishwasher"
    programs = {"eco": 180, "auto": 120, "intensive": 150, "quick": 60}


class WashingMachine(Machine):
    kind = "washing_machine"
    programs = {"cotton": 150, "synthetic": 90, "delicate": 60, "quick": 30}


class AirFryer(Machine):
    kind = "air_fryer"
    programs = {"manual": 15}

    def __init__(self, ident, name):
        super().__init__(ident, name)
        self.extra = {"temperature_c": 180}

    def actions(self):
        return [
            {"name": "start", "params": {"temperature_c": {"type": "number", "min": 80, "max": 200},
                                         "minutes": {"type": "number", "min": 1, "max": 60}}},
            {"name": "stop", "params": {}},
        ]

    def act(self, action, params):
        if action == "start":
            if self.remaining():
                raise ActionError(f"{self.name} is already running")
            try:
                temp = int(params.get("temperature_c", 180))
                minutes = float(params.get("minutes", 15))
            except (TypeError, ValueError):
                raise ActionError("temperature_c and minutes must be numbers") from None
            if not 80 <= temp <= 200:
                raise ActionError("temperature must be between 80 and 200 °C")
            if not 1 <= minutes <= 60:
                raise ActionError("time must be between 1 and 60 minutes")
            self.extra["temperature_c"] = temp
            self.program, self.started, self.duration = "manual", time.time(), minutes * 60
        else:
            super().act(action, params)


class SimAdapter(Adapter):
    def __init__(self, entry):
        super().__init__(entry)
        self.lock = threading.Lock()
        self.machines = {m.id: m for m in (
            Dishwasher("dishwasher", "Dishwasher (sim)"),
            WashingMachine("washer", "Washing machine (sim)"),
            AirFryer("airfryer", "Air fryer (sim)"),
        )}

    def devices(self):
        with self.lock:
            return [m.device() for m in self.machines.values()]

    def act(self, device_id, action, params):
        with self.lock:
            machine = self.machines.get(device_id)
            if machine is None:
                raise ActionError(f"unknown device {device_id!r}")
            machine.act(action, params)
            return machine.device()
