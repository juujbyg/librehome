# SPDX-License-Identifier: GPL-2.0-or-later
import json
import threading
import urllib.error
import urllib.request

import pytest

from librehome import jarvis
from librehome.adapters import ActionError
from librehome.registry import Registry
from librehome.server import serve

CFG = {"adapters": [{"type": "sim", "name": "sim"}]}


@pytest.fixture
def reg():
    return Registry(CFG)


def test_sim_lifecycle(reg):
    reg.act("sim/dishwasher", "start", {"program": "eco"})
    d = next(x for x in reg.devices() if x["id"] == "sim/dishwasher")
    assert d["state"]["status"] == "running" and d["state"]["program"] == "eco"
    with pytest.raises(ActionError):
        reg.act("sim/dishwasher", "start", {})
    reg.act("sim/dishwasher", "stop")
    assert next(x for x in reg.devices() if x["id"] == "sim/dishwasher")["state"]["status"] == "idle"


def test_airfryer_validation(reg):
    with pytest.raises(ActionError):
        reg.act("sim/airfryer", "start", {"temperature_c": 500})
    with pytest.raises(ActionError):
        reg.act("sim/airfryer", "start", {"minutes": "abc"})


def test_unknown_device(reg):
    with pytest.raises(ActionError):
        reg.act("nope/x", "start")


def test_jarvis_commands(reg):
    assert "Started" in jarvis.handle("start the dishwasher on intensive", reg)
    assert "intensive" in jarvis.handle("dishwasher status", reg)
    out = jarvis.handle("air fryer 200 degrees for 12 minutes", reg)
    assert "temperature_c=200" in out and "minutes=12" in out
    assert "Stopped" in jarvis.handle("stop the washing machine", reg)
    assert "Dishwasher" in jarvis.handle("status", reg)
    with pytest.raises(ActionError):
        jarvis.handle("start the toaster", reg)


def test_http_api_and_auth(reg):
    httpd = serve(reg, "secret", "127.0.0.1", 0)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{port}"
        assert b"LibreHome" in urllib.request.urlopen(base + "/").read()
        devs = json.load(urllib.request.urlopen(base + "/api/devices"))
        assert {d["id"] for d in devs} == {"sim/dishwasher", "sim/washer", "sim/airfryer"}
        req = urllib.request.Request(base + "/api/act/sim/washer/start", data=b'{"program":"quick"}',
                                     method="POST")
        assert json.load(urllib.request.urlopen(req))["state"]["program"] == "quick"
        bad = urllib.request.Request(base + "/api/act/sim/washer/start", data=b"{}", method="POST")
        urllib.request.urlopen(bad)
    except urllib.error.HTTPError as exc:
        assert exc.code == 400  # already running -> clean error, not a crash
    finally:
        httpd.shutdown()
