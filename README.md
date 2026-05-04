# io7app

A small Python framework for writing **io7 IoT app servers**.

```python
from io7app import App
app = App()

@app.on_event("switch1", "status")
def on_switch(data):
    app.send_cmd("lamp1", "lamp", {"lamp": data["switch"]})

app.run()
```

- See **[USER_GUIDE.md](USER_GUIDE.md)** for the full guide and examples.
- See **[docs/superpowers/specs/](docs/superpowers/specs/)** for the design.
- Devices publish events; apps publish commands. This library is the **app side** only.

## Install

```bash
pip install io7app
# Optional, for @inject(cron=...):
pip install croniter
```

## Configure

Drop a `.env` next to your script (see `.env.example`). TLS auto-engages if `IO7_CA` is set or `ca.pem` is in cwd.

## Test

```bash
pip install -e ".[dev]"
pytest
```
