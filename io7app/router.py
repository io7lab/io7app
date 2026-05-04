"""Topic router: matching + registration consolidation."""
from collections import namedtuple
from typing import Callable
import logging
import re

log = logging.getLogger("io7app")

Entry = namedtuple("Entry", ["handler", "name", "pattern", "fmt"])


def _fmt_of(pattern: str) -> str | None:
    parts = pattern.split("/")
    if len(parts) >= 2 and parts[-2] == "fmt":
        return parts[-1]
    return None


def _wildcard_kind(pattern: str) -> str:
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


def _subsumes(broader: str, narrower: str) -> bool:
    b = broader.split("/")
    n = narrower.split("/")
    bi = ni = 0
    while bi < len(b) and ni < len(n):
        bs = b[bi]
        ns = n[ni]
        if bs == "#":
            return True
        if ns == "#":
            return False
        if bs == "+":
            bi += 1; ni += 1
            continue
        if bs == ns:
            bi += 1; ni += 1
            continue
        return False
    return bi == len(b) and ni == len(n)


class Router:
    def __init__(self):
        self._exact: dict[str, list[Entry]] = {}
        self._single: list[tuple[re.Pattern, list[Entry], str]] = []
        self._multi: list[tuple[re.Pattern, list[Entry], str]] = []

    def add(self, pattern: str, handler: Callable, name: str) -> bool:
        """Register (pattern, handler, name). Apply consolidation rules.
        Returns True if the pattern is newly subscribed (caller should subscribe).
        """
        # Find existing patterns for this name
        existing = [p for p in self._patterns_for_name(name)]

        for ep in existing:
            if ep == pattern:
                log.warning(
                    "handler %r already registered with pattern %r; ignoring duplicate",
                    name, pattern,
                )
                return False
            if _subsumes(ep, pattern):
                log.warning(
                    "handler %r new pattern %r is covered by existing %r; ignoring",
                    name, pattern, ep,
                )
                return False

        # Detect "existing is subsumed by new" -- replace
        replaced_any = False
        for ep in list(existing):
            if _subsumes(pattern, ep) and ep != pattern:
                log.warning(
                    "handler %r new pattern %r subsumes existing %r; replacing",
                    name, pattern, ep,
                )
                self._remove_entry_for_name(ep, name)
                replaced_any = True

        # Pure-overlap warning (no subsumption either way, but plausibly overlap)
        for ep in self._patterns_for_name(name):
            if ep == pattern:
                continue
            if not _subsumes(ep, pattern) and not _subsumes(pattern, ep):
                if self._may_overlap(ep, pattern):
                    log.warning(
                        "handler %r patterns %r and %r may both match some topics "
                        "-- handler may fire twice for those topics",
                        name, ep, pattern,
                    )

        # Insert
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

    # --- internals ---

    def _patterns_for_name(self, name: str) -> list[str]:
        out: list[str] = []
        for p, entries in self._exact.items():
            if any(e.name == name for e in entries):
                out.append(p)
        for _, entries, p in self._single:
            if any(e.name == name for e in entries):
                out.append(p)
        for _, entries, p in self._multi:
            if any(e.name == name for e in entries):
                out.append(p)
        return out

    def _remove_entry_for_name(self, pattern: str, name: str) -> None:
        if pattern in self._exact:
            self._exact[pattern] = [e for e in self._exact[pattern] if e.name != name]
            if not self._exact[pattern]:
                del self._exact[pattern]
            return
        for bucket in (self._single, self._multi):
            for i, (rgx, entries, p) in enumerate(bucket):
                if p == pattern:
                    new_entries = [e for e in entries if e.name != name]
                    if not new_entries:
                        bucket.pop(i)
                    else:
                        bucket[i] = (rgx, new_entries, p)
                    return

    def remove_by_name(self, name: str) -> set[str]:
        """Remove every entry where entry.name == name across all tiers.
        Returns the set of patterns that have no remaining handlers
        (caller should MQTT-unsubscribe each).
        """
        emptied: set[str] = set()

        # Exact tier
        for p in list(self._exact.keys()):
            new_entries = [e for e in self._exact[p] if e.name != name]
            if not new_entries:
                del self._exact[p]
                emptied.add(p)
            else:
                self._exact[p] = new_entries

        # Single & multi tiers
        for bucket in (self._single, self._multi):
            i = 0
            while i < len(bucket):
                rgx, entries, p = bucket[i]
                new_entries = [e for e in entries if e.name != name]
                if not new_entries:
                    bucket.pop(i)
                    emptied.add(p)
                    continue
                if len(new_entries) != len(entries):
                    bucket[i] = (rgx, new_entries, p)
                i += 1

        return emptied

    @staticmethod
    def _may_overlap(a: str, b: str) -> bool:
        """Heuristic: returns False if patterns are provably disjoint by a literal mismatch.
        Both must contain wildcards to be considered overlapping."""
        if not (("+" in a or "#" in a) and ("+" in b or "#" in b)):
            return False
        ap = a.split("/")
        bp = b.split("/")
        for as_, bs in zip(ap, bp):
            if as_ == "#" or bs == "#":
                return True
            if as_ == "+" or bs == "+":
                continue
            if as_ != bs:
                return False
        return True
