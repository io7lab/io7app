import importlib.util
import sys
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def _load(modname, app_fixture, monkeypatch):
    """Patch App so the example's `App()` returns our test app, then import."""
    import io7app as io7app_pkg
    from io7app import app as app_mod
    monkeypatch.setattr(io7app_pkg, "App", lambda *a, **k: app_fixture)
    monkeypatch.setattr(app_mod, "App", lambda *a, **k: app_fixture)
    path = EXAMPLES / f"{modname}.py"
    spec = importlib.util.spec_from_file_location(modname, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[modname] = m
    # The example calls app.run(); patch run to no-op
    app_fixture.run = lambda *a, **k: None
    spec.loader.exec_module(m)
    return m


def test_switch_lamp(app, fake_client, monkeypatch):
    _load("01_switch_lamp", app, monkeypatch)
    assert "iot3/sw1/evt/status/fmt/json" in fake_client.subscribed
    fake_client.deliver("iot3/sw1/evt/status/fmt/json",
                        '{"d": {"switch": "on"}}')
    assert any(t == "iot3/lamp1/cmd/lamp/fmt/json"
               for t, *_ in fake_client.published)


def test_thermostat_valve(app, fake_client, monkeypatch):
    _load("04_thermostat_valve", app, monkeypatch)
    assert "iot3/thermo1/evt/status/fmt/json" in fake_client.subscribed
    # Cold reading drives valve on
    fake_client.deliver("iot3/thermo1/evt/status/fmt/json",
                        '{"d": {"temperature": 18.0, "target": 22.0}}')
    cmds = [t for t, *_ in fake_client.published]
    assert "iot3/valve1/cmd/valve/fmt/json" in cmds


def test_lux_lamp(app, fake_client, monkeypatch):
    _load("02_lux_lamp", app, monkeypatch)
    assert "iot3/lux1/evt/status/fmt/json" in fake_client.subscribed
    fake_client.deliver("iot3/lux1/evt/status/fmt/json", '{"d": {"lux": 10}}')
    assert any(t == "iot3/lamp1/cmd/lamp/fmt/json"
               for t, *_ in fake_client.published)


def test_scheduled_inject(app, fake_client, monkeypatch):
    _load("05_scheduled_inject", app, monkeypatch)
    assert any(name in app._scheduler._jobs
               for name in ("morning", "refresh"))


def test_wildcard_trace(app, fake_client, monkeypatch):
    _load("06_wildcard_trace", app, monkeypatch)
    assert "iot3/+/evt/+/fmt/json" in fake_client.subscribed


def test_lux_auto_lamp(app, fake_client, monkeypatch):
    import json as _json
    _load("03_lux_auto_lamp", app, monkeypatch)
    assert "iot3/lux1/evt/status/fmt/json" in fake_client.subscribed
    assert "iot3/sw1/evt/status/fmt/json" in fake_client.subscribed
    assert "iot3/lamp1/evt/status/fmt/json" in fake_client.subscribed

    def lamp_cmds():
        return [_json.loads(p)["d"]["lamp"] for t, p, *_ in fake_client.published
                if t == "iot3/lamp1/cmd/lamp/fmt/json"]

    def sw_syncs():
        return [t for t, *_ in fake_client.published
                if t == "iot3/sw1/cmd/update/fmt/json"]

    # the plain handlers drive the lamp on every report (idempotent)
    fake_client.deliver("iot3/lux1/evt/status/fmt/json", '{"d": {"lux": 150}}')
    fake_client.deliver("iot3/lux1/evt/status/fmt/json", '{"d": {"lux": 900}}')
    assert lamp_cmds() == ["on", "off"]
    fake_client.deliver("iot3/sw1/evt/status/fmt/json", '{"d": {"switch": "on"}}')
    assert lamp_cmds() == ["on", "off", "on"]

    # the ONE filter, on the lamp event: a state change syncs the switch...
    fake_client.deliver("iot3/lamp1/evt/status/fmt/json", '{"d": {"lamp": "on"}}')
    assert len(sw_syncs()) == 1
    # ...but the lamp's periodic republish / post-command echo dies at the
    # gate — this is what terminates the sw1 -> lamp1 -> sw1 echo loop.
    fake_client.deliver("iot3/lamp1/evt/status/fmt/json", '{"d": {"lamp": "on"}}')
    fake_client.deliver("iot3/lamp1/evt/status/fmt/json", '{"d": {"lamp": "on"}}')
    assert len(sw_syncs()) == 1
