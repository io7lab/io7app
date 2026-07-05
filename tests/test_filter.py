"""Tests for the report-by-exception filter: io7app.filter.Filter and @app.filter."""
import json
import logging

from io7app.filter import Filter

TOPIC = "iot3/sw1/evt/status/fmt/json"


def evt(d, t=None):
    body = {"d": d}
    if t is not None:
        body["t"] = t
    return json.dumps(body)


# ---------- Filter unit tests (pure logic) ----------

def test_blocks_unless_value_changes():
    f = Filter("switch", act_on_first=True)
    assert f.passes({"switch": "on"}) is True
    assert f.passes({"switch": "on"}) is False
    assert f.passes({"switch": "off"}) is True
    assert f.passes({"switch": "off"}) is False


def test_first_report_only_initializes_by_default():
    f = Filter("switch")
    assert f.passes({"switch": "on"}) is False   # recorded, not fired
    assert f.passes({"switch": "on"}) is False
    assert f.passes({"switch": "off"}) is True


def test_element_level_other_elements_ignored():
    f = Filter("switch", act_on_first=True)
    assert f.passes({"switch": "on", "brightness": 333}) is True
    assert f.passes({"switch": "on", "brightness": 555}) is False
    assert f.passes({"switch": "off", "brightness": 333}) is True


def test_dotted_path():
    f = Filter("sensor.lux", act_on_first=True)
    assert f.passes({"sensor": {"lux": 250}, "id": 1}) is True
    assert f.passes({"sensor": {"lux": 250}, "id": 2}) is False
    assert f.passes({"sensor": {"lux": 900}}) is True


def test_valid_rejects_without_touching_reference(caplog):
    caplog.set_level(logging.WARNING, logger="io7app")
    f = Filter("switch", act_on_first=True, valid=("on", "off"))
    assert f.passes({"switch": "on"}) is True
    assert f.passes({"switch": "banana"}) is False
    assert "unexpected" in caplog.text
    # reference still "on": a following "on" is a repeat, "off" is a change
    assert f.passes({"switch": "on"}) is False
    assert f.passes({"switch": "off"}) is True


def test_missing_key_rejected():
    f = Filter("switch")
    assert f.passes({"lamp": "on"}) is False
    assert f.passes("not a dict") is False


def test_deadband_min_delta():
    f = Filter("lux", act_on_first=True, min_delta=250)
    fired = [v for v in (150, 220, 130, 890, 950, 810, 120, 260)
             if f.passes({"lux": v})]
    assert fired == [150, 890, 120]  # only dark<->bright transitions


def test_narrowband_max_delta_rejects_spike():
    f = Filter("lux", act_on_first=True, max_delta=500, min_delta=1)
    fired = [v for v in (200, 210, 5000, 240, 190) if f.passes({"lux": v})]
    assert fired == [200, 210, 240, 190]


def test_narrowband_persistent_step_never_passes():
    f = Filter("lux", act_on_first=True, max_delta=50)
    assert f.passes({"lux": 100}) is True
    assert f.passes({"lux": 500}) is False  # step blocked...
    assert f.passes({"lux": 500}) is False  # ...and stays blocked by design


def test_numeric_mode_rejects_non_numeric():
    f = Filter("lux", min_delta=10)
    assert f.passes({"lux": "bright"}) is False


def test_key_none_watches_whole_payload():
    f = Filter(act_on_first=True)
    assert f.passes("on") is True    # utf8 payloads are plain strings
    assert f.passes("on") is False
    assert f.passes("off") is True


# ---------- @app.filter integration (through dispatch) ----------

def test_filter_drops_periodic_republish(app, fake_client):
    calls = []

    @app.on_event("sw1", "status")
    @app.filter("switch", act_on_first=True)
    def h(data):
        calls.append(data["switch"])

    fake_client.connect("h", 1883)
    for payload in ({"switch": "on"}, {"switch": "on"}, {"switch": "on"},
                    {"switch": "off"}):
        fake_client.deliver(TOPIC, evt(payload))
    assert calls == ["on", "off"]


def test_filter_element_change_passes_full_payload(app, fake_client):
    calls = []

    @app.on_event("sw1", "status")
    @app.filter("switch", act_on_first=True)
    def h(data):
        calls.append((data["switch"], data["brightness"]))

    fake_client.connect("h", 1883)
    fake_client.deliver(TOPIC, evt({"switch": "on", "brightness": 333}))
    fake_client.deliver(TOPIC, evt({"switch": "on", "brightness": 555}))
    fake_client.deliver(TOPIC, evt({"switch": "off", "brightness": 777}))
    assert calls == [("on", 333), ("off", 777)]


def test_all_signature_forms_work_behind_filter(app, fake_client):
    got = {}

    @app.on_event("sw1", "status")
    @app.filter("switch", act_on_first=True)
    def one(data):
        got["one"] = data

    @app.on_event("sw1", "status")
    @app.filter("switch", act_on_first=True)
    def two(topic, data):
        got["two"] = (topic, data)

    @app.on_event("sw1", "status")
    @app.filter("switch", act_on_first=True)
    def three(data, t):
        got["three"] = (data, t)

    @app.on_event("sw1", "status")
    @app.filter("switch", act_on_first=True)
    def four(topic, data, t):
        got["four"] = (topic, data, t)

    fake_client.connect("h", 1883)
    fake_client.deliver(TOPIC, evt({"switch": "on"}, t=1714800000000))
    d = {"switch": "on"}
    assert got["one"] == d
    assert got["two"] == (TOPIC, d)
    assert got["three"] == (d, 1714800000000)
    assert got["four"] == (TOPIC, d, 1714800000000)


def test_filter_state_is_per_handler(app, fake_client):
    calls = []

    @app.on_event("sw1", "status")
    @app.filter("switch", act_on_first=True)
    def first(data):
        calls.append("first")

    @app.on_event("sw1", "status")
    @app.filter("switch")          # default: skip initial value
    def second(data):
        calls.append("second")

    fake_client.connect("h", 1883)
    fake_client.deliver(TOPIC, evt({"switch": "on"}))
    fake_client.deliver(TOPIC, evt({"switch": "off"}))
    assert calls == ["first", "first", "second"]


def test_unfiltered_handler_unaffected(app, fake_client):
    calls = []

    @app.on_event("sw1", "status")
    @app.filter("switch")
    def gated(data):
        calls.append("gated")

    @app.on_event("sw1", "status")
    def raw(data):
        calls.append("raw")

    fake_client.connect("h", 1883)
    fake_client.deliver(TOPIC, evt({"switch": "on"}))
    fake_client.deliver(TOPIC, evt({"switch": "on"}))
    assert calls == ["raw", "raw"]


def test_wrong_decorator_order_warns(app, caplog):
    caplog.set_level(logging.WARNING, logger="io7app")

    @app.filter("switch")          # applied ABOVE the registration: wrong
    @app.on_event("sw1", "status")
    def h(data):
        pass

    assert "apply @app.filter below" in caplog.text


def test_stacked_handlers_each_focus_on_one_element(app, fake_client):
    """Several functions share one on_event signature; the runtime stacks
    them, and each filtered handler fires only when ITS element changes."""
    calls = []
    topic = "iot3/dimmer1/evt/status/fmt/json"

    @app.on_event("dimmer1", "status")
    @app.filter("switch", act_on_first=True)
    def power(data):
        calls.append(("power", data["switch"]))

    @app.on_event("dimmer1", "status")
    @app.filter("brightness", act_on_first=True, min_delta=10)
    def level(data):
        calls.append(("level", data["brightness"]))

    @app.on_event("dimmer1", "status")
    def audit(data):                      # unfiltered: sees every report
        calls.append(("audit",))

    fake_client.connect("h", 1883)
    fake_client.deliver(topic, evt({"switch": "on", "brightness": 100}))
    fake_client.deliver(topic, evt({"switch": "on", "brightness": 100}))   # repeat
    fake_client.deliver(topic, evt({"switch": "on", "brightness": 180}))   # dimmed
    fake_client.deliver(topic, evt({"switch": "off", "brightness": 180}))  # powered off
    assert calls == [
        ("power", "on"), ("level", 100), ("audit",),   # first report
        ("audit",),                                    # repeat: filters block
        ("level", 180), ("audit",),                    # only brightness moved
        ("power", "off"), ("audit",),                  # only switch moved
    ]


def test_filtered_handler_on_wildcard_warns(app, caplog):
    caplog.set_level(logging.WARNING, logger="io7app")

    @app.on("iot3/+/evt/status/fmt/json")
    @app.filter("switch")
    def h(data):
        pass

    assert "filter state is shared" in caplog.text


def test_unregister_works_through_filter(app, fake_client):
    calls = []

    @app.on_event("sw1", "status")
    @app.filter("switch", act_on_first=True)
    def h(data):
        calls.append(1)

    fake_client.connect("h", 1883)
    fake_client.deliver(TOPIC, evt({"switch": "on"}))
    app.unregister("h")            # wraps preserves __name__
    fake_client.deliver(TOPIC, evt({"switch": "off"}))
    assert calls == [1]
    assert TOPIC in fake_client.unsubscribed
