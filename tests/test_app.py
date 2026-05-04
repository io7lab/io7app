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


def test_tls_auto_detect_from_kwarg(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IO7_SERVER", "h")
    monkeypatch.setenv("IO7_APP_ID", "a")
    monkeypatch.setenv("IO7_TOKEN", "t")
    (tmp_path / "myca.pem").write_text("dummy")
    app = App(ca=str(tmp_path / "myca.pem"), _connect=False)
    assert app.ca == str(tmp_path / "myca.pem")
    assert app.port == 8883


def test_tls_auto_detect_from_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IO7_SERVER", "h")
    monkeypatch.setenv("IO7_APP_ID", "a")
    monkeypatch.setenv("IO7_TOKEN", "t")
    monkeypatch.setenv("IO7_CA", "envca.pem")
    app = App(_connect=False)
    assert app.ca == "envca.pem"
    assert app.port == 8883


def test_tls_auto_detect_from_capem_in_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IO7_SERVER", "h")
    monkeypatch.setenv("IO7_APP_ID", "a")
    monkeypatch.setenv("IO7_TOKEN", "t")
    monkeypatch.delenv("IO7_CA", raising=False)
    (tmp_path / "ca.pem").write_text("dummy")
    app = App(_connect=False)
    assert app.ca == "ca.pem"
    assert app.port == 8883


def test_no_tls_default_port_1883(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IO7_SERVER", "h")
    monkeypatch.setenv("IO7_APP_ID", "a")
    monkeypatch.setenv("IO7_TOKEN", "t")
    monkeypatch.delenv("IO7_CA", raising=False)
    app = App(_connect=False)
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


def test_utf8_format_no_unwrap(app, fake_client):
    seen = []
    @app.on("iot3/lamp1/evt/status/fmt/utf8")
    def h(data):
        seen.append(data)
    fake_client.deliver("iot3/lamp1/evt/status/fmt/utf8", "hello")
    assert seen == ["hello"]
