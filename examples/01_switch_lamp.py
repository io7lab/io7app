"""Switch -> Lamp mirror. Pairs with iotlab101/3.iot-lamp-switch."""
from io7app import App

app = App()


@app.on_event("switch1", "status")
def on_switch(data):
    app.send_cmd("lamp1", "lamp", {"lamp": data["switch"]})


if __name__ == "__main__":
    app.run()
