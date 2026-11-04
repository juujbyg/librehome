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


@pytest.fixture
def hub(reg):
    httpd = serve(reg, "secret", "127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def call(url, data=None, headers=None, method=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


AUTH = {"X-Token": "secret", "Content-Type": "application/json"}


def test_api_works_with_token(hub):
    status, body = call(hub + "/api/devices", headers=AUTH)
    assert status == 200
    assert {d["id"] for d in json.loads(body)} == {"sim/dishwasher", "sim/washer", "sim/airfryer"}
    status, body = call(hub + "/api/act/sim/washer/start", b'{"program":"quick"}', AUTH, "POST")
    assert status == 200 and json.loads(body)["state"]["program"] == "quick"
    status, body = call(hub + "/api/act/sim/washer/start", b"{}", AUTH, "POST")
    assert status == 400 and b"already running" in body  # clean error, not a crash


def test_localhost_needs_token_too(hub):
    # A website open in the browser can reach 127.0.0.1; without the token it must get nothing.
    assert call(hub + "/api/devices")[0] == 401
    assert call(hub + "/api/command", b'{"text":"start the dishwasher"}',
                {"Content-Type": "text/plain"}, "POST")[0] == 401
    assert call(hub + "/api/devices?token=secret")[0] == 401  # header only


def test_form_posts_are_rejected(hub):
    status, _ = call(hub + "/api/command", b'{"text":"status"}',
                     {"X-Token": "secret", "Content-Type": "text/plain"}, "POST")
    assert status == 400


def test_dns_rebinding_is_blocked(hub):
    assert call(hub + "/", headers={"Host": "evil.example.com"})[0] == 403
    assert call(hub + "/api/devices", headers={**AUTH, "Host": "evil.example.com"})[0] == 403


def test_token_only_embedded_for_local_page(hub):
    status, page = call(hub + "/")
    assert status == 200 and b'content="secret"' in page
    port = hub.rsplit(":", 1)[1]
    status, page = call(hub + "/", headers={"Host": f"192.168.1.20:{port}"})
    assert status == 200 and b"secret" not in page
