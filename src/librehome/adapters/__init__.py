# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

from .base import ActionError, Adapter
from .cups import CupsAdapter
from .homeassistant import HomeAssistantAdapter
from .http import HttpAdapter
from .ipp import IppAdapter
from .sim import SimAdapter

TYPES = {
    "sim": SimAdapter,
    "ipp": IppAdapter,
    "cups": CupsAdapter,
    "printers": CupsAdapter,  # old name for "cups"
    "homeassistant": HomeAssistantAdapter,
    "http": HttpAdapter,
}


def build(entry: dict) -> Adapter:
    try:
        cls = TYPES[entry["type"]]
    except KeyError:
        raise ValueError(f"unknown adapter type: {entry.get('type')!r}") from None
    return cls(entry)


__all__ = ["Adapter", "ActionError", "build", "TYPES"]
