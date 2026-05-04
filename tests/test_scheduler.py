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
    import pytest
    with pytest.raises(ValueError):
        s.schedule("f", lambda p: None, at_start=True)


import datetime as dt
from unittest.mock import patch


def test_at_mode_computes_next_fire():
    s = Scheduler()
    # We don't actually wait until tomorrow; we test the next-fire computation.
    next_at = s._next_fire_for_at("23:59", now=dt.datetime(2026, 1, 1, 12, 0))
    assert next_at == dt.datetime(2026, 1, 1, 23, 59)

    # If the time today already passed, schedule for tomorrow
    next_at = s._next_fire_for_at("06:00", now=dt.datetime(2026, 1, 1, 12, 0))
    assert next_at == dt.datetime(2026, 1, 2, 6, 0)


def test_at_mode_invalid_format_rejected():
    import pytest
    s = Scheduler()
    with pytest.raises(ValueError):
        s.schedule("f", lambda p: None, at="not-a-time")
