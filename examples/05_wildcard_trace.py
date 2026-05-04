"""Cross-device trace; demonstrates dynamic unregister."""
import threading
from io7app import App

app = App()


@app.on("iot3/+/evt/+/fmt/json")
def trace(topic, data):
    print(f"[{topic}] {data}")


def stop_tracing_after(delay):
    threading.Timer(delay, lambda: app.unregister("trace")).start()


if __name__ == "__main__":
    stop_tracing_after(60)  # auto-stop after 60s
    app.run()
