"""Report-by-exception (RBE) filter: handlers fire only when a watched value changes.

Modeled on Node-RED's filter (rbe) node: a handler behind a filter fires
only when the watched element of the payload actually changes — not on
the periodic republishes io7 devices emit (~5 s apart), and not on the
echo a device sends right after obeying a command. That echo absorption
is what makes bidirectional syncs (switch <-> lamp) settle after a single
round instead of looping.

Used through the App.filter decorator; this module holds the pure logic.
"""
import logging

log = logging.getLogger("io7app")


def _pluck(data, path):
    """Follow a dotted path ("switch", "sensor.lux") into a payload dict."""
    value = data
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


class Filter:
    """Stateful change gate for one handler registration.

    key: element of the decoded payload to watch; a dotted path reaches
        nested elements ("sensor.lux"). None watches the whole payload
        (useful for utf8/raw formats).
    act_on_first: also fire on the first value seen. By default the first
        report only initializes the reference, so an app restart does not
        re-trigger actions for state that isn't changing.
    valid: optional collection of accepted values; anything else is logged
        and dropped before it can pollute the change detection.
    min_delta: numeric deadband — block unless abs(change) >= min_delta.
    max_delta: numeric narrowband — block if abs(change) > max_delta
        (rejects one-off spikes; a persistent step never passes).

    Deltas compare against the last value that passed the filter.
    """

    def __init__(self, key=None, *, act_on_first=False, valid=None,
                 min_delta=None, max_delta=None, name="filter"):
        self.key = key
        self.act_on_first = act_on_first
        self.valid = valid
        self.min_delta = min_delta
        self.max_delta = max_delta
        self.name = name
        self._numeric = min_delta is not None or max_delta is not None
        self._prev = None

    def passes(self, data) -> bool:
        """True if the handler should fire for this payload."""
        value = _pluck(data, self.key) if self.key is not None else data
        if value is None or (self.valid is not None and value not in self.valid) \
                or (self._numeric and not isinstance(value, (int, float))):
            log.warning("%s: unexpected %r in payload: %r", self.name, self.key, data)
            return False
        if self._prev is None:
            self._prev = value
            return self.act_on_first
        if self._numeric:
            delta = abs(value - self._prev)
            if self.max_delta is not None and delta > self.max_delta:
                return False  # outlier: block, keep the reference value
            if self.min_delta is not None and delta < self.min_delta:
                return False  # inside the deadband
            self._prev = value
            return True
        if value == self._prev:
            return False
        self._prev = value
        return True
