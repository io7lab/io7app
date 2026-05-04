"""Topic router: matching + registration consolidation."""
from collections import namedtuple
from typing import Callable
import re

Entry = namedtuple("Entry", ["handler", "name", "pattern", "fmt"])


def _fmt_of(pattern: str) -> str | None:
    parts = pattern.split("/")
    if len(parts) >= 2 and parts[-2] == "fmt":
        return parts[-1]
    return None


def _wildcard_kind(pattern: str) -> str:
    """Returns 'exact', 'single', or 'multi'."""
    parts = pattern.split("/")
    if parts[-1] == "#":
        return "multi"
    if "+" in parts:
        return "single"
    return "exact"


def _compile(pattern: str) -> re.Pattern:
    parts = pattern.split("/")
    out = []
    for p in parts:
        if p == "+":
            out.append(r"[^/]+")
        elif p == "#":
            out.append(r".*")
        else:
            out.append(re.escape(p))
    return re.compile("^" + "/".join(out) + "$")


class Router:
    def __init__(self):
        self._exact: dict[str, list[Entry]] = {}
        self._single: list[tuple[re.Pattern, list[Entry], str]] = []
        self._multi: list[tuple[re.Pattern, list[Entry], str]] = []

    def add(self, pattern: str, handler: Callable, name: str) -> bool:
        entry = Entry(handler, name, pattern, _fmt_of(pattern))
        kind = _wildcard_kind(pattern)
        if kind == "exact":
            is_new = pattern not in self._exact
            self._exact.setdefault(pattern, []).append(entry)
            return is_new
        bucket = self._single if kind == "single" else self._multi
        for _, entries, pat in bucket:
            if pat == pattern:
                entries.append(entry)
                return False
        bucket.append((_compile(pattern), [entry], pattern))
        return True

    def dispatch(self, topic: str) -> list[Entry]:
        out: list[Entry] = []
        out.extend(self._exact.get(topic, []))
        for rgx, entries, _ in self._single:
            if rgx.match(topic):
                out.extend(entries)
        for rgx, entries, _ in self._multi:
            if rgx.match(topic):
                out.extend(entries)
        return out
