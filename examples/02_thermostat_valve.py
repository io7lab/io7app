"""Thermostat -> Valve with hysteresis. Pairs with iotlab101/12.io7Thermostat."""
from io7app import App

app = App()
state = {"valve": "off"}


@app.on_event("thermo1", "status")
def thermostat(data):
    temp = data["temperature"]
    target = data.get("target", 22.0)
    desired = (
        "on" if temp < target - 0.5
        else "off" if temp > target + 0.5
        else state["valve"]
    )
    if desired != state["valve"]:
        state["valve"] = desired
        app.send_cmd("valve1", "valve", {"valve": desired})


if __name__ == "__main__":
    app.run()
