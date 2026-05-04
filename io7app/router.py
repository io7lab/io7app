"""Topic router: matching + registration consolidation."""
from collections import namedtuple
from typing import Callable

Entry = namedtuple("Entry", ["handler", "name", "pattern", "fmt"])


def _fmt_of(pattern: str) -> str | None:
    """Extract the trailing /fmt/<x> token, or None if absent."""
    parts = pattern.split("/")
    if len(parts) >= 2 and parts[-2] == "fmt":
        return parts[-1]
    return None


class Router:
    def __init__(self):
        self._exact: dict[str, list[Entry]] = {}

    def add(self, pattern: str, handler: Callable, name: str) -> bool:
        """Register a handler. Returns True if pattern is new (caller must subscribe)."""
        is_new = pattern not in self._exact
        entry = Entry(handler, name, pattern, _fmt_of(pattern))
        self._exact.setdefault(pattern, []).append(entry)
        return is_new

    def dispatch(self, topic: str) -> list[Entry]:
        return list(self._exact.get(topic, []))
