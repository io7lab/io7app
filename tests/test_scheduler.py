import time
from io7app.scheduler import Scheduler


def test_every_fires_repeatedly():
    s = Scheduler()
    calls = []

    def f(payload):
        calls.append(payload)

    s.schedule("f", f, every=0.05, payload={"k": 1})
    s.start()
    time.sleep(0.22)
    s.stop()
    # ~4 fires in ~0.22s; allow slack
    assert 3 <= len(calls) <= 6
    assert all(c == {"k": 1} for c in calls)


def test_cancel_stops_thread():
    s = Scheduler()
    calls = []
    def f(payload): calls.append(1)

    s.schedule("f", f, every=0.05)
    s.start()
    time.sleep(0.12)
    s.cancel("f")
    n_after_cancel = len(calls)
    time.sleep(0.15)
    assert len(calls) == n_after_cancel  # no further fires
