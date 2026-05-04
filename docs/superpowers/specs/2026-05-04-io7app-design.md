# io7app — Python Framework for io7 IoT Apps

**Status:** design approved, ready for implementation plan
**Date:** 2026-05-04

## Goal

A small, intuitive Python framework that lets users build io7 IoT applications by decorating functions with the device/event topic they react to and the schedule they fire on. The framework owns MQTT connection, topic routing, payload (de)serialization, and scheduling. The user writes only business logic.

## Non-goals

- Async/await runtime (paho-mqtt thread + scheduler threads is enough for IoT app loads).
- Persistent state, retries, or backpressure beyond paho's defaults.
- A device-side library — io7lab already has `IO7FuPython` and `IO7F32` for that. This framework is for the **app side** only (see *io7 platform design* below).
- Helpers for unwrapping/wrapping the `{"d":...,"t":...}` envelope. Users handle the dict directly. May be added later.

## io7 platform design

The io7 IoT platform separates the world into two roles connected by an MQTT broker:

- **Devices** publish *events* (sensor readings, status changes) and receive *commands* (actuation requests). Device-side libraries: `IO7FuPython`, `IO7F32`, `IO7F8266`.
- **Apps** subscribe to *events* from one or more devices and publish *commands* to one or more devices. Apps embody the IoT business logic — "if temperature drops, turn the valve on", "when the switch flips, mirror it on the lamp".

```
┌────────────┐
│  Device 1  │ ─── evt ──▶ ┐                  ┌─────────────────┐
│ (thermo1)  │ ◀── cmd ─── │                  │                 │
└────────────┘             │                  │                 │
┌────────────┐             │   ┌──────────┐   │      App        │
│  Device 2  │ ─── evt ──▶ ├──▶│  Broker  │──▶│ (this framework,│
│  (valve1)  │ ◀── cmd ─── │   │(Mosquitto)│◀──│   one process) │
└────────────┘             │   └──────────┘   │                 │
   ...                     │                  │  evt → @on_event│
┌────────────┐             │                  │  cmd ← send_cmd │
│  Device N  │ ─── evt ──▶ ┘                  └─────────────────┘
│  (lamp1)   │ ◀── cmd ───
└────────────┘
   (many)                                          (one)
```

Many devices, one app: a single `App` instance subscribes to events from any number of devices and addresses commands to any of them by `device_id`. There is no built-in concept of a multi-app deployment — running multiple apps means running multiple Python processes, each with its own `IO7_APP_ID` and `.env`.

This framework implements the **App role**. Its capabilities are exactly the capabilities the io7 platform grants an app:

| io7 role | Subscribes to | Publishes to | This framework |
|---|---|---|---|
| Device | `cmd` topics for itself | `evt` topics for itself | out of scope |
| **App** | `evt` topics for any device | `cmd` topics for any device | **implemented** |

Apps do not publish events — that is a device-only capability in io7, enforced by the broker's ACL on the `appId` + token. The framework's API surface (`@app.on`, `@app.on_event`, `app.send_cmd`) maps directly to these role boundaries; there is no `publish_event` and there will not be one, because no app on this platform should call it.

### Topic conventions (from io7lab/IO7FuPython, io7lab/node-red-contrib-io7)

- **Events** (device → app): `iot3/{deviceId}/evt/{eventId}/fmt/{fmt}`
- **Commands** (app → device): `iot3/{deviceId}/cmd/{cmdId}/fmt/{fmt}`
- `fmt` is typically `json`. Standard payload envelope is `{"d": {...}, "t": optional_timestamp}`. Per PRD #7, the framework treats this envelope as a contract: messages without `"d"` are silently dropped, and outbound commands are auto-wrapped so user code only deals with the inner `data`.

## Architecture

```
┌────────────────────────────────────────────────┐
│                    App                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │  Router  │  │ paho     │  │  Scheduler   │  │
│  │ (exact + │←─│ MQTT     │  │ (1 thread    │  │
│  │  regex)  │  │ client   │  │  per inject) │  │
│  └──────────┘  └──────────┘  └──────────────┘  │
└────────────────────────────────────────────────┘
        ▲                              │
        │ @app.on / @app.on_event      │ @app.inject
        │ @app.unregister(name)        │
```

Three modules, each independently testable:

```
io7app/
  __init__.py        # public exports: App
  app.py             # App class, decorators, lifecycle, .env loading
  router.py          # topic matching: exact dict + DFA + multi-level regex
  scheduler.py       # inject scheduler (interval / cron / daily-at)
examples/
  01_switch_lamp.py
  02_thermostat_valve.py
  03_lux_auto_lamp.py
  04_heartbeat_inject.py
  05_wildcard_trace.py
tests/
  test_router.py
  test_scheduler.py
  test_app.py
.env.example
README.md
pyproject.toml         # minimal: name, deps, no install ceremony
```

## Public API

### `App` class

```python
App(server=None, app_id=None, token=None, port=None, ca=None, env_path=".env")
```

Constructor reads from environment if any of `server`/`app_id`/`token` is missing:
- `IO7_SERVER`, `IO7_APP_ID`, `IO7_TOKEN`, optional `IO7_PORT`, optional `IO7_CA`
- Loads `env_path` via `python-dotenv` if it exists; explicit kwargs always win.
- `App.from_env(path)` is an alias for `App(env_path=path)`.

**TLS/CA — same auto-detection rule as `io7lab/IO7FuPython`:**

The app picks transport in this order:
1. `ca=` kwarg (path to CA cert file) → TLS on port 8883.
2. `IO7_CA` env var (path to CA cert file) → TLS on port 8883.
3. `ca.pem` exists in cwd → TLS on port 8883 (auto-detect).
4. None of the above → plaintext on port 1883.

Explicit `port=` (or `IO7_PORT`) overrides the default port chosen above. TLS is implemented via paho's `client.tls_set(ca_certs=<path>)`; verification uses the system CA bundle plus the supplied CA. No client cert support in v1 (matches `IO7FuPython`).

Lifecycle:
- `app.run()` — connects, subscribes to all registered patterns, starts scheduler, blocks on MQTT loop. Handles SIGINT cleanly.
- `app.stop()` — disconnects, signals scheduler threads to exit.

Publishing — per the io7 App role, only commands are published:
- `app.send_cmd(device_id, cmd_id, data, fmt="json", qos=0, retain=False)`
  → wraps `data` as `{"d": data}` and publishes to `iot3/{device_id}/cmd/{cmd_id}/fmt/{fmt}`. Per PRD #7, the framework owns the envelope so user code passes only the meaningful payload (e.g. `{"lamp": "on"}`).
- `app.publish(topic, payload, fmt="json", qos=0, retain=False)`
  → raw publish escape hatch for non-`iot3/` topics (dashboards, internal monitoring). **Does not auto-wrap** — caller supplies the full body. The broker ACL still rejects any attempt to publish to an `evt` topic from an app credential.

Decorators (all return the original function unchanged):
- `@app.on(pattern)` — pattern is a full MQTT topic with optional `+` and `#` wildcards.
- `@app.on_event(device_id, event_id, fmt="json")` — sugar; `device_id` and `event_id` may be `"+"` for any.
- `@app.inject(every=None, cron=None, at=None, at_start=False, payload=None)` — see Scheduler section.

Multiple decorators stack: registering the same function under several topics or schedules is supported.

Unregistration:
- `app.unregister(name)` — removes every router entry and every inject thread whose function `__name__` equals `name`. Auto-unsubscribes from any pattern that no longer has handlers. Auto-cancels any inject thread for that name.

### Handler signatures and payload handling (PRD #7)

The io7 envelope is `{"d": <data>, "t": <optional_timestamp>}`. The framework owns the envelope so user code is simpler:

**Inbound (events):**
1. JSON-decode the body. Malformed JSON → log WARNING, drop.
2. If the decoded body is not a dict, or has no `"d"` key → **silently drop** (no log, no handler call). This is PRD #7's "if no 'd' just silently ignore."
3. Extract `data = body["d"]` and `t = body.get("t")`.
4. Call the handler with the shape its signature expects (see table below).

**Outbound (commands):** `app.send_cmd(device, cmd, data)` wraps automatically: the body sent on the wire is `{"d": data}`. User code never writes `{"d": ...}` for commands.

**Handler signatures** — chosen by parameter count and presence of a `t` parameter:

| Signature | Receives |
|---|---|
| `f(data)` | unwrapped `d` |
| `f(topic, data)` | topic + unwrapped `d` |
| `f(data, t)` *or* `f(data, *, t=None)` | `d` + timestamp (or `None` if envelope had no `t`) |
| `f(topic, data, t)` | all three |

Detection: parameter **count** picks topic/data shape; presence of a parameter **named `t`** opts into the timestamp pass-through. `t` is whatever the device sent (epoch ms or ISO string — no parsing).

For non-`/fmt/json` topics:
- `/fmt/utf8` → `data` is the decoded string; `t` is always `None`; no envelope unwrap (no `d` requirement).
- Other formats → `data` is raw `bytes`; `t` is always `None`.

For `@app.inject`, the framework hands the handler the `payload=` kwarg directly (no envelope; user-supplied). If the handler accepts `t`, the wall-clock fire time (`time.time()`) is passed.

## Components

### Router (`io7app/router.py`)

Ports the optimized matching from the existing `MQTTRouter.py` prototype, with three storage tiers:

- `_exact: dict[str, list[Entry]]` — O(1) lookup for static topics (no `+` or `#`).
- `_single: list[(compiled_regex, list[Entry], pattern)]` — patterns containing `+` only.
- `_multi: list[(compiled_regex, list[Entry], pattern)]` — patterns ending in `#`.

`Entry = (handler_callable, name, fmt)` where `fmt` is parsed from the pattern's last `fmt/{x}` segment for fast format-specific decoding at dispatch time.

```python
class Router:
    def add(self, pattern: str, handler, name: str) -> bool:
        """Register a handler. Returns True if pattern is new (caller must MQTT-subscribe)."""

    def remove_by_name(self, name: str) -> set[str]:
        """Remove every entry where entry.name == name.
        Returns the set of patterns that became empty (caller must MQTT-unsubscribe)."""

    def dispatch(self, topic: str, raw_payload: bytes) -> list[Entry]:
        """Return all handlers matching topic, in registration order."""
```

Pattern → regex compilation (only when wildcards present):
- `+` → `[^/]+`
- trailing `#` → `.*`
- All other characters `re.escape`d.

The dispatch path is hot — exact matches return immediately without entering the regex loops; this matches the prototype's design.

#### Registration-time consolidation (requirement #2)

When a new (handler_name, pattern) pair is registered, the router walks every existing registration for the same handler name and applies these rules:

| Case | Detection | Action | Log |
|---|---|---|---|
| Exact duplicate | `new == existing` | drop the new registration | WARNING |
| New is subsumed | every topic matching `new` also matches `existing` | drop the new registration | WARNING |
| Existing is subsumed | every topic matching `existing` also matches `new` | remove `existing`, install `new` | WARNING |
| Pure overlap (neither subsumes) | not provably subsumed either way | keep both | WARNING — "may fire twice for topics matching both" |
| Disjoint | no topic could match both | keep both | (silent) |

**Subsumption** is decided segment-by-segment on the pattern parts:
- `#` (must be the last segment per MQTT spec) covers all remaining segments → broader.
- `+` covers any single literal segment → broader than that literal at that position.
- Equal literals → match.
- Anything else → not subsumed.

A reference implementation lives in `router.py` as `_subsumes(broader, narrower) -> bool`.

**Overlap without subsumption** is not formally computed in v1 — the router emits a generic "may overlap" warning when neither side subsumes but a quick heuristic (same first literal segment, or both wildcard-heavy) suggests possible intersection. Real intersection detection is deferred until users hit it in practice.

Because the router holds a *minimal* set of patterns per handler after consolidation, dispatch is plain "collect all matching entries, call them in order" — no per-message dedup logic is needed.

#### Optimization on unregister (requirement #3)

`remove_by_name(name)` strips every entry for that name from all three tiers. After removal, any pattern with zero remaining handlers is reported back so `App` can `client.unsubscribe(pattern)` — the broker then stops sending those messages entirely. Empty regex objects and exact-match keys are evicted immediately to keep the dispatch path lean.

### Scheduler (`io7app/scheduler.py`)

One daemon thread per `@inject`. Each thread runs a small loop:

```python
while running:
    sleep_until_next()
    fire(name, fn, payload)
    next = compute_next()
```

Modes (mutually exclusive — exactly one of `every`/`cron`/`at` is required):
- `every=N` — fire every N seconds.
- `cron="m h dom mon dow"` — standard 5-field cron expression. Imports `croniter` lazily; raise a clear error if not installed.
- `at="HH:MM"` — fire daily at local time HH:MM.
- `at_start=True` — orthogonal flag: also fire once on startup, immediately when `app.run()` enters the loop.

`fire()` calls the user fn with the inspected signature (1-arg `fn(payload)` or 2-arg `fn(topic, payload)` where `topic` is `None` for inject calls). Exceptions are logged and swallowed.

```python
class Scheduler:
    def schedule(self, name, fn, *, every=None, cron=None, at=None,
                 at_start=False, payload=None) -> None
    def cancel(self, name: str) -> None
    def start(self) -> None       # starts all pending threads, fires at_start ones
    def stop(self) -> None        # signals all threads to exit, joins
```

### App (`io7app/app.py`)

Wires everything together. Key responsibilities:

1. **Config**: load `.env` if present, build connection params, fail fast with clear message if any of server/app_id/token is missing.
2. **paho client lifecycle**: `on_connect` re-subscribes to all router patterns (covers reconnect); `on_message` decodes and dispatches.
3. **Decorator implementation**: each decorator registers with router/scheduler and returns the original fn unchanged. The function's `__name__` is the canonical identifier for unregister.
4. **Decoding**: per-message — read fmt from the topic suffix, decode accordingly, log+drop on JSON parse error.
5. **Signature dispatch**: cache `inspect.signature(fn)` results per function; call with the right arity.

## Data flow

**Event:**
```
broker → paho on_message(topic, raw_bytes)
       → Router.dispatch(topic) → list of Entry (already deduplicated at registration)
       → for each Entry:
            decode raw_bytes per Entry.fmt
            (json fmt only) verify body is dict and has "d" — silently drop otherwise
            extract data = body["d"], t = body.get("t")
            inspect handler signature → call with the right shape:
              f(data) | f(topic, data) | f(data, t) | f(topic, data, t)
```

**Inject:**
```
inject thread wakes → handler(payload) [or handler(None, payload) for 2-arg form]
                    → handler may call app.send_cmd / app.publish / app.publish_event
```

**Unregister:**
```
app.unregister(name)
  → router.remove_by_name(name) → set of newly-empty patterns
  → for each empty pattern: paho.unsubscribe(pattern)
  → scheduler.cancel(name)
```

## Error handling

- **Missing `.env` config and no kwargs**: raise `RuntimeError` at `App.__init__` with a message listing required env vars and showing a sample `.env`.
- **MQTT connect failure**: log the rc; paho's `reconnectPeriod` handles retry. `app.run()` does not raise.
- **JSON decode error on `/fmt/json` topic**: WARNING log with topic + payload preview; message dropped.
- **Handler raises**: ERROR log including handler name, topic, and traceback; other handlers for the same message still run.
- **Inject handler raises**: ERROR log; thread continues with the next scheduled fire.
- **Unknown decorator combo on `@inject`** (e.g. both `every=` and `cron=`): `ValueError` at decoration time.

## Testing strategy

Three focused test modules:

**`test_router.py`** — pure unit tests, no MQTT:
- exact, single-wildcard, multi-wildcard match correctness
- multiple handlers per pattern
- `remove_by_name` reports correct newly-empty patterns
- non-matching topics return empty list
- the `iot3/+/evt/+/fmt/+` pattern from the prototype's test cases
- registration consolidation: exact-dup dropped, subsumed pattern dropped, narrower replaced by broader, pure-overlap kept with warning
- `_subsumes` truth table for representative pairs (literal/+/#)

**`test_scheduler.py`** — fast tests with short intervals:
- `every=0.1` fires ~10 times in 1 second
- `at_start=True` fires immediately
- `cancel` stops a running thread within one tick
- `cron` mode is exercised only if `croniter` is installed (skip otherwise)

**`test_app.py`** — uses paho's loopback or a mocked client:
- decorators register, function runs, function is unaffected (returns original fn)
- signature dispatch: `f(data)`, `f(topic, data)`, `f(data, t)`, `f(topic, data, t)`
- JSON decode happens before user fn
- envelope unwrap: handler receives `body["d"]`, not the full body
- envelope guard: messages without `"d"` are silently dropped (handler not called, no log noise)
- `t` pass-through: `body["t"]` arrives as `t` kwarg/positional when handler declares it; `None` when absent
- `unregister(name)` removes router + scheduler entries
- `send_cmd("lamp1", "lamp", {"lamp": "on"})` produces topic `iot3/lamp1/cmd/lamp/fmt/json` with body `{"d": {"lamp": "on"}}`

## Examples (`examples/`)

Each is a complete runnable script with a one-line description at the top:

1. **01_switch_lamp.py** — react to `switch1` on/off, mirror to `lamp1` (the canonical io7 starter).
2. **02_thermostat_valve.py** — read `thermo1` temperature, drive `valve1` with hysteresis around `target`.
3. **03_lux_auto_lamp.py** — read `lux1`, turn `lamp1` on at low light (from iotlab101 `5.io7uLux02`).
4. **04_scheduled_inject.py** — `@inject(cron="0 7 * * *")` daily morning lamp on; `@inject(every=300)` periodic refresh that re-sends the desired state command (defends against missed messages).
5. **05_wildcard_trace.py** — `@app.on("iot3/+/evt/+/fmt/json")` for cross-device logging, plus `app.unregister("trace")` after a delay.

Each example has a top-of-file comment naming the io7lab/iotlab101 hardware project it pairs with.

## Dependencies

- `paho-mqtt` — required, IoT MQTT client
- `python-dotenv` — required, `.env` loading
- `croniter` — optional, only imported when `@inject(cron=...)` is used; lazy import with a clear "pip install croniter" error message

`pyproject.toml` lists paho and dotenv under `dependencies`, croniter under `optional-dependencies.cron`.

## Out of scope (deferred)

- Async/await variant
- Connection retry callbacks / on-connect-status hooks
- Multi-broker apps
- Client certificate authentication (only CA-based TLS in v1, matching `IO7FuPython`)
