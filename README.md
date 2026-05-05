# io7app

[![PyPI](https://img.shields.io/pypi/v/io7app.svg)](https://pypi.org/project/io7app/)
[![Python](https://img.shields.io/pypi/pyversions/io7app.svg)](https://pypi.org/project/io7app/)
[![License](https://img.shields.io/pypi/l/io7app.svg)](LICENSE)

A small, intuitive Python framework for writing **app servers** on the [io7 IoT platform](https://github.com/io7lab/).

You decorate Python functions with the device events they react to and the schedules they fire on. The framework owns the MQTT connection, topic routing, JSON envelope handling, scheduling, and dynamic register/unregister. Your code stays focused on business logic.

## The io7 platform — where this library fits

```
┌──────────┐                  ┌───────────┐                  ┌─────────────────┐
│  Devices │  ── events ──▶   │  Broker   │  ── events ──▶   │       App       │
│ (sensors,│                  │(Mosquitto)│                  │  (this library, │
│actuators)│ ◀── commands ──  │           │ ◀── commands ──  │   one process)  │
└──────────┘                  └───────────┘                  └─────────────────┘
   (many)                                                        (one)
```

io7 separates the world into two roles. **Devices** publish *events* (sensor readings, status changes) and receive *commands* (actuation requests). **Apps** subscribe to events from any device and publish commands to any device — they are where the IoT business logic lives ("if temperature drops, turn the valve on", "when the switch flips, mirror it on the lamp").

This library implements **only the App side**. Device firmware lives in the io7 [device libraries](https://github.com/io7lab/IO7FuPython) (ESP32, ESP8266, MicroPython).

## Quick start

You have two ways to run an io7app: as a normal pip package on your machine, or inside a self-contained Docker image. Both expect the same two files in your working directory:

- **`app.py`** — your application (decorators + `App().run()`).
- **`.env`** — broker credentials. Copy from [`.env.example`](.env.example):
  ```
  IO7_SERVER=iot201.ddns.net
  IO7_APP_ID=app3
  IO7_TOKEN=app3
  ```
  TLS, port overrides, and log levels are documented in the [user guide](USER_GUIDE.md).

A minimal `app.py`:

```python
from io7app import App

app = App()

@app.on_event("sw1", "status")
def on_switch(data):
    print("sw1 ->", data)

app.run()
```

### Option 1 — Local install (pip)

Available on [PyPI](https://pypi.org/project/io7app/). Requires Python ≥ 3.10:

```bash
pip install io7app
# Optional, only if you use @inject(cron=...)
pip install io7app[cron]
```

Then in the directory containing `app.py` and `.env`:

```bash
python app.py
```

Talks to any standard MQTT broker (Mosquitto, EMQX, HiveMQ, the io7 platform itself).

### Option 2 — Docker

Useful when you don't want to manage a Python environment on the host, and the natural choice when the rest of your io7 stack (broker, `io7api`, etc.) already runs in containers. The image is published on Docker Hub as **`io7lab/io7-app`** — no local build needed.

**1. Find the network your io7 stack is on.**

So this app can talk to the broker / `io7api` by container name instead of via the public internet:

```bash
docker network ls
# or, looked up off a known container:
docker inspect io7api \
  --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'
```

You'll see something like `io7_default` or `io7-net`. Use that below.

**2. Run the container** from any directory containing `app.py` and `.env`:

```bash
docker run -d --restart always \
  --name io7app \
  --network io7_default \
  -v "$PWD":/app \
  io7lab/io7-app
```

When the broker runs on the same docker network, `.env` should target the broker's service/container name rather than its public DNS:

```
IO7_SERVER=mqtt        # or whatever your broker container is named
IO7_APP_ID=app3
IO7_TOKEN=app3
```

The container watches `/app/app.py` and `/app/.env` and **auto-restarts** the python process when either changes — edit a file, save, and the new code is live within ~2 seconds. No need to bounce the container yourself. If you split your app across helper modules, run `touch app.py` to force a reload after editing them.

If `app.py` raises an exception, the traceback shows up in `docker logs -f io7-app` and the container keeps watching; fix the file and it restarts automatically.

Tunables (set with `-e`):

- `IO7_POLL_INTERVAL=1` — poll period in seconds (default 2).

**Docker Compose**

If you already maintain a `docker-compose.yml` for the io7 stack, add this service alongside `io7api` / `mqtt` so it shares the same network and lifecycle:

```yaml
services:
  io7-app:
    image: io7lab/io7-app
    container_name: io7app
    restart: always
    volumes:
      - ./myapp:/app          # folder with app.py and .env
    # environment:
    #   - IO7_POLL_INTERVAL=1
    # networks:               # only needed if your compose file
    #   - io7-net              # uses a non-default network name
```

Then `docker compose up -d io7-app`. Compose places the service on the project's default network automatically, so it can reach `mqtt` / `io7api` by service name.

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

MIT — see [LICENSE](LICENSE). Same as the rest of the io7lab packages.
