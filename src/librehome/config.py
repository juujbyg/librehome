# SPDX-License-Identifier: GPL-2.0-or-later
"""Configuration: one JSON file, per-user, same location logic on Linux and Windows."""
from __future__ import annotations

import json
import os
import secrets
import sys
from pathlib import Path


def config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "librehome"


def config_path() -> Path:
    return Path(os.environ.get("LIBREHOME_CONFIG", config_dir() / "config.json"))


DEFAULT = {
    "token": "",
    "adapters": [
        {"type": "ipp", "name": "printers"},
        {"type": "sim", "name": "sim"},
    ],
}


def load() -> dict:
    path = config_path()
    if path.exists():
        cfg = json.loads(path.read_text(encoding="utf-8"))
    else:
        cfg = json.loads(json.dumps(DEFAULT))
    if not cfg.get("token"):
        cfg["token"] = secrets.token_urlsafe(16)
        save(cfg)
    return cfg


def save(cfg: dict) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)  # holds tokens for Home Assistant etc.
    except OSError:
        pass
