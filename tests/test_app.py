import ssl

import pytest
from io7app.app import App


def test_kwargs_override_env(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("IO7_SERVER=fromenv\nIO7_APP_ID=A\nIO7_TOKEN=T\n")
    monkeypatch.chdir(tmp_path)
    app = App(server="explicit", env_path=str(env_file), _connect=False)
    assert app.server == "explicit"
    assert app.app_id == "A"
    assert app.token == "T"


def test_env_loaded(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("IO7_SERVER=fromenv\nIO7_APP_ID=A\nIO7_TOKEN=T\n")
    monkeypatch.chdir(tmp_path)
    app = App(env_path=str(env_file), _connect=False)
    assert app.server == "fromenv"
    assert app.app_id == "A"
    assert app.token == "T"


def test_missing_config_raises(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("IO7_SERVER", raising=False)
    monkeypatch.delenv("IO7_APP_ID", raising=False)
    monkeypatch.delenv("IO7_TOKEN", raising=False)
    with pytest.raises(RuntimeError):
        App(_connect=False)


# NOTE: the effective port default (8883 with TLS, 1883 without) is resolved
# in _build_client() at connect time, not in __init__. So these tests build
# the client (with the fake injected) before asserting the port.

def test_tls_auto_detect_from_kwarg(tmp_path, monkeypatch, fake_client):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IO7_SERVER", "h")
    monkeypatch.setenv("IO7_APP_ID", "a")
    monkeypatch.setenv("IO7_TOKEN", "t")
    monkeypatch.setattr("io7app.app.mqtt.Client", lambda *a, **k: fake_client)
    (tmp_path / "myca.pem").write_text("dummy")
    app = App(ca=str(tmp_path / "myca.pem"), _connect=True)
    assert app.ca == str(tmp_path / "myca.pem")
    assert app.port == 8883


def test_tls_auto_detect_from_env(tmp_path, monkeypatch, fake_client):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IO7_SERVER", "h")
    monkeypatch.setenv("IO7_APP_ID", "a")
    monkeypatch.setenv("IO7_TOKEN", "t")
    monkeypatch.setenv("IO7_CA", "envca.pem")
    monkeypatch.setattr("io7app.app.mqtt.Client", lambda *a, **k: fake_client)
    app = App(_connect=True)
    assert app.ca == "envca.pem"
    assert app.port == 8883


def test_tls_auto_detect_from_capem_in_cwd(tmp_path, monkeypatch, fake_client):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IO7_SERVER", "h")
    monkeypatch.setenv("IO7_APP_ID", "a")
    monkeypatch.setenv("IO7_TOKEN", "t")
    monkeypatch.delenv("IO7_CA", raising=False)
    monkeypatch.setattr("io7app.app.mqtt.Client", lambda *a, **k: fake_client)
    (tmp_path / "ca.pem").write_text("dummy")
    app = App(_connect=True)
    assert app.ca == "ca.pem"
    assert app.port == 8883


def test_no_tls_default_port_1883(tmp_path, monkeypatch, fake_client):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IO7_SERVER", "h")
    monkeypatch.setenv("IO7_APP_ID", "a")
    monkeypatch.setenv("IO7_TOKEN", "t")
    monkeypatch.delenv("IO7_CA", raising=False)
    monkeypatch.setattr("io7app.app.mqtt.Client", lambda *a, **k: fake_client)
    app = App(_connect=True)
    assert app.ca is None
    assert app.port == 1883


def test_explicit_port_overrides_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IO7_SERVER", "h")
    monkeypatch.setenv("IO7_APP_ID", "a")
    monkeypatch.setenv("IO7_TOKEN", "t")
    (tmp_path / "ca.pem").write_text("dummy")
    app = App(port=9999, _connect=False)
    assert app.port == 9999


def test_port_from_env_is_int(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IO7_SERVER", "h")
    monkeypatch.setenv("IO7_APP_ID", "a")
    monkeypatch.setenv("IO7_TOKEN", "t")
    monkeypatch.delenv("IO7_CA", raising=False)
    monkeypatch.setenv("IO7_PORT", "1234")
    app = App(_connect=False)
    assert app.port == 1234
    assert isinstance(app.port, int)


def test_ignore_tls_verify_uses_cert_none_on_8883(tmp_path, monkeypatch, fake_client):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IO7_SERVER", "h")
    monkeypatch.setenv("IO7_APP_ID", "a")
    monkeypatch.setenv("IO7_TOKEN", "t")
    monkeypatch.delenv("IO7_CA", raising=False)
    monkeypatch.setenv("IO7_IGNORE_TLS_VERIFY", "1")
    monkeypatch.setattr("io7app.app.mqtt.Client", lambda *a, **k: fake_client)
    app = App(_connect=True)
    assert app.port == 8883
    assert fake_client.tls_set_calls == [{"ca_certs": None, "cert_reqs": ssl.CERT_NONE}]


# --- IO7_LOG / log_level handling ---

def test_log_level_default_is_error(tmp_path, monkeypatch):
    import logging
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IO7_SERVER", "h")
    monkeypatch.setenv("IO7_APP_ID", "a")
    monkeypatch.setenv("IO7_TOKEN", "t")
    monkeypatch.delenv("IO7_LOG", raising=False)
    App(_connect=False)
    assert logging.getLogger("io7app").level == logging.ERROR


def test_log_level_from_env(tmp_path, monkeypatch):
    import logging
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IO7_SERVER", "h")
    monkeypatch.setenv("IO7_APP_ID", "a")
    monkeypatch.setenv("IO7_TOKEN", "t")
    monkeypatch.setenv("IO7_LOG", "DEBUG")
    App(_connect=False)
    assert logging.getLogger("io7app").level == logging.DEBUG


def test_log_level_kwarg_wins(tmp_path, monkeypatch):
    import logging
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IO7_SERVER", "h")
    monkeypatch.setenv("IO7_APP_ID", "a")
    monkeypatch.setenv("IO7_TOKEN", "t")
    monkeypatch.setenv("IO7_LOG", "ERROR")
    App(log_level="INFO", _connect=False)
    assert logging.getLogger("io7app").level == logging.INFO


def test_log_level_invalid_rejected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IO7_SERVER", "h")
    monkeypatch.setenv("IO7_APP_ID", "a")
    monkeypatch.setenv("IO7_TOKEN", "t")
    monkeypatch.setenv("IO7_LOG", "VERBOSE")
    with pytest.raises(ValueError):
        App(_connect=False)


def test_paho_client_built_with_credentials(app, fake_client):
    assert fake_client.username_pw == ("testapp", "t")


# --- Task 15: @app.on decorator + envelope unwrap + signature dispatch ---

def test_on_decorator_registers_and_subscribes(app, fake_client):
    @app.on("iot3/lamp1/evt/status/fmt/json")
    def h(data):
        pass
    assert "iot3/lamp1/evt/status/fmt/json" in fake_client.subscribed


def test_unwraps_d(app, fake_client):
    seen = []
    @app.on("iot3/lamp1/evt/status/fmt/json")
    def h(data):
        seen.append(data)
    fake_client.deliver("iot3/lamp1/evt/status/fmt/json",
                        '{"d": {"lamp": "on"}, "t": 123}')
    assert seen == [{"lamp": "on"}]


def test_drops_when_no_d(app, fake_client):
    seen = []
    @app.on("iot3/lamp1/evt/status/fmt/json")
    def h(data):
        seen.append(data)
    fake_client.deliver("iot3/lamp1/evt/status/fmt/json", '{"oops": "no d"}')
    assert seen == []


def test_drops_when_not_dict(app, fake_client):
    seen = []
    @app.on("iot3/lamp1/evt/status/fmt/json")
    def h(data):
        seen.append(data)
    fake_client.deliver("iot3/lamp1/evt/status/fmt/json", '"just a string"')
    assert seen == []


def test_drops_malformed_json(app, fake_client, caplog):
    import logging
    seen = []
    @app.on("iot3/lamp1/evt/status/fmt/json")
    def h(data):
        seen.append(data)
    with caplog.at_level(logging.WARNING, logger="io7app"):
        fake_client.deliver("iot3/lamp1/evt/status/fmt/json", "{not json")
    assert seen == []
    assert any("malformed json" in r.message.lower() for r in caplog.records)


def test_signature_one_arg(app, fake_client):
    seen = []
    @app.on("iot3/lamp1/evt/status/fmt/json")
    def h(data):
        seen.append(data)
    fake_client.deliver("iot3/lamp1/evt/status/fmt/json", '{"d": {"x": 1}}')
    assert seen == [{"x": 1}]


def test_signature_two_args_topic_data(app, fake_client):
    seen = []
    @app.on("iot3/+/evt/+/fmt/json")
    def h(topic, data):
        seen.append((topic, data))
    fake_client.deliver("iot3/lamp1/evt/status/fmt/json", '{"d": {"x": 1}}')
    assert seen == [("iot3/lamp1/evt/status/fmt/json", {"x": 1})]


def test_signature_with_t(app, fake_client):
    seen = []
    @app.on("iot3/lamp1/evt/status/fmt/json")
    def h(data, t):
        seen.append((data, t))
    fake_client.deliver(
        "iot3/lamp1/evt/status/fmt/json", '{"d": {"x": 1}, "t": 999}')
    assert seen == [({"x": 1}, 999)]


def test_signature_with_topic_and_t(app, fake_client):
    seen = []
    @app.on("iot3/+/evt/+/fmt/json")
    def h(topic, data, t):
        seen.append((topic, data, t))
    fake_client.deliver(
        "iot3/lamp1/evt/status/fmt/json", '{"d": {"x": 1}, "t": 42}')
    assert seen == [("iot3/lamp1/evt/status/fmt/json", {"x": 1}, 42)]


def test_t_none_when_envelope_missing_t(app, fake_client):
    seen = []
    @app.on("iot3/lamp1/evt/status/fmt/json")
    def h(data, t):
        seen.append((data, t))
    fake_client.deliver("iot3/lamp1/evt/status/fmt/json", '{"d": {"x": 1}}')
    assert seen == [({"x": 1}, None)]


def test_signature_with_keyword_only_t(app, fake_client):
    """The spec lists `f(data, *, t=None)` — must work via keyword pass."""
    seen = []
    @app.on("iot3/lamp1/evt/status/fmt/json")
    def h(data, *, t=None):
        seen.append((data, t))
    fake_client.deliver(
        "iot3/lamp1/evt/status/fmt/json", '{"d": {"x": 1}, "t": 7}')
    assert seen == [({"x": 1}, 7)]


def test_handler_isolation_other_handlers_still_run(app, fake_client):
    """A raising handler must not block other handlers on the same topic."""
    seen = []
    @app.on("iot3/lamp1/evt/status/fmt/json")
    def boom(data):
        raise RuntimeError("intentional")
    @app.on("iot3/lamp1/evt/status/fmt/json")
    def survivor(data):
        seen.append(data)
    fake_client.deliver("iot3/lamp1/evt/status/fmt/json", '{"d": {"x": 1}}')
    assert seen == [{"x": 1}]


def test_utf8_format_no_unwrap(app, fake_client):
    seen = []
    @app.on("iot3/lamp1/evt/status/fmt/utf8")
    def h(data):
        seen.append(data)
    fake_client.deliver("iot3/lamp1/evt/status/fmt/utf8", "hello")
    assert seen == ["hello"]


# --- Task 16: on_event sugar + send_cmd ---

def test_on_event_topic_built(app, fake_client):
    @app.on_event("thermo1", "status")
    def h(data):
        pass
    assert "iot3/thermo1/evt/status/fmt/json" in fake_client.subscribed


def test_on_event_with_wildcards(app, fake_client):
    @app.on_event("+", "status")
    def h(topic, data):
        pass
    assert "iot3/+/evt/status/fmt/json" in fake_client.subscribed


def test_switch_lamp_round_trip(app, fake_client):
    @app.on_event("switch1", "status")
    def on_switch(data):
        app.send_cmd("lamp1", "lamp", {"lamp": data["switch"]})
    fake_client.deliver("iot3/switch1/evt/status/fmt/json",
                        '{"d": {"switch": "on"}}')
    assert fake_client.published, "no command published"
    topic, body, qos, retain = fake_client.published[0]
    assert topic == "iot3/lamp1/cmd/lamp/fmt/json"
    import json
    assert json.loads(body) == {"d": {"lamp": "on"}}


# --- Task 17: publish raw escape hatch ---

def test_publish_raw_no_wrap(app, fake_client):
    app.publish("dashboard/foo", {"alive": True})
    assert fake_client.published
    topic, body, _, _ = fake_client.published[0]
    assert topic == "dashboard/foo"
    import json
    assert json.loads(body) == {"alive": True}  # not wrapped in 'd'


def test_send_cmd_utf8_does_not_repr_dict(app, fake_client):
    """fmt='utf8' must send the raw string, not Python repr of {'d': ...}."""
    app.send_cmd("printer1", "label", "Hello\nWorld", fmt="utf8")
    topic, body, _, _ = fake_client.published[0]
    assert topic == "iot3/printer1/cmd/label/fmt/utf8"
    assert body == b"Hello\nWorld"


def test_send_cmd_raw_bytes_passthrough(app, fake_client):
    """fmt='bin' (anything not json/utf8) must pass bytes through verbatim."""
    app.send_cmd("modem1", "tx", b"\x01\x02\x03", fmt="bin")
    topic, body, _, _ = fake_client.published[0]
    assert topic == "iot3/modem1/cmd/tx/fmt/bin"
    assert body == b"\x01\x02\x03"


# --- Task 18: @app.inject decorator ---

def test_inject_registers_with_scheduler(app):
    @app.inject(every=0.05, payload={"k": 1})
    def heartbeat(data):
        pass
    # Job is registered; scheduler not started yet (run() does that)
    assert "heartbeat" in app._scheduler._jobs
    job = app._scheduler._jobs["heartbeat"]
    assert job.every == 0.05
    assert job.payload == {"k": 1}


def test_inject_validates_modes(app):
    import pytest
    with pytest.raises(ValueError):
        @app.inject()  # no mode
        def bad(d): pass


# --- Task 19: unregister ---

def test_unregister_removes_handler(app, fake_client):
    seen = []
    @app.on_event("lamp1", "status")
    def h(data):
        seen.append(data)
    fake_client.deliver("iot3/lamp1/evt/status/fmt/json", '{"d": {"x": 1}}')
    assert seen == [{"x": 1}]
    app.unregister("h")
    fake_client.deliver("iot3/lamp1/evt/status/fmt/json", '{"d": {"x": 2}}')
    assert seen == [{"x": 1}]  # no further calls


def test_unregister_unsubscribes_when_pattern_empty(app, fake_client):
    @app.on_event("lamp1", "status")
    def h(data):
        pass
    assert "iot3/lamp1/evt/status/fmt/json" in fake_client.subscribed
    app.unregister("h")
    assert "iot3/lamp1/evt/status/fmt/json" in fake_client.unsubscribed


def test_unregister_keeps_pattern_alive_if_other_handlers(app, fake_client):
    @app.on_event("lamp1", "status")
    def a(data):
        pass
    @app.on_event("lamp1", "status")
    def b(data):
        pass
    app.unregister("a")
    assert "iot3/lamp1/evt/status/fmt/json" not in fake_client.unsubscribed


def test_unregister_cancels_inject(app):
    @app.inject(every=0.05)
    def beat(data):
        pass
    assert "beat" in app._scheduler._jobs
    app.unregister("beat")
    assert "beat" not in app._scheduler._jobs


# --- Task 20: run/stop lifecycle ---

def test_run_subscribes_all(app, fake_client):
    @app.on_event("lamp1", "status")
    def a(data):
        pass
    @app.on_event("thermo1", "status")
    def b(data):
        pass
    app.run(_block=False)
    assert "iot3/lamp1/evt/status/fmt/json" in fake_client.subscribed
    assert "iot3/thermo1/evt/status/fmt/json" in fake_client.subscribed
    app.stop()


def test_resubscribes_on_reconnect(app, fake_client):
    @app.on_event("lamp1", "status")
    def a(data):
        pass
    fake_client.subscribed.clear()
    # Simulate paho firing on_connect again after a reconnect
    fake_client.on_connect(fake_client, None, None, 0)
    assert "iot3/lamp1/evt/status/fmt/json" in fake_client.subscribed


def test_stop_cancels_scheduler(app, fake_client):
    @app.inject(every=0.05)
    def beat(d): pass
    app.run(_block=False)
    app.stop()
    assert "beat" not in app._scheduler._jobs or \
           app._scheduler._jobs["beat"].stop_event.is_set()
