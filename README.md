# io7app

A small, intuitive Python framework for writing **app servers** on the [io7 IoT platform](https://github.com/io7lab/).

You decorate Python functions with the device events they react to and the schedules they fire on. The framework owns the MQTT connection, topic routing, JSON envelope handling, scheduling, and dynamic register/unregister. Your code stays focused on business logic.

## The io7 platform — where this library fits

```
┌──────────┐                  ┌──────────┐                  ┌─────────────────┐
│  Devices │ ── events ──▶    │  Broker  │ ── events ──▶    │       App       │
│ (sensors,│                  │(Mosquitto)│                  │  (this library, │
│actuators)│ ◀── commands ──  │          │ ◀── commands ──  │   one process)  │
└──────────┘                  └──────────┘                  └─────────────────┘
   (many)                                                        (one)
```

io7 separates the world into two roles. **Devices** publish *events* (sensor readings, status changes) and receive *commands* (actuation requests). **Apps** subscribe to events from any device and publish commands to any device — they are where the IoT business logic lives ("if temperature drops, turn the valve on", "when the switch flips, mirror it on the lamp").

This library implements **only the App side**. Device firmware lives in the io7 [device libraries](https://github.com/io7lab/IO7FuPython) (ESP32, ESP8266, MicroPython).

## Install

```bash
pip install io7app
# Optional, only if you use @inject(cron=...)
pip install croniter
```

Requires Python ≥ 3.10. Talks to any standard MQTT broker (Mosquitto, EMQX, HiveMQ, the io7 platform itself).

## Configure

Drop a `.env` next to your script (copy from `.env.example`):

```
IO7_SERVER=iot201.ddns.net
IO7_APP_ID=app3
IO7_TOKEN=app3
```

That's the minimum. TLS, port overrides, and log levels are documented in the user guide.

## Status

- Version 0.1.0
- ~640 lines of Python across three small modules (router, scheduler, app)
- 71 tests, all green
- One dependency: `paho-mqtt`. Plus `python-dotenv` for config and optionally `croniter` for cron schedules.

## Where to go next

- **[USER_GUIDE.md](USER_GUIDE.md)** — write your first app, decorator reference, scheduling, dynamic register/unregister, debug logging. Every claim in the guide is exercised by a test.
- **[examples/](examples/)** — five runnable apps: switch/lamp, thermostat/valve, lux auto-lamp, scheduled inject, wildcard tracing.
- **[docs/superpowers/specs/](docs/superpowers/specs/)** — design document.
- **[docs/superpowers/plans/](docs/superpowers/plans/)** — implementation plan.

## Develop

```bash
git clone <this-repo>
cd io7app
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Design principles

- **Small.** Three modules, one class, four decorators.
- **Intuitive.** A working app is 3-5 lines of business logic.
- **Honest.** No magic — handler signatures are inspected, not assumed; dropped messages are silent only when the spec says so; warnings spell out exactly what was deduplicated and why.
- **Optimal where it counts.** Static topics dispatch in O(1); wildcards compile to a regex once; overlapping decorators are consolidated at registration time so handlers never double-fire.

## License

TBD — no LICENSE file yet. Add one before publishing to PyPI.
