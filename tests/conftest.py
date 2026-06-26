"""Shared test fixtures."""
import pytest


class FakeMessage:
    def __init__(self, topic, payload):
        self.topic = topic
        self.payload = payload if isinstance(payload, (bytes, bytearray)) else payload.encode()


class FakeMQTTClient:
    """Stands in for paho.mqtt.client.Client. Records calls and lets tests inject messages."""
    def __init__(self):
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self.published: list[tuple[str, bytes, int, bool]] = []
        self.connected = False
        self.tls_set_calls: list[dict] = []
        self.username_pw: tuple | None = None
        self.client_id = None
        self.on_connect = None
        self.on_message = None

    # paho-mqtt API surface used by App
    def username_pw_set(self, user, pw):
        self.username_pw = (user, pw)

    def tls_set(self, **kwargs):
        self.tls_set_calls.append(kwargs)

    def connect(self, host, port, keepalive=60):
        self.host = host
        self.port = port
        self.connected = True
        if self.on_connect:
            # paho v2 callback shape: (client, userdata, flags, reason_code, properties)
            self.on_connect(self, None, None, 0, None)

    def disconnect(self):
        self.connected = False

    def loop_start(self):
        pass

    def loop_forever(self):
        pass

    def loop_stop(self):
        pass

    def subscribe(self, topic, qos=0):
        self.subscribed.append(topic)

    def unsubscribe(self, topic):
        self.unsubscribed.append(topic)

    def publish(self, topic, payload, qos=0, retain=False):
        b = payload.encode() if isinstance(payload, str) else payload
        self.published.append((topic, b, qos, retain))

    # Test helper
    def deliver(self, topic, payload):
        if self.on_message:
            self.on_message(self, None, FakeMessage(topic, payload))


@pytest.fixture
def fake_client():
    return FakeMQTTClient()


@pytest.fixture
def app(monkeypatch, tmp_path, fake_client):
    """Build an App with FakeMQTTClient injected."""
    from io7app.app import App
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IO7_SERVER", "h")
    monkeypatch.setenv("IO7_APP_ID", "testapp")
    monkeypatch.setenv("IO7_TOKEN", "t")
    monkeypatch.delenv("IO7_CA", raising=False)
    # App now builds the paho client inline in _build_client(); patch the
    # mqtt.Client constructor itself so our fake is returned instead.
    monkeypatch.setattr(
        "io7app.app.mqtt.Client",
        lambda *args, **kwargs: fake_client,
    )
    a = App(_connect=True)
    return a
