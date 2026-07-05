"""Auto-lighting triangle: lux and sw1 drive lamp1; lamp1 syncs sw1.

lux1 reports the light level every few seconds and lamp1 follows the
light (on when dark, off when bright); flipping sw1 drives the lamp too;
and sw1's position is synced back to the lamp's actual state, so the
wall switch always shows the truth no matter who changed the lamp.

The sync-back makes a potential echo loop: sw1 -> lamp1 -> sw1 -> ...
One filter, on the lamp event, is enough to break it — every echo path
in the triangle funnels through lamp1's status, and a report that
doesn't change the lamp state dies at that gate. The lux and switch
handlers stay plain (commands are idempotent, like examples 01 and 03);
act_on_first fixes a lamp/switch mismatch right at startup.

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
