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
