# SPDX-License-Identifier: GPL-2.0-or-later
import pytest
from fake_printer import serve

from librehome.adapters import ActionError
from librehome.protocols import mdns
from librehome.registry import Registry


@pytest.fixture
def printer():
    server, state = serve()
    entry = {"type": "ipp", "name": "printers", "discover": False,
             "printers": [{"name": "Fake Printer", "host": "127.0.0.1",
                           "port": server.server_address[1], "secure": False}]}
    yield Registry({"adapters": [entry]}), state
    server.shutdown()


def test_status_and_ink(printer):
    reg, _ = printer
    (dev,) = reg.devices()
    assert dev["id"] == "printers/fake-printer" and dev["online"]
    assert dev["state"]["status"] == "idle"
    assert dev["state"]["ink"] == {"Black": 64, "Tri-color": 8}


def test_print_and_cancel(printer):
    reg, state = printer
    out = reg.print_file("printers/fake-printer", "invoice.pdf", b"%PDF-1.4 fake")
    assert out["format"] == "application/pdf"
    attrs, payload = state.documents[out["job_id"]]
    assert payload == b"%PDF-1.4 fake" and attrs["job-name"] == ["invoice.pdf"]
    assert len(reg.devices()[0]["state"]["queue"]) == 1
    reg.act("printers/fake-printer", "cancel_all")
    assert reg.devices()[0]["state"]["queue"] == []


def test_unsupported_format_is_explained(printer):
    reg, _ = printer
    with pytest.raises(ActionError, match="can't read .docx"):
        reg.print_file("printers/fake-printer", "letter.docx", b"PK..")


def test_offline_printer_is_reported():
    entry = {"type": "ipp", "name": "p", "discover": False,
             "printers": [{"name": "Gone", "host": "127.0.0.1", "port": 9, "secure": False}]}
    (dev,) = Registry({"adapters": [entry]}).devices()
    assert not dev["online"] and dev["state"]["error"]


def test_mdns_assemble_prefers_ipps():
    records = [
        ("_ipp._tcp.local", mdns.TYPE_PTR, "HP._ipp._tcp.local"),
        ("_ipps._tcp.local", mdns.TYPE_PTR, "HP._ipps._tcp.local"),
        ("HP._ipp._tcp.local", mdns.TYPE_SRV, (631, "hp.local")),
        ("HP._ipps._tcp.local", mdns.TYPE_SRV, (631, "hp.local")),
        ("HP._ipp._tcp.local", mdns.TYPE_TXT, {"ty": "HP ENVY", "uuid": "u1"}),
        ("HP._ipps._tcp.local", mdns.TYPE_TXT, {"ty": "HP ENVY", "uuid": "u1"}),
        ("hp.local", mdns.TYPE_A, "192.168.1.9"),
    ]
    (p,) = mdns.assemble(records)
    assert p == {"name": "HP ENVY", "host": "192.168.1.9", "port": 631, "path": "/ipp/print", "secure": True}
