"""App class: wires paho-mqtt, Router, Scheduler."""
import json
import logging
import os
from typing import Optional

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

from io7app.router import Router
from io7app.scheduler import Scheduler

log = logging.getLogger("io7app")


def _build_mqtt_client(app_id: str, token: str, ca: str | None) -> mqtt.Client:
    client = mqtt.Client(client_id=app_id, clean_session=True)
    if ca:
        client.tls_set(ca_certs=ca)
    return client


class App:
    def __init__(
        self,
        server: Optional[str] = None,
        app_id: Optional[str] = None,
        token: Optional[str] = None,
        port: Optional[int] = None,
        ca: Optional[str] = None,
        env_path: str = ".env",
        _connect: bool = True,  # test hook to skip MQTT connect
    ):
        # 1. Load .env if present
        if env_path and os.path.exists(env_path):
            load_dotenv(env_path, override=False)

        # 2. Resolve config: kwargs > env vars
        self.server = server or os.getenv("IO7_SERVER")
        self.app_id = app_id or os.getenv("IO7_APP_ID")
        self.token = token or os.getenv("IO7_TOKEN")
        env_port = os.getenv("IO7_PORT")
        env_ca = os.getenv("IO7_CA")
        self.ca = ca if ca is not None else env_ca
        # Auto-detect ca.pem in cwd if no explicit ca
        if not self.ca and os.path.exists("ca.pem"):
            self.ca = "ca.pem"
        # Port default depends on TLS
        default_port = 8883 if self.ca else 1883
        if port is not None:
            self.port = port
        elif env_port:
            self.port = int(env_port)
        else:
            self.port = default_port

        missing = [k for k, v in (
            ("IO7_SERVER", self.server),
            ("IO7_APP_ID", self.app_id),
            ("IO7_TOKEN", self.token),
        ) if not v]
        if missing:
            raise RuntimeError(
                f"missing io7 config: {', '.join(missing)}. "
                f"Set them in .env or pass to App(server=, app_id=, token=)."
            )

        self._router = Router()
        self._scheduler = Scheduler()
        self._client = None
        self._running = False

        if _connect:
            self._build_client()

    @classmethod
    def from_env(cls, env_path: str = ".env", **kwargs):
        return cls(env_path=env_path, **kwargs)

    def _build_client(self):
        self._client = _build_mqtt_client(self.app_id, self.token, self.ca)
        self._client.username_pw_set(self.app_id, self.token)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, rc):
        if rc != 0:
            log.warning("io7 connect failed rc=%s", rc)
            return
        log.info("io7 connected as %s", self.app_id)
        # Re-subscribe to all currently-registered patterns
        for pattern in self._registered_patterns():
            self._client.subscribe(pattern)

    def _on_message(self, client, userdata, msg):
        # Filled in next task
        pass

    def _registered_patterns(self) -> set[str]:
        patterns: set[str] = set()
        patterns.update(self._router._exact.keys())
        patterns.update(p for _, _, p in self._router._single)
        patterns.update(p for _, _, p in self._router._multi)
        return patterns
