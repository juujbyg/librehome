# SPDX-License-Identifier: GPL-2.0-or-later
"""Adapter contract.

A device is a plain dict:
  {"id": str, "name": str, "kind": str, "online": bool, "state": {...},
   "actions": [{"name": str, "params": {param: {"type": ..., ...}}}]}
Adapters return devices with adapter-local ids; the registry prefixes them.
"""
from __future__ import annotations


class ActionError(Exception):
    """An action could not be performed (bad input, device unreachable, ...)."""


class Adapter:
    def __init__(self, entry: dict):
        self.entry = entry
        self.name = entry.get("name") or entry["type"]

    def devices(self) -> list[dict]:
        raise NotImplementedError

    def act(self, device_id: str, action: str, params: dict) -> dict:
        raise NotImplementedError

    def print_file(self, device_id: str, filename: str, data: bytes) -> dict:
        raise ActionError("this device cannot print")

    def scan(self, device_id: str, dpi: int | None = None, color: bool = True) -> bytes:
        """Scan one page and return it as JPEG."""
        raise ActionError("this device cannot scan")
