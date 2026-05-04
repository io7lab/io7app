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


import logging


def test_consolidation_exact_dup(caplog):
    r = Router()
    def h(t, p): pass
    r.add("iot3/lamp1/evt/status/fmt/json", h, "h")
    with caplog.at_level(logging.WARNING, logger="io7app"):
        added = r.add("iot3/lamp1/evt/status/fmt/json", h, "h")
    assert added is False  # not a new pattern
    assert len(r.dispatch("iot3/lamp1/evt/status/fmt/json")) == 1  # only one entry
    assert any("already registered" in rec.message for rec in caplog.records)


def test_consolidation_subsumed(caplog):
    r = Router()
    def h(t, p): pass
    r.add("iot3/+/evt/+/fmt/json", h, "h")
    with caplog.at_level(logging.WARNING, logger="io7app"):
        r.add("iot3/lamp1/evt/status/fmt/json", h, "h")
    # Narrower pattern dropped
    assert r.dispatch("iot3/lamp1/evt/status/fmt/json")  # still matches via broader
    assert all(e.pattern == "iot3/+/evt/+/fmt/json" for e in r.dispatch("iot3/lamp1/evt/status/fmt/json"))
    assert any("covered by" in rec.message for rec in caplog.records)


def test_consolidation_replace_narrower(caplog):
    r = Router()
    def h(t, p): pass
    r.add("iot3/lamp1/evt/status/fmt/json", h, "h")
    with caplog.at_level(logging.WARNING, logger="io7app"):
        r.add("iot3/+/evt/+/fmt/json", h, "h")
    entries = r.dispatch("iot3/lamp1/evt/status/fmt/json")
    assert len(entries) == 1
    assert entries[0].pattern == "iot3/+/evt/+/fmt/json"  # narrower replaced
    assert any("subsumes existing" in rec.message for rec in caplog.records)


def test_consolidation_pure_overlap_warns(caplog):
    r = Router()
    def h(t, p): pass
    r.add("iot3/lamp1/#", h, "h")
    with caplog.at_level(logging.WARNING, logger="io7app"):
        r.add("iot3/+/evt/status/fmt/json", h, "h")
    # Both kept
    matches = r.dispatch("iot3/lamp1/evt/status/fmt/json")
    assert len(matches) == 2
    assert any("may fire twice" in rec.message for rec in caplog.records)


def test_consolidation_disjoint_silent(caplog):
    r = Router()
    def h(t, p): pass
    r.add("iot3/lamp1/#", h, "h")
    with caplog.at_level(logging.WARNING, logger="io7app"):
        r.add("iot3/thermo1/#", h, "h")
    assert caplog.records == []  # no warnings


def test_consolidation_only_within_same_name(caplog):
    """Different handler names with overlapping patterns -- no consolidation."""
    r = Router()
    def a(t, p): pass
    def b(t, p): pass
    r.add("iot3/+/#", a, "a")
    with caplog.at_level(logging.WARNING, logger="io7app"):
        r.add("iot3/lamp1/evt/status/fmt/json", b, "b")
    # Both kept; no warning
    assert caplog.records == []
    matches = r.dispatch("iot3/lamp1/evt/status/fmt/json")
    assert len(matches) == 2
