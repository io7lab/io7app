"""Auto-lamp from light sensor. Pairs with iotlab101/5.io7uLux02."""
from io7app import App

app = App()


@app.on_event("lux1", "status")
def auto_lamp(data):
    desired = "on" if data["lux"] < 50 else "off"
    app.send_cmd("lamp1", "lamp", {"lamp": desired})


if __name__ == "__main__":
    app.run()
