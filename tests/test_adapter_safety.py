# SPDX-License-Identifier: GPL-2.0-or-later
import pytest

from librehome.adapters import ActionError
from librehome.adapters.homeassistant import HomeAssistantAdapter
from librehome.adapters.http import _fill


class FakeHA(HomeAssistantAdapter):
    def __init__(self):
        super().__init__({"type": "homeassistant", "url": "http://ha", "token": "t"})
        self.calls = []

    def _call(self, path, body=None):
        if path == "/api/states":
            return [{"entity_id": "switch.dishwasher", "state": "off",
                     "attributes": {"friendly_name": "Dishwasher"}},
                    {"entity_id": "script.wipe_everything", "state": "off", "attributes": {}}]
        self.calls.append((path, body))
        return []


def test_ha_start_maps_to_turn_on():
    ha = FakeHA()
    ha.act("switch.dishwasher", "start", {})
    assert ha.calls == [("/api/services/switch/turn_on", {"entity_id": "switch.dishwasher"})]


@pytest.mark.parametrize("device, params", [
    ("script.wipe_everything", {}),                              # domain not exposed
    ("switch.unknown", {}),                                      # entity not listed
    ("switch.dishwasher", {"service": "../../config/core/restart"}),  # path injection
])
def test_ha_rejects_unlisted_or_unsafe(device, params):
    ha = FakeHA()
    with pytest.raises(ActionError):
        ha.act(device, "service" if params else "start", params)
    assert ha.calls == []


def test_ha_cannot_retarget_entity():
    ha = FakeHA()
    ha.act("switch.dishwasher", "service", {"service": "toggle", "entity_id": "lock.front_door"})
    assert ha.calls[0][1]["entity_id"] == "switch.dishwasher"


def test_http_url_params_are_encoded():
    url = _fill("http://192.168.1.50/start?t={t}", {"t": "1@evil.com/x?y=1#"}, url=True)
    assert url == "http://192.168.1.50/start?t=1%40evil.com%2Fx%3Fy%3D1%23"
