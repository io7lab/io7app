from io7app.router import Router


def test_exact_match_dispatch():
    r = Router()
    calls = []
    def h(topic, payload):
        calls.append((topic, payload))
    r.add("iot3/lamp1/evt/status/fmt/json", h, "h")
    entries = r.dispatch("iot3/lamp1/evt/status/fmt/json")
    assert len(entries) == 1
    assert entries[0].handler is h
    assert entries[0].name == "h"


def test_exact_no_match():
    r = Router()
    r.add("iot3/lamp1/evt/status/fmt/json", lambda t, p: None, "h")
    assert r.dispatch("iot3/other/evt/status/fmt/json") == []
