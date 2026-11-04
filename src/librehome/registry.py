# SPDX-License-Identifier: GPL-2.0-or-later
"""Collects devices from every configured adapter under one namespace."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from . import adapters
from .adapters import ActionError


class Registry:
    def __init__(self, cfg: dict):
        self.adapters = {}
        for entry in cfg.get("adapters", []):
            ad = adapters.build(entry)
            self.adapters[ad.name] = ad

    def devices(self) -> list[dict]:
        def fetch(ad):
            try:
                return [{**d, "id": f"{ad.name}/{d['id']}"} for d in ad.devices()]
            except Exception as exc:  # one broken adapter must not hide the others
                return [{"id": f"{ad.name}/_error", "name": f"{ad.name} (error)", "kind": "error",
                         "online": False, "state": {"error": str(exc)}, "actions": []}]
        with ThreadPoolExecutor(max_workers=max(1, len(self.adapters))) as pool:
            return [d for chunk in pool.map(fetch, self.adapters.values()) for d in chunk]

    def _split(self, full_id: str):
        name, _, local = full_id.partition("/")
        if name not in self.adapters:
            raise ActionError(f"unknown device {full_id!r}")
        return self.adapters[name], local

    def act(self, full_id: str, action: str, params: dict | None = None) -> dict:
        ad, local = self._split(full_id)
        dev = ad.act(local, action, params or {})
        return {**dev, "id": full_id} if dev else {}

    def print_file(self, full_id: str, filename: str, data: bytes) -> dict:
        ad, local = self._split(full_id)
        return ad.print_file(local, filename, data)

    def scan(self, full_id: str, dpi: int | None = None, color: bool = True) -> bytes:
        ad, local = self._split(full_id)
        return ad.scan(local, dpi, color)
