"""Auto lamp: 01_switch_lamp and 02_lux_lamp merged; switch control and
lux control both keep working, side by side.

The lamp is now controlled from two sides — flip sw1 and the lamp
follows (example 01), and the light level drives it too, on when dark,
off when bright (example 02). Because the lux can change the lamp
behind the switch's back, the switch must be synced to the lamp's
actual state, so its position always shows the truth.

That sync is where an infinite loop threatens: sw1 moves the lamp, the
lamp's status update moves sw1, sw1's status update moves the lamp
again, and so on. @app.filter breaks the cycle — the sync handler
processes a lamp event only once, ignoring any event that reports the
same state as before, so each real change settles in a single round.

Pairs with io7-dummy-device lux / lamp / switch.
"""
from io7app import App

app = App()

LUX_THRESHOLD = 300


@app.on_event("lux1", "status")
def auto_lamp(data):
    desired = "on" if data["lux"] < LUX_THRESHOLD else "off"
    app.send_cmd("lamp1", "lamp", {"lamp": desired}, qos=1)


@app.on_event("sw1", "status")
def on_switch(data):
    app.send_cmd("lamp1", "lamp", {"lamp": data["switch"]}, qos=1)


@app.on_event("lamp1", "status")
@app.filter("lamp", act_on_first=True, valid=("on", "off"))
def sync_switch(data):
    app.send_cmd("sw1", "update", {"switch": data["lamp"]}, qos=1)


if __name__ == "__main__":
    app.run()
