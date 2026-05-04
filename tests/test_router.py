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


def test_single_wildcard_plus():
    r = Router()
    seen = []
    def h(topic, payload): seen.append(topic)
    r.add("iot3/+/evt/+/fmt/json", h, "h")
    assert len(r.dispatch("iot3/lamp1/evt/status/fmt/json")) == 1
    assert len(r.dispatch("iot3/thermo1/evt/temperature/fmt/json")) == 1
    # Wrong fmt -- no match
    assert r.dispatch("iot3/lamp1/evt/status/fmt/utf8") == []
    # Too few segments
    assert r.dispatch("iot3/lamp1/evt/status") == []


def test_multi_wildcard_hash():
    r = Router()
    seen = []
    def h(topic, payload): seen.append(topic)
    r.add("iot3/lamp1/#", h, "h")
    assert len(r.dispatch("iot3/lamp1/evt/status/fmt/json")) == 1
    assert len(r.dispatch("iot3/lamp1/cmd/lamp/fmt/json")) == 1
    # Different device -- no match
    assert r.dispatch("iot3/thermo1/evt/status/fmt/json") == []


def test_hash_with_plus_combined():
    r = Router()
    r.add("iot3/+/cmd/#", lambda t, p: None, "h")
    assert len(r.dispatch("iot3/lamp1/cmd/lamp/fmt/json")) == 1
    assert len(r.dispatch("iot3/thermo1/cmd/anything/here")) == 1
    assert r.dispatch("iot3/lamp1/evt/status/fmt/json") == []


from io7app.router import _subsumes


def test_subsumes_truth_table():
    # Identical patterns: each subsumes the other
    assert _subsumes("a/b/c", "a/b/c")

    # + covers a literal at the same position
    assert _subsumes("a/+/c", "a/b/c")
    assert not _subsumes("a/b/c", "a/+/c")

    # # covers everything from its position
    assert _subsumes("a/#", "a/b/c")
    assert _subsumes("a/#", "a/b")
    assert _subsumes("iot3/+/#", "iot3/lamp1/evt/status/fmt/json")

    # Disjoint
    assert not _subsumes("a/b/c", "a/b/d")
    assert not _subsumes("a/b", "a/b/c")  # narrower than required

    # + is exactly one segment, # is many; + does not subsume #
    assert not _subsumes("a/+", "a/#")
    assert _subsumes("a/#", "a/+")        # # broader than +
