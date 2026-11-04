# Contributing to LibreHome

Thanks for helping. LibreHome is pure Python (standard library only at runtime) and runs on Linux, Windows and macOS. The Ubuntu Touch app in `ubuntutouch/` is QML.

## Setup

```sh
python3 -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install pytest ruff
python -m pytest -q
ruff check src tests
./run.sh                                        # Windows: run.bat
```

## Ground rules

- Python >= 3.10, **standard library only** at runtime. That is what makes it run anywhere, including confined phones.
- **Driverless first.** Prefer a device's open, standard protocol (IPP, eSCL, Matter, a documented local API) over a vendor cloud, and a vendor cloud over a bridge. Never ship vendor drivers, binaries or reverse-engineered secrets.
- Every source file starts with `# SPDX-License-Identifier: GPL-2.0-or-later`.
- Tests never need real hardware. Protocol code is tested against simulators (see `tests/fake_printer.py` and `tests/fake_scanner.py`).
- An adapter must never crash the hub. Report failures as `ActionError` with a message a non-technical person can act on.

## Layout

- `src/librehome/protocols/`: wire protocols (`ipp.py`, `mdns.py`, `escl.py`, shared with LibrePrint).
- `src/librehome/adapters/`: one file per device family or bridge. Each turns devices into plain dicts (see `adapters/base.py`).
- `src/librehome/registry.py`: merges all adapters.
- `src/librehome/jarvis.py`: the plain-language commands.
- `src/librehome/server.py` + `web/index.html`: the API and the app that every platform uses.
- `ubuntutouch/`: the phone app (`clickable build`).

## Adding an appliance family

1. Write `src/librehome/adapters/<name>.py` with a subclass of `Adapter` implementing `devices()` and `act()`.
2. Register it in `adapters/__init__.py`.
3. Add a simulator or recorded responses under `tests/` and test it.
4. Document its config in `docs/ADAPTERS.md`, and the models you tested in `docs/HARDWARE.md`.

## Reporting hardware results

Open a "Device report" issue, or add a row to [docs/HARDWARE.md](docs/HARDWARE.md).
