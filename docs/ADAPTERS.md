# Adapters

Adapters are listed in the config file: `~/.config/librehome/config.json` (Windows: `%APPDATA%\librehome\config.json`; override with `LIBREHOME_CONFIG`). Run `librehome config` to see the path. Every entry needs a `type` and a unique `name`; the name prefixes device ids (`printers/office-printer`).

## `ipp`: driverless printers
IPP Everywhere / AirPrint printers, found automatically with mDNS. Same code on every OS, no CUPS or drivers. Shows status, ink levels, warnings and the queue; prints PDF, JPEG, PNG and text when the printer reads them; cancels jobs.
```json
{"type": "ipp", "name": "printers"}
{"type": "ipp", "name": "printers", "printers": [{"name": "Office", "host": "192.168.1.30"}]}
```
Use `printers` for networks that block mDNS. Optional keys per printer: `port` (631), `path` (`/ipp/print`), `secure` (true).

## `cups`: system print queues
Queues already set up on the computer (CUPS on Linux/macOS, Windows printers). Useful for USB printers.
```json
{"type": "cups", "name": "queues"}
```

## `homeassistant`: bridge
Any appliance Home Assistant supports (Home Connect, SmartThings, Miele, Tuya, LG ThinQ...). `start`/`stop` map to `turn_on`/`turn_off` (`start`/`stop` for vacuums); `service` calls any service.
```json
{"type": "homeassistant", "name": "ha", "url": "http://homeassistant.local:8123", "token": "<long-lived access token>"}
```

## `http`: any appliance with a web API
```json
{"type": "http", "name": "fryer",
 "device": {"id": "fryer", "name": "Air fryer", "kind": "air_fryer"},
 "status": {"url": "http://192.168.1.50/status"},
 "actions": {"start": {"method": "POST", "url": "http://192.168.1.50/start", "body": {"temp": "{temperature_c}"}},
             "stop": {"method": "POST", "url": "http://192.168.1.50/stop"}}}
```

## `sim`: simulated appliances
A dishwasher, washing machine and air fryer to try LibreHome without hardware. `LIBREHOME_SIM_SPEED=60` makes a minute pass every second. Remove the entry once real appliances are connected.
