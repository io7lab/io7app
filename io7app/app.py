"""App class: wires paho-mqtt, Router, Scheduler."""
import inspect
import json
import logging
import os
from typing import Optional

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

from io7app.router import Router
from io7app.scheduler import Scheduler

log = logging.getLogger("io7app")


class _DropMessage(Exception):
    """Internal: raise to indicate a message should be silently dropped."""


_VALID_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def _configure_logger(level_name: str) -> None:
    """Set the io7app logger level and ensure it has at least one handler.
    Idempotent — safe to call multiple times. Does not touch the root logger."""
    name = (level_name or "ERROR").upper()
    if name not in _VALID_LOG_LEVELS:
        raise ValueError(
            f"IO7_LOG must be one of {', '.join(_VALID_LOG_LEVELS)}, got {level_name!r}"
        )
    logger = logging.getLogger("io7app")
    logger.setLevel(getattr(logging, name))
    # Add a stream handler only when no logging is configured at all
    # (no handlers on us AND no handlers on root). Keep propagate=True so
    # pytest's caplog and any user-installed handlers still see our records.
    if not logger.handlers and not logging.getLogger().handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s io7app: %(message)s",
            datefmt="%H:%M:%S",
        ))
        logger.addHandler(h)


def _build_mqtt_client(app_id: str, token: str, ca: str | None) -> mqtt.Client:
    # paho 2.x prefers VERSION2 callbacks (V1 is deprecated).
    # paho 1.x has no CallbackAPIVersion at all.
    api_kw = {}
    if hasattr(mqtt, "CallbackAPIVersion"):
        api_kw["callback_api_version"] = mqtt.CallbackAPIVersion.VERSION2
    client = mqtt.Client(client_id=app_id, clean_session=True, **api_kw)
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
        log_level: Optional[str] = None,
        env_path: str = ".env",
        _connect: bool = True,  # test hook to skip MQTT connect
    ):
        # 1. Load .env if present
        if env_path and os.path.exists(env_path):
            load_dotenv(env_path, override=False)

        # 2. Configure logger (kwarg > IO7_LOG env > default ERROR)
        _configure_logger(log_level or os.getenv("IO7_LOG") or "ERROR")

        # 3. Resolve config: kwargs > env vars
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

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        # paho v2 callback (5 args incl. properties); v1 (4 args incl. rc)
        # both dispatch here. v1 reason_code is an int rc; v2 is a ReasonCode
        # object exposing .is_failure and string formatting.
        failed = getattr(reason_code, "is_failure", reason_code != 0)
        if failed:
            log.warning("io7 connect failed: %s", reason_code)
            return
        log.info("io7 connected as %s", self.app_id)
        # Re-subscribe to all currently-registered patterns.
        # Use the `client` arg paho passes us (safer if reconnect ever
        # rebuilds self._client) rather than self._client directly.
        for pattern in self._router.all_patterns():
            client.subscribe(pattern)

    def on(self, pattern: str):
        """Decorator: register `fn` as a handler for the topic `pattern`."""
        def decorator(fn):
            name = fn.__name__
            is_new = self._router.add(pattern, fn, name)
            log.info("registered %r on %s%s", name, pattern,
                     "" if is_new else " (existing pattern)")
            if is_new and self._client is not None:
                self._client.subscribe(pattern)
            return fn
        return decorator

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        raw = msg.payload
        entries = self._router.dispatch(topic)
        log.debug("recv %s (%d bytes) -> %d handler(s)", topic, len(raw), len(entries))
        if not entries:
            return
        for entry in entries:
            try:
                args = self._decode_for_entry(topic, raw, entry)
            except _DropMessage:
                continue
            try:
                self._invoke(entry.handler, topic, args["data"], args["t"])
            except Exception:
                log.exception("handler %r raised on topic %s", entry.name, topic)

    def _decode_for_entry(self, topic, raw, entry):
        fmt = entry.fmt
        if fmt == "json":
            try:
                body = json.loads(raw)
            except (ValueError, TypeError):
                log.warning("malformed json on %s", topic)
                raise _DropMessage
            if not isinstance(body, dict) or "d" not in body:
                raise _DropMessage  # silent drop per PRD #7
            return {"data": body["d"], "t": body.get("t")}
        if fmt == "utf8":
            try:
                return {"data": raw.decode("utf-8"), "t": None}
            except UnicodeDecodeError:
                raise _DropMessage
        # raw bytes
        return {"data": bytes(raw), "t": None}

    def _invoke(self, fn, topic, data, t):
        sig = self._sig_cache(fn)
        params = list(sig.parameters)
        n = len(params)
        wants_t = "t" in sig.parameters
        # Pass t as a kwarg so both positional and keyword-only `t` parameters work.
        if n == 1:
            fn(data)
        elif n == 2 and not wants_t:
            fn(topic, data)
        elif n == 2 and wants_t:
            fn(data, t=t)
        elif n == 3 and wants_t:
            fn(topic, data, t=t)
        else:
            raise TypeError(
                f"unsupported handler signature for {fn.__name__}: {sig}"
            )

    def _sig_cache(self, fn):
        cache = getattr(self, "_sigs", None)
        if cache is None:
            cache = self._sigs = {}
        s = cache.get(fn)
        if s is None:
            s = inspect.signature(fn)
            cache[fn] = s
        return s

    def on_event(self, device_id: str, event_id: str, fmt: str = "json"):
        topic = f"iot3/{device_id}/evt/{event_id}/fmt/{fmt}"
        return self.on(topic)

    def send_cmd(self, device_id: str, cmd_id: str, data, *,
                 fmt: str = "json", qos: int = 0, retain: bool = False):
        topic = f"iot3/{device_id}/cmd/{cmd_id}/fmt/{fmt}"
        # The {"d": ...} envelope is a JSON convention. For non-json formats
        # the caller passes the wire payload directly (str for utf8, bytes for raw).
        if fmt == "json":
            payload = json.dumps({"d": data}).encode()
        elif fmt == "utf8":
            payload = data.encode() if isinstance(data, str) else bytes(data)
        else:
            payload = data  # caller passes bytes for raw fmts
        log.debug("send_cmd %s (%d bytes)", topic, len(payload))
        self._client.publish(topic, payload, qos=qos, retain=retain)

    def publish(self, topic: str, payload, *,
                fmt: str = "json", qos: int = 0, retain: bool = False):
        if fmt == "json":
            body = json.dumps(payload).encode()
        elif fmt == "utf8":
            body = payload.encode() if isinstance(payload, str) else bytes(payload)
        else:
            body = payload  # bytes
        self._client.publish(topic, body, qos=qos, retain=retain)

    def inject(self, *, every=None, cron=None, at=None,
               at_start=False, payload=None):
        def decorator(fn):
            self._scheduler.schedule(
                fn.__name__, fn,
                every=every, cron=cron, at=at,
                at_start=at_start, payload=payload,
            )
            return fn
        return decorator

    def unregister(self, name: str) -> None:
        emptied = self._router.remove_by_name(name)
        if self._client is not None:
            for pattern in emptied:
                log.info("unsubscribe %s (handler %r removed)", pattern, name)
                self._client.unsubscribe(pattern)
        # Cancel any inject by this name
        if self._scheduler.cancel(name):
            log.info("inject %r cancelled", name)

    def run(self, _block: bool = True):
        """Connect to broker, start scheduler, block on the MQTT loop."""
        if self._client is None:
            self._build_client()
        self._client.connect(self.server, self.port, keepalive=60)
        self._scheduler.start()
        self._running = True
        if _block:
            try:
                self._client.loop_forever()
            except KeyboardInterrupt:
                pass
            finally:
                self.stop()
        else:
            self._client.loop_start()

    def stop(self):
        if not self._running:
            return
        self._running = False
        self._scheduler.stop()
        if self._client is not None:
            try:
                self._client.loop_stop()
            except Exception:
                pass
            self._client.disconnect()
