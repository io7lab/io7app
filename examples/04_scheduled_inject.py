"""Cron + interval scheduling. Daily morning lamp on; periodic command refresh."""
from io7app import App

app = App()
last_state = {"lamp": "off"}


@app.inject(cron="0 7 * * *", payload={"lamp": "on"})
def morning(data):
    last_state["lamp"] = data["lamp"]
    app.send_cmd("lamp1", "lamp", data)


@app.inject(every=300)
def refresh(data):
    """Re-send the desired state every 5 minutes -- defends against missed messages."""
    app.send_cmd("lamp1", "lamp", {"lamp": last_state["lamp"]})


if __name__ == "__main__":
    app.run()
