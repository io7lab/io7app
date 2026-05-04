# io7app — User Guide

`io7app` is a small Python framework for writing **io7 IoT app servers**.

You write the business logic — "if a switch flips, mirror it to the lamp", "if it's 7am, turn the heater on". The framework handles the MQTT connection, topic subscriptions, envelope wrapping, scheduling, and dynamic register/unregister.

> **The io7 platform.** Devices publish *events* and receive *commands* through an MQTT broker. Apps subscribe to events and publish commands. This library implements only the **App** side. There can be many devices but typically one app per process.

---

## 1. Install and configure

```bash
pip install io7app
```

Create a `.env` file in your project directory:

```
IO7_SERVER=iot201.ddns.net
IO7_APP_ID=app3
IO7_TOKEN=app3
# IO7_PORT=1883      # optional, default 1883 (or 8883 with TLS)
# IO7_CA=ca.pem      # optional, enables TLS on 8883
# IO7_LOG=ERROR      # DEBUG | INFO | WARNING | ERROR | CRITICAL (default ERROR)
```

TLS is auto-detected: if `IO7_CA` is set, or if a file named `ca.pem` exists in the working directory, the connection upgrades to TLS on port 8883. Same convention as `io7lab/IO7FuPython`.

**Logging.** Set `IO7_LOG=DEBUG` (or `INFO`) when developing — you'll see registered handlers, every received message with handler count, every command published, and inject fires. Defaults to `ERROR` so a production app stays quiet. You can also override per-instance: `App(log_level="DEBUG")`. The framework only configures its own `io7app` logger and adds a stream handler if you don't already have one — your own logging setup is left alone.

Tested by: `test_app.py::test_env_loaded`, `test_app.py::test_tls_auto_detect_from_kwarg`, `::test_tls_auto_detect_from_env`, `::test_tls_auto_detect_from_capem_in_cwd`, `::test_no_tls_default_port_1883`, `::test_log_level_default_is_error`, `::test_log_level_from_env`, `::test_log_level_kwarg_wins`, `::test_log_level_invalid_rejected`.

---

## 2. Your first app

```python
# switch_lamp.py
from io7app import App

app = App()

@app.on_event("switch1", "status")
def on_switch(data):
    app.send_cmd("lamp1", "lamp", {"lamp": data["switch"]})

app.run()
```

Run it:

```bash
python switch_lamp.py
```

That's the whole app. When `switch1` publishes `{"d": {"switch": "on"}}` to `iot3/switch1/evt/status/fmt/json`, the framework:

1. Receives the message,
2. Decodes JSON, unwraps `d`, hands `{"switch": "on"}` to `on_switch`,
3. `send_cmd` re-wraps as `{"d": {"lamp": "on"}}` and publishes to `iot3/lamp1/cmd/lamp/fmt/json`.

User code never writes `payload["d"]["switch"]` and never builds the topic string by hand.

Tested by: `test_app.py::test_switch_lamp_round_trip`.

---

## 3. Listening to events

### 3.1 `@app.on_event(device, event)` — the common case

```python
@app.on_event("thermo1", "status")
def thermostat(data):
    print(data["temperature"])
```

Subscribes to `iot3/thermo1/evt/status/fmt/json`. Wildcards work too:

```python
@app.on_event("+", "status")        # status from any device
@app.on_event("thermo1", "+")       # any event from thermo1
```

Tested by: `test_app.py::test_on_event_topic_built`, `::test_on_event_with_wildcards`, `test_router.py::test_single_wildcard_plus`, `::test_multi_wildcard_hash`, `::test_hash_with_plus_combined`.

### 3.2 `@app.on(pattern)` — raw topic for full power

When you need a non-`evt` topic, or arbitrary wildcards:

```python
@app.on("iot3/+/evt/+/fmt/json")
def trace(topic, data):
    print(topic, data)
```

Tested by: `test_app.py::test_on_decorator_registers_and_subscribes`, `::test_signature_two_args_topic_data`.

### 3.3 Handler signatures

The framework inspects your handler and calls it with what it asks for:

| Your signature | Framework calls with |
|---|---|
| `f(data)` | unwrapped `d` |
| `f(topic, data)` | topic + unwrapped `d` |
| `f(data, t)` | `d` + timestamp (or `None`) |
| `f(topic, data, t)` | all three |

Detection rule: parameter **count** picks topic vs data; presence of a parameter **named `t`** opts into the timestamp.

```python
@app.on_event("thermo1", "status")
def log(data, t):
    print(f"{t}: {data['temperature']}°C")
```

`t` is whatever the device sent (epoch ms or ISO string — pass-through, no parsing). `None` if the envelope had no `t`.

Tested by: `test_app.py::test_signature_one_arg`, `::test_signature_two_args_topic_data`, `::test_signature_with_t`, `::test_signature_with_topic_and_t`, `::test_signature_with_keyword_only_t`, `::test_t_none_when_envelope_missing_t`.

### 3.4 The `d` envelope contract (PRD #7)

io7 messages are `{"d": <data>, "t": <optional>}`. The framework:

- **Silently drops** any `/fmt/json` message that isn't a dict, or has no `"d"` key. Your handler is not called. No log noise.
- **Hands you `data`** (the inner value of `"d"`) directly. You never write `payload["d"]`.

```python
# Device publishes:        {"d": {"temperature": 23.4}, "t": 1714800000000}
# Your handler receives:   data = {"temperature": 23.4}, t = 1714800000000

# Device publishes:        {"oops": "no d here"}
# Your handler:            not called.
```

For non-JSON formats:
- `/fmt/utf8` → `data` is the decoded string; `t` is always `None`; no `d` requirement.
- Any other format → `data` is raw `bytes`.

Tested by: `test_app.py::test_unwraps_d`, `::test_drops_when_no_d`, `::test_drops_when_not_dict`, `::test_drops_malformed_json`, `::test_utf8_format_no_unwrap`.

---

## 4. Sending commands

```python
app.send_cmd("lamp1", "lamp", {"lamp": "on"})
# → publishes {"d": {"lamp": "on"}} to iot3/lamp1/cmd/lamp/fmt/json
```

`send_cmd(device_id, cmd_id, data)` auto-wraps: you pass the meaningful data, the framework adds the `"d":` envelope. Optional kwargs: `fmt="json"`, `qos=0`, `retain=False`.

Tested by: `test_app.py::test_switch_lamp_round_trip`, `::test_send_cmd_utf8_does_not_repr_dict`, `::test_send_cmd_raw_bytes_passthrough`.

### Raw publish (escape hatch)

For non-`iot3/` topics (dashboards, internal monitoring) where you supply the full body:

```python
app.publish("dashboard/status", {"alive": True})
```

Does **not** auto-wrap. You're responsible for the body shape. The broker's ACL still rejects any attempt to publish to an `evt` topic from an app credential.

Tested by: `test_app.py::test_publish_raw_no_wrap`.

---

## 5. Scheduling with `@app.inject`

Mimics Node-RED's inject node — fire a handler on a schedule.

```python
@app.inject(every=60)                       # every 60 seconds
def heartbeat(data):
    app.send_cmd("watchdog", "ping", {"alive": True})

@app.inject(cron="0 7 * * *", payload={"lamp": "on"})
def morning(data):                          # daily 07:00
    app.send_cmd("lamp1", "lamp", data)

@app.inject(at="22:00", at_start=True)      # daily 22:00, also fire on startup
def night(data):
    app.send_cmd("lamp1", "lamp", {"lamp": "off"})
```

Modes (mutually exclusive):
- `every=N` — fire every N seconds
- `cron="m h dom mon dow"` — standard 5-field cron (requires `pip install croniter`)
- `at="HH:MM"` — daily at local time

Orthogonal flag: `at_start=True` also fires once when `app.run()` starts.

Optional: `payload=<dict>` becomes the `data` argument to your handler. `None` if omitted.

Inject handlers also get `t` (the wall-clock fire time as `time.time()` float) if they declare it.

Tested by: `test_scheduler.py::test_every_fires_repeatedly`, `::test_at_start_fires_immediately`, `::test_at_mode_computes_next_fire`, `::test_at_mode_invalid_format_rejected`, `::test_cron_mode_fires`, `::test_cron_mode_validates_at_register`, `::test_inject_with_t_param`.

---

## 6. Dynamic register / unregister

Decorators register at import time, but you can also unregister at runtime by **function name**:

```python
@app.on("iot3/+/evt/+/fmt/json")
def trace(topic, data):
    print(topic, data)

# Later:
app.unregister("trace")
```

`unregister(name)` removes:
- every router entry whose handler `__name__` is `name`,
- every inject thread for that name.

If a topic pattern has no remaining handlers, the framework calls `client.unsubscribe(pattern)` so the broker stops sending those messages — saves bandwidth.

Tested by: `test_app.py::test_unregister_removes_handler`, `::test_unregister_unsubscribes_when_pattern_empty`, `::test_unregister_keeps_pattern_alive_if_other_handlers`, `::test_unregister_cancels_inject`.

---

## 7. Optimization the framework does for you

### 7.1 Storage tiers (zero user effort)

- Static topics → O(1) dict lookup at dispatch time.
- `+` patterns → compiled regex, cached.
- `#` patterns → compiled regex, cached.

### 7.2 Registration consolidation (PRD #2)

When you stack decorators or register the same handler under multiple patterns, the framework consolidates them so the same message never fires the handler twice:

```python
@app.on("iot3/+/evt/status/fmt/json")
@app.on("iot3/lamp1/evt/status/fmt/json")   # subsumed by the line above
def react(data): ...
```

Warning emitted:

```
WARNING io7app: handler 'react' new pattern 'iot3/lamp1/evt/status/fmt/json'
        is covered by existing 'iot3/+/evt/status/fmt/json'; ignoring
```

Rules applied per handler name:

| Case | Action |
|---|---|
| Exact duplicate | drop new, WARN |
| New is subsumed by existing | drop new, WARN |
| Existing is subsumed by new | replace existing with new (broader covers narrower), WARN |
| Pure overlap (neither subsumes) | keep both, WARN — handler may fire twice for those topics |
| Disjoint | keep both, no log |

Tested by: `test_router.py::test_consolidation_exact_dup`, `::test_consolidation_subsumed`, `::test_consolidation_replace_narrower`, `::test_consolidation_pure_overlap_warns`.

---

## 8. Cookbook examples

Each is a runnable file under `examples/`. Tested by an integration test that imports the module and asserts the expected handler is registered for the expected topic.

| File | What it does | Test |
|---|---|---|
| `01_switch_lamp.py` | switch1 → lamp1 mirror | `test_examples.py::test_switch_lamp` |
| `02_thermostat_valve.py` | thermo1 temperature drives valve1 with hysteresis | `test_examples.py::test_thermostat_valve` |
| `03_lux_auto_lamp.py` | lux1 turns lamp1 on at low light | `test_examples.py::test_lux_auto_lamp` |
| `04_scheduled_inject.py` | daily morning lamp on (cron) + periodic command refresh | `test_examples.py::test_scheduled_inject` |
| `05_wildcard_trace.py` | log all events from any device, then unregister after delay | `test_examples.py::test_wildcard_trace` |

---

## 9. Lifecycle

```python
app = App()                 # connects on .run()
@app.on_event(...)
def ...

app.run()                   # blocks; subscribes; starts scheduler; handles SIGINT
# app.stop()                # programmatic shutdown
```

`run()` handles reconnection automatically (paho's built-in 5s backoff). On reconnect, all currently-registered topic patterns are re-subscribed.

Tested by: `test_app.py::test_run_subscribes_all`, `::test_resubscribes_on_reconnect`.

---

## 10. What this library does *not* do

- It does not publish events. Events are a device-only capability in io7. There is no `publish_event` method.
- It does not run async/await. Handlers run on paho's MQTT thread; inject handlers run on dedicated threads.
- It does not persist state between runs. Use a file or a database if you need that.
- It does not provide a device-side library. Use `io7lab/IO7FuPython` or `IO7F32` for that.

---

## Documentation contract

Every claim in this guide is exercised by a test. If you find a behavior described here that the code doesn't honor, file a bug — the test should be failing too. The mapping is in the "Tested by:" tags throughout this document.
