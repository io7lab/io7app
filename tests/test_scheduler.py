import datetime as dt
import time

import pytest

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


def test_at_start_fires_immediately():
    s = Scheduler()
    calls = []
    def f(payload): calls.append(time.time())
    s.schedule("f", f, every=10.0, at_start=True)
    t0 = time.time()
    s.start()
    time.sleep(0.05)  # well before the 10s interval
    s.stop()
    assert len(calls) == 1
    assert calls[0] - t0 < 0.1


def test_at_start_with_no_other_mode_only_fires_once():
    """at_start alone -- still need a mode; verify at_start without every is rejected."""
    s = Scheduler()
    with pytest.raises(ValueError):
        s.schedule("f", lambda p: None, at_start=True)


def test_at_mode_computes_next_fire():
    s = Scheduler()
    # We don't actually wait until tomorrow; we test the next-fire computation.
    next_at = s._next_fire_for_at("23:59", now=dt.datetime(2026, 1, 1, 12, 0))
    assert next_at == dt.datetime(2026, 1, 1, 23, 59)

    # If the time today already passed, schedule for tomorrow
    next_at = s._next_fire_for_at("06:00", now=dt.datetime(2026, 1, 1, 12, 0))
    assert next_at == dt.datetime(2026, 1, 2, 6, 0)


def test_at_mode_invalid_format_rejected():
    s = Scheduler()
    with pytest.raises(ValueError):
        s.schedule("f", lambda p: None, at="not-a-time")


def test_cron_mode_validates_at_register():
    s = Scheduler()
    with pytest.raises(ValueError):
        s.schedule("f", lambda p: None, cron="not a cron")


def test_cron_mode_fires(monkeypatch):
    """Use a cron that fires every minute, then accelerate by mocking time waits."""
    pytest.importorskip("croniter")
    s = Scheduler()
    calls = []
    def f(payload): calls.append(time.time())

    # We can't wait a real minute. Instead patch _next_fire_for_cron to return
    # a time ~0.05s ahead each call so the loop fires quickly.
    def fast(_cron):
        return dt.datetime.now() + dt.timedelta(seconds=0.05)
    s._next_fire_for_cron = fast  # type: ignore

    s.schedule("f", f, cron="* * * * *")
    s.start()
    time.sleep(0.25)
    s.stop()
    assert len(calls) >= 3


def test_start_is_idempotent():
    """Double-calling start() must not launch ghost threads (matters for reconnect)."""
    s = Scheduler()
    calls = []
    def f(payload): calls.append(1)
    s.schedule("f", f, every=0.05)
    s.start()
    s.start()  # should be a no-op
    time.sleep(0.22)
    s.stop()
    # If start were not idempotent, we'd see ~2x the fires
    assert 3 <= len(calls) <= 6


def test_inject_with_t_param():
    s = Scheduler()
    seen = []
    def f(payload, t):
        seen.append((payload, t))
    s.schedule("f", f, every=0.05, payload={"k": 1})
    s.start()
    time.sleep(0.12)
    s.stop()
    assert seen
    payload, t = seen[0]
    assert payload == {"k": 1}
    assert isinstance(t, float) and t > 0
