# io7app Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a small Python framework (`io7app`) that lets users write io7 IoT app servers by decorating functions with the device/event topics they react to and the schedules they fire on.

**Architecture:** Three independently-testable modules — `router.py` (topic matching + registration consolidation), `scheduler.py` (one thread per `@inject`), `app.py` (paho wiring + decorators + envelope unwrap) — wired together by a single `App` class. Three storage tiers in the router (exact dict / `+`-regex / `#`-regex) and registration-time consolidation make dispatch O(1) for static topics and dedup-free for stacked decorators.

**Tech Stack:** Python 3.10+, `paho-mqtt` (MQTT client), `python-dotenv` (config), `croniter` (optional, only for `@inject(cron=...)`). Testing with `pytest`. No async, no extra build system beyond `pyproject.toml`.

---

## File structure

```
io7app/
  __init__.py            # exports: App
  router.py              # Router class, _subsumes, Entry namedtuple
  scheduler.py           # Scheduler class, one daemon thread per inject
  app.py                 # App class: config, paho, decorators, decoder
examples/
  01_switch_lamp.py
  02_thermostat_valve.py
  03_lux_auto_lamp.py
  04_scheduled_inject.py
  05_wildcard_trace.py
tests/
  __init__.py
  conftest.py            # FakeMQTTClient fixture
  test_router.py
  test_scheduler.py
  test_app.py
  test_examples.py
.env.example
pyproject.toml
.gitignore
README.md                # short, points to USER_GUIDE.md
USER_GUIDE.md            # already written
PRD.md                   # already exists
```

Each module has one responsibility:
- `router.py` — pure topic-matching logic; no IO; no MQTT.
- `scheduler.py` — pure time-based firing; no IO; no MQTT.
- `app.py` — owns the paho client, the Router, the Scheduler; binds them together.

---

## Phase 0: Project scaffolding

### Task 0: Create package skeleton, dev deps, gitignore

**Files:**
- Create: `/Users/yhur/tmp/io7app/pyproject.toml`
- Create: `/Users/yhur/tmp/io7app/.gitignore`
- Create: `/Users/yhur/tmp/io7app/.env.example`
- Create: `/Users/yhur/tmp/io7app/io7app/__init__.py`
- Create: `/Users/yhur/tmp/io7app/io7app/router.py` (empty stub)
- Create: `/Users/yhur/tmp/io7app/io7app/scheduler.py` (empty stub)
- Create: `/Users/yhur/tmp/io7app/io7app/app.py` (empty stub)
- Create: `/Users/yhur/tmp/io7app/tests/__init__.py`
- Create: `/Users/yhur/tmp/io7app/tests/conftest.py` (placeholder)

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "io7app"
version = "0.1.0"
description = "Python app-server framework for the io7 IoT platform"
requires-python = ">=3.10"
dependencies = [
  "paho-mqtt>=1.6,<3.0",
  "python-dotenv>=1.0",
]

[project.optional-dependencies]
cron = ["croniter>=2.0"]
dev  = ["pytest>=8.0", "pytest-timeout>=2.3", "croniter>=2.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["io7app"]

[tool.pytest.ini_options]
addopts = "-q --timeout=10"
testpaths = ["tests"]
```

- [ ] **Step 2: Write `.gitignore`**

```
__pycache__/
*.pyc
.venv/
.env
ca.pem
*.egg-info/
dist/
build/
.pytest_cache/
```

- [ ] **Step 3: Write `.env.example`**

```
IO7_SERVER=iot201.ddns.net
IO7_APP_ID=app3
IO7_TOKEN=app3
# IO7_PORT=1883     # optional; auto 8883 when TLS engages
# IO7_CA=ca.pem     # optional; or place ca.pem in cwd
```

- [ ] **Step 4: Write `io7app/__init__.py`**

```python
from io7app.app import App

__all__ = ["App"]
__version__ = "0.1.0"
```

- [ ] **Step 5: Write empty stubs for `router.py`, `scheduler.py`, `app.py`**

`io7app/router.py`:
```python
"""Topic router: matching + registration consolidation."""
```

`io7app/scheduler.py`:
```python
"""Inject scheduler: one daemon thread per scheduled job."""
```

`io7app/app.py`:
```python
"""App class: wires paho-mqtt, Router, Scheduler."""

class App:
    pass
```

- [ ] **Step 6: Write `tests/__init__.py`** (empty file)

- [ ] **Step 7: Write `tests/conftest.py`** (just a header for now)

```python
"""Shared test fixtures."""
```

- [ ] **Step 8: Set up venv and install dev deps**

Run:
```bash
cd /Users/yhur/tmp/io7app
python -m venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

Expected: install succeeds with paho-mqtt, python-dotenv, croniter, pytest, pytest-timeout.

- [ ] **Step 9: Confirm pytest discovers tests dir**

Run: `pytest --collect-only`
Expected: `collected 0 items` and no errors.

- [ ] **Step 10: Commit**

```bash
git init
git add .
git commit -m "scaffold: io7app package layout, deps, gitignore"
```

---

## Phase 1: Router

### Task 1: Router exact-match add + dispatch

**Files:**
- Modify: `/Users/yhur/tmp/io7app/io7app/router.py`
- Create: `/Users/yhur/tmp/io7app/tests/test_router.py`

- [ ] **Step 1: Write the failing test**

`tests/test_router.py`:
```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_router.py -v`
Expected: ImportError or NameError — `Router` not defined.

- [ ] **Step 3: Implement minimal Router**

`io7app/router.py`:
```python
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
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_router.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add io7app/router.py tests/test_router.py
git commit -m "router: exact-match add + dispatch"
```

---

### Task 2: Router single-wildcard `+` matching

**Files:**
- Modify: `/Users/yhur/tmp/io7app/io7app/router.py`
- Modify: `/Users/yhur/tmp/io7app/tests/test_router.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_router.py`:
```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_router.py::test_single_wildcard_plus -v`
Expected: FAIL — wildcard not matched.

- [ ] **Step 3: Add `+` support to Router**

Replace `io7app/router.py` with:
```python
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


def _has_wildcard(pattern: str) -> bool:
    return "+" in pattern.split("/") or pattern.split("/")[-1] == "#"


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

    def add(self, pattern: str, handler: Callable, name: str) -> bool:
        entry = Entry(handler, name, pattern, _fmt_of(pattern))
        if not _has_wildcard(pattern):
            is_new = pattern not in self._exact
            self._exact.setdefault(pattern, []).append(entry)
            return is_new
        # has + (we'll handle # in next task)
        for rgx, entries, pat in self._single:
            if pat == pattern:
                entries.append(entry)
                return False
        self._single.append((_compile(pattern), [entry], pattern))
        return True

    def dispatch(self, topic: str) -> list[Entry]:
        out: list[Entry] = []
        out.extend(self._exact.get(topic, []))
        for rgx, entries, _ in self._single:
            if rgx.match(topic):
                out.extend(entries)
        return out
```

- [ ] **Step 4: Run all router tests**

Run: `pytest tests/test_router.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add io7app/router.py tests/test_router.py
git commit -m "router: + wildcard support via compiled regex"
```

---

### Task 3: Router multi-wildcard `#` matching

**Files:**
- Modify: `/Users/yhur/tmp/io7app/io7app/router.py`
- Modify: `/Users/yhur/tmp/io7app/tests/test_router.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_router.py`:
```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_router.py::test_multi_wildcard_hash -v`
Expected: FAIL — `#` not handled (`add` puts it in `_single` but the regex `.*` with full anchoring may pass; actually `_has_wildcard` only checks last segment for `#`, so the test combining `+` and `#` should fail).

- [ ] **Step 3: Add `_multi` tier to Router**

Replace `io7app/router.py` with:
```python
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
```

- [ ] **Step 4: Run all router tests**

Run: `pytest tests/test_router.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add io7app/router.py tests/test_router.py
git commit -m "router: # multi-level wildcard support"
```

---

### Task 4: `_subsumes` — pattern containment check

**Files:**
- Modify: `/Users/yhur/tmp/io7app/io7app/router.py`
- Modify: `/Users/yhur/tmp/io7app/tests/test_router.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_router.py`:
```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_router.py::test_subsumes_truth_table -v`
Expected: ImportError — `_subsumes` not defined.

- [ ] **Step 3: Implement `_subsumes`**

Add to `io7app/router.py` (above the `Router` class):

```python
def _subsumes(broader: str, narrower: str) -> bool:
    """True if every topic matching `narrower` also matches `broader`."""
    b = broader.split("/")
    n = narrower.split("/")
    bi = ni = 0
    while bi < len(b) and ni < len(n):
        bs = b[bi]
        ns = n[ni]
        if bs == "#":
            return True  # remaining n consumed by #
        if ns == "#":
            return False  # broader ran out of generality
        if bs == "+":
            bi += 1; ni += 1
            continue
        if bs == ns:
            bi += 1; ni += 1
            continue
        return False
    return bi == len(b) and ni == len(n)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_router.py::test_subsumes_truth_table -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add io7app/router.py tests/test_router.py
git commit -m "router: _subsumes pattern containment helper"
```

---

### Task 5: Router registration consolidation

**Files:**
- Modify: `/Users/yhur/tmp/io7app/io7app/router.py`
- Modify: `/Users/yhur/tmp/io7app/tests/test_router.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_router.py`:
```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_router.py -v -k consolidation`
Expected: failures — consolidation not yet implemented.

- [ ] **Step 3: Replace Router with consolidating version**

Replace `io7app/router.py` with:
```python
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

    @staticmethod
    def _may_overlap(a: str, b: str) -> bool:
        """Heuristic: same first literal segment AND both have wildcards somewhere."""
        ap = a.split("/")
        bp = b.split("/")
        if not ap or not bp:
            return False
        if ap[0] != bp[0] and "+" not in (ap[0], bp[0]) and "#" not in (ap[0], bp[0]):
            return False
        return ("+" in a or "#" in a) and ("+" in b or "#" in b)
```

- [ ] **Step 4: Run all router tests**

Run: `pytest tests/test_router.py -v`
Expected: all consolidation tests pass; previously-passing tests still pass.

- [ ] **Step 5: Commit**

```bash
git add io7app/router.py tests/test_router.py
git commit -m "router: registration-time consolidation with warnings"
```

---

### Task 6: `remove_by_name` + report newly-empty patterns

**Files:**
- Modify: `/Users/yhur/tmp/io7app/io7app/router.py`
- Modify: `/Users/yhur/tmp/io7app/tests/test_router.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_router.py`:
```python
def test_remove_by_name_returns_emptied_patterns():
    r = Router()
    def a(t, p): pass
    def b(t, p): pass
    r.add("iot3/lamp1/evt/status/fmt/json", a, "a")
    r.add("iot3/lamp1/evt/status/fmt/json", b, "b")
    r.add("iot3/+/evt/+/fmt/json", a, "a")
    emptied = r.remove_by_name("a")
    # The +-pattern was a-only; the exact pattern still has b
    assert emptied == {"iot3/+/evt/+/fmt/json"}
    assert len(r.dispatch("iot3/lamp1/evt/status/fmt/json")) == 1


def test_remove_by_name_unknown_returns_empty_set():
    r = Router()
    assert r.remove_by_name("nope") == set()


def test_remove_by_name_removes_all_tiers():
    r = Router()
    def f(t, p): pass
    r.add("iot3/lamp1/evt/status/fmt/json", f, "f")
    r.add("iot3/+/evt/+/fmt/json", f, "f")
    # different name to keep these patterns alive
    def g(t, p): pass
    r.add("iot3/+/cmd/#", g, "g")
    emptied = r.remove_by_name("f")
    # Both f patterns drop. (Note: '+' subsumed exact at registration so only one f-pattern remains.)
    assert "iot3/+/evt/+/fmt/json" in emptied
    # g still works
    assert len(r.dispatch("iot3/lamp1/cmd/lamp/fmt/json")) == 1
    assert r.dispatch("iot3/lamp1/evt/status/fmt/json") == []
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_router.py -v -k remove_by_name`
Expected: AttributeError — `remove_by_name` not defined.

- [ ] **Step 3: Add `remove_by_name` to Router**

Append inside the `Router` class in `io7app/router.py`:

```python
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
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_router.py -v`
Expected: all router tests pass.

- [ ] **Step 5: Commit**

```bash
git add io7app/router.py tests/test_router.py
git commit -m "router: remove_by_name reports newly-empty patterns"
```

---

## Phase 2: Scheduler

### Task 7: Scheduler `every=N` mode + cancel

**Files:**
- Modify: `/Users/yhur/tmp/io7app/io7app/scheduler.py`
- Create: `/Users/yhur/tmp/io7app/tests/test_scheduler.py`

- [ ] **Step 1: Write the failing test**

`tests/test_scheduler.py`:
```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_scheduler.py -v`
Expected: ImportError — Scheduler not defined.

- [ ] **Step 3: Implement Scheduler with `every` + cancel**

`io7app/scheduler.py`:
```python
"""Inject scheduler: one daemon thread per scheduled job."""
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

log = logging.getLogger("io7app")


@dataclass
class _Job:
    name: str
    fn: Callable
    every: float | None = None
    cron: str | None = None
    at: str | None = None
    at_start: bool = False
    payload: dict | None = None
    thread: threading.Thread | None = None
    stop_event: threading.Event = field(default_factory=threading.Event)


class Scheduler:
    def __init__(self):
        self._jobs: dict[str, _Job] = {}
        self._started = False

    def schedule(self, name, fn, *, every=None, cron=None, at=None,
                 at_start=False, payload=None):
        modes = [m for m in (every, cron, at) if m is not None]
        if len(modes) != 1:
            raise ValueError(
                f"@inject requires exactly one of every/cron/at (got {len(modes)})"
            )
        if name in self._jobs:
            raise ValueError(f"duplicate inject name {name!r}")
        job = _Job(name=name, fn=fn, every=every, cron=cron, at=at,
                   at_start=at_start, payload=payload)
        self._jobs[name] = job
        if self._started:
            self._launch(job)

    def cancel(self, name: str) -> bool:
        job = self._jobs.pop(name, None)
        if not job:
            return False
        job.stop_event.set()
        if job.thread:
            job.thread.join(timeout=2.0)
        return True

    def start(self):
        self._started = True
        for job in list(self._jobs.values()):
            self._launch(job)

    def stop(self):
        for name in list(self._jobs):
            self.cancel(name)
        self._started = False

    # --- internals ---

    def _launch(self, job: _Job):
        t = threading.Thread(target=self._run_job, args=(job,), daemon=True,
                             name=f"io7-inject-{job.name}")
        job.thread = t
        t.start()

    def _run_job(self, job: _Job):
        if job.at_start:
            self._fire(job)
        if job.stop_event.is_set():
            return
        if job.every is not None:
            while not job.stop_event.wait(job.every):
                self._fire(job)
                if job.stop_event.is_set():
                    return

    def _fire(self, job: _Job):
        try:
            job.fn(job.payload)
        except Exception:
            log.exception("inject %r raised", job.name)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_scheduler.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add io7app/scheduler.py tests/test_scheduler.py
git commit -m "scheduler: every-mode + cancel"
```

---

### Task 8: Scheduler `at_start=True`

**Files:**
- Modify: `/Users/yhur/tmp/io7app/tests/test_scheduler.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_scheduler.py`:
```python
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
```

- [ ] **Step 2: Run to verify**

Run: `pytest tests/test_scheduler.py::test_at_start_fires_immediately -v`
Expected: PASS already (the implementation handles `at_start` in `_run_job`).

Run: `pytest tests/test_scheduler.py::test_at_start_with_no_other_mode_only_fires_once -v`
Expected: PASS — `schedule` raises since no every/cron/at.

If both pass, no implementation change needed; if either fails, debug.

- [ ] **Step 3: Commit**

```bash
git add tests/test_scheduler.py
git commit -m "scheduler: tests for at_start behavior"
```

---

### Task 9: Scheduler `at="HH:MM"` daily mode

**Files:**
- Modify: `/Users/yhur/tmp/io7app/io7app/scheduler.py`
- Modify: `/Users/yhur/tmp/io7app/tests/test_scheduler.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_scheduler.py`:
```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_scheduler.py -v -k at_mode`
Expected: failures — `_next_fire_for_at` not defined; format validation absent.

- [ ] **Step 3: Implement `at` mode**

Modify `io7app/scheduler.py`:

Add the helper as a static method on `Scheduler`:

```python
    @staticmethod
    def _next_fire_for_at(at: str, now: dt.datetime | None = None) -> dt.datetime:
        try:
            hh, mm = at.split(":")
            hh, mm = int(hh), int(mm)
            assert 0 <= hh < 24 and 0 <= mm < 60
        except (ValueError, AssertionError) as e:
            raise ValueError(f"at= must be 'HH:MM', got {at!r}") from e
        now = now or dt.datetime.now()
        candidate = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if candidate <= now:
            candidate += dt.timedelta(days=1)
        return candidate
```

Add `import datetime as dt` near the top.

Update `schedule()` to validate the format eagerly:

```python
    def schedule(self, name, fn, *, every=None, cron=None, at=None,
                 at_start=False, payload=None):
        modes = [m for m in (every, cron, at) if m is not None]
        if len(modes) != 1:
            raise ValueError(
                f"@inject requires exactly one of every/cron/at (got {len(modes)})"
            )
        if at is not None:
            self._next_fire_for_at(at)  # validate now, raises on bad format
        if name in self._jobs:
            raise ValueError(f"duplicate inject name {name!r}")
        job = _Job(name=name, fn=fn, every=every, cron=cron, at=at,
                   at_start=at_start, payload=payload)
        self._jobs[name] = job
        if self._started:
            self._launch(job)
```

Extend `_run_job` to handle the `at` branch:

```python
    def _run_job(self, job: _Job):
        if job.at_start:
            self._fire(job)
        if job.stop_event.is_set():
            return
        if job.every is not None:
            while not job.stop_event.wait(job.every):
                self._fire(job)
                if job.stop_event.is_set():
                    return
            return
        if job.at is not None:
            while not job.stop_event.is_set():
                next_at = self._next_fire_for_at(job.at)
                wait = (next_at - dt.datetime.now()).total_seconds()
                if wait > 0:
                    if job.stop_event.wait(wait):
                        return
                self._fire(job)
            return
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_scheduler.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add io7app/scheduler.py tests/test_scheduler.py
git commit -m "scheduler: at='HH:MM' daily mode with format validation"
```

---

### Task 10: Scheduler `cron=` mode (lazy croniter)

**Files:**
- Modify: `/Users/yhur/tmp/io7app/io7app/scheduler.py`
- Modify: `/Users/yhur/tmp/io7app/tests/test_scheduler.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_scheduler.py`:
```python
def test_cron_mode_validates_at_register():
    import pytest
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
    real = s._next_fire_for_cron
    def fast(_cron):
        return dt.datetime.now() + dt.timedelta(seconds=0.05)
    s._next_fire_for_cron = fast  # type: ignore

    s.schedule("f", f, cron="* * * * *")
    s.start()
    time.sleep(0.25)
    s.stop()
    assert len(calls) >= 3
```

Add at the top of the file (with other imports if not already present):

```python
import pytest
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_scheduler.py -v -k cron`
Expected: failures — cron mode unimplemented.

- [ ] **Step 3: Implement cron mode**

Modify `io7app/scheduler.py`:

```python
    @staticmethod
    def _next_fire_for_cron(cron: str, now: dt.datetime | None = None) -> dt.datetime:
        try:
            from croniter import croniter
        except ImportError as e:
            raise ImportError(
                "croniter is required for @inject(cron=...). "
                "Install it with: pip install croniter"
            ) from e
        if not croniter.is_valid(cron):
            raise ValueError(f"invalid cron expression: {cron!r}")
        now = now or dt.datetime.now()
        return croniter(cron, now).get_next(dt.datetime)
```

Update `schedule()` to validate cron eagerly:

```python
        if cron is not None:
            self._next_fire_for_cron(cron)  # validates + checks croniter installed
```

(Insert this next to the `at` validation block.)

Extend `_run_job` with the cron branch (after the `at` branch):

```python
        if job.cron is not None:
            while not job.stop_event.is_set():
                next_at = self._next_fire_for_cron(job.cron)
                wait = (next_at - dt.datetime.now()).total_seconds()
                if wait > 0:
                    if job.stop_event.wait(wait):
                        return
                self._fire(job)
            return
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_scheduler.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add io7app/scheduler.py tests/test_scheduler.py
git commit -m "scheduler: cron mode with lazy croniter import"
```

---

### Task 11: Scheduler — pass `t` kwarg when handler signature requests it

**Files:**
- Modify: `/Users/yhur/tmp/io7app/io7app/scheduler.py`
- Modify: `/Users/yhur/tmp/io7app/tests/test_scheduler.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_scheduler.py`:
```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_scheduler.py::test_inject_with_t_param -v`
Expected: TypeError — `f` requires positional `t` but only `payload` passed.

- [ ] **Step 3: Use signature inspection in `_fire`**

Modify `_fire` in `io7app/scheduler.py`:

```python
import inspect

# ...

    def _fire(self, job: _Job):
        try:
            sig = inspect.signature(job.fn)
            kwargs = {}
            if "t" in sig.parameters:
                kwargs["t"] = time.time()
            job.fn(job.payload, **kwargs)
        except Exception:
            log.exception("inject %r raised", job.name)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_scheduler.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add io7app/scheduler.py tests/test_scheduler.py
git commit -m "scheduler: pass t= kwarg when handler declares it"
```

---

## Phase 3: App — config, paho wiring, decoder

### Task 12: `App` config loading from `.env` + kwargs

**Files:**
- Modify: `/Users/yhur/tmp/io7app/io7app/app.py`
- Create: `/Users/yhur/tmp/io7app/tests/test_app.py`
- Modify: `/Users/yhur/tmp/io7app/tests/conftest.py`

- [ ] **Step 1: Write the failing test**

`tests/test_app.py`:
```python
import pytest
from io7app.app import App


def test_kwargs_override_env(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("IO7_SERVER=fromenv\nIO7_APP_ID=A\nIO7_TOKEN=T\n")
    monkeypatch.chdir(tmp_path)
    app = App(server="explicit", env_path=str(env_file), _connect=False)
    assert app.server == "explicit"
    assert app.app_id == "A"
    assert app.token == "T"


def test_env_loaded(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("IO7_SERVER=fromenv\nIO7_APP_ID=A\nIO7_TOKEN=T\n")
    monkeypatch.chdir(tmp_path)
    app = App(env_path=str(env_file), _connect=False)
    assert app.server == "fromenv"
    assert app.app_id == "A"
    assert app.token == "T"


def test_missing_config_raises(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("IO7_SERVER", raising=False)
    monkeypatch.delenv("IO7_APP_ID", raising=False)
    monkeypatch.delenv("IO7_TOKEN", raising=False)
    with pytest.raises(RuntimeError):
        App(_connect=False)
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_app.py -v`
Expected: failures — `App` not implementing config loading.

- [ ] **Step 3: Implement config loading**

Replace `io7app/app.py`:
```python
"""App class: wires paho-mqtt, Router, Scheduler."""
import logging
import os
from typing import Optional

from dotenv import load_dotenv

from io7app.router import Router
from io7app.scheduler import Scheduler

log = logging.getLogger("io7app")


class App:
    def __init__(
        self,
        server: Optional[str] = None,
        app_id: Optional[str] = None,
        token: Optional[str] = None,
        port: Optional[int] = None,
        ca: Optional[str] = None,
        env_path: str = ".env",
        _connect: bool = True,  # test hook to skip MQTT connect
    ):
        # 1. Load .env if present
        if env_path and os.path.exists(env_path):
            load_dotenv(env_path, override=False)

        # 2. Resolve config: kwargs > env vars
        self.server = server or os.getenv("IO7_SERVER")
        self.app_id = app_id or os.getenv("IO7_APP_ID")
        self.token = token or os.getenv("IO7_TOKEN")
        env_port = os.getenv("IO7_PORT")
        env_ca = os.getenv("IO7_CA")
        self.ca = ca if ca is not None else env_ca
        # Auto-detect ca.pem in cwd if no explicit ca
        if not self.ca and os.path.exists("ca.pem"):
            self.ca = "ca.pem"
        # Port default depends on TLS
        default_port = 8883 if self.ca else 1883
        if port is not None:
            self.port = port
        elif env_port:
            self.port = int(env_port)
        else:
            self.port = default_port

        missing = [k for k, v in (
            ("IO7_SERVER", self.server),
            ("IO7_APP_ID", self.app_id),
            ("IO7_TOKEN", self.token),
        ) if not v]
        if missing:
            raise RuntimeError(
                f"missing io7 config: {', '.join(missing)}. "
                f"Set them in .env or pass to App(server=, app_id=, token=)."
            )

        self._router = Router()
        self._scheduler = Scheduler()
        self._client = None
        self._running = False

        if _connect:
            self._build_client()

    @classmethod
    def from_env(cls, env_path: str = ".env", **kwargs):
        return cls(env_path=env_path, **kwargs)

    def _build_client(self):
        # placeholder; populated in next task
        pass
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_app.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add io7app/app.py tests/test_app.py
git commit -m "app: config loading from .env + kwargs with port/ca defaults"
```

---

### Task 13: TLS auto-detection

**Files:**
- Modify: `/Users/yhur/tmp/io7app/tests/test_app.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_app.py`:
```python
def test_tls_auto_detect_from_kwarg(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IO7_SERVER", "h")
    monkeypatch.setenv("IO7_APP_ID", "a")
    monkeypatch.setenv("IO7_TOKEN", "t")
    (tmp_path / "myca.pem").write_text("dummy")
    app = App(ca=str(tmp_path / "myca.pem"), _connect=False)
    assert app.ca == str(tmp_path / "myca.pem")
    assert app.port == 8883


def test_tls_auto_detect_from_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IO7_SERVER", "h")
    monkeypatch.setenv("IO7_APP_ID", "a")
    monkeypatch.setenv("IO7_TOKEN", "t")
    monkeypatch.setenv("IO7_CA", "envca.pem")
    app = App(_connect=False)
    assert app.ca == "envca.pem"
    assert app.port == 8883


def test_tls_auto_detect_from_capem_in_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IO7_SERVER", "h")
    monkeypatch.setenv("IO7_APP_ID", "a")
    monkeypatch.setenv("IO7_TOKEN", "t")
    monkeypatch.delenv("IO7_CA", raising=False)
    (tmp_path / "ca.pem").write_text("dummy")
    app = App(_connect=False)
    assert app.ca == "ca.pem"
    assert app.port == 8883


def test_no_tls_default_port_1883(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IO7_SERVER", "h")
    monkeypatch.setenv("IO7_APP_ID", "a")
    monkeypatch.setenv("IO7_TOKEN", "t")
    monkeypatch.delenv("IO7_CA", raising=False)
    app = App(_connect=False)
    assert app.ca is None
    assert app.port == 1883


def test_explicit_port_overrides_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IO7_SERVER", "h")
    monkeypatch.setenv("IO7_APP_ID", "a")
    monkeypatch.setenv("IO7_TOKEN", "t")
    (tmp_path / "ca.pem").write_text("dummy")
    app = App(port=9999, _connect=False)
    assert app.port == 9999
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_app.py -v -k tls`
Expected: PASS — the existing config-loading code already handles this.

If any fails, fix `App.__init__`'s port-resolution logic.

- [ ] **Step 3: Commit**

```bash
git add tests/test_app.py
git commit -m "app: tests covering TLS auto-detection"
```

---

### Task 14: FakeMQTTClient fixture + paho wiring

**Files:**
- Modify: `/Users/yhur/tmp/io7app/tests/conftest.py`
- Modify: `/Users/yhur/tmp/io7app/io7app/app.py`
- Modify: `/Users/yhur/tmp/io7app/tests/test_app.py`

- [ ] **Step 1: Write the FakeMQTTClient and the failing test**

Replace `tests/conftest.py`:
```python
"""Shared test fixtures."""
import pytest


class FakeMessage:
    def __init__(self, topic, payload):
        self.topic = topic
        self.payload = payload if isinstance(payload, (bytes, bytearray)) else payload.encode()


class FakeMQTTClient:
    """Stands in for paho.mqtt.client.Client. Records calls and lets tests inject messages."""
    def __init__(self):
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self.published: list[tuple[str, bytes, int, bool]] = []
        self.connected = False
        self.tls_set_calls: list[dict] = []
        self.username_pw: tuple | None = None
        self.client_id = None
        self.on_connect = None
        self.on_message = None

    # paho-mqtt API surface used by App
    def username_pw_set(self, user, pw):
        self.username_pw = (user, pw)

    def tls_set(self, **kwargs):
        self.tls_set_calls.append(kwargs)

    def connect(self, host, port, keepalive=60):
        self.host = host
        self.port = port
        self.connected = True
        if self.on_connect:
            self.on_connect(self, None, None, 0)

    def disconnect(self):
        self.connected = False

    def loop_start(self):
        pass

    def loop_forever(self):
        pass

    def loop_stop(self):
        pass

    def subscribe(self, topic, qos=0):
        self.subscribed.append(topic)

    def unsubscribe(self, topic):
        self.unsubscribed.append(topic)

    def publish(self, topic, payload, qos=0, retain=False):
        b = payload.encode() if isinstance(payload, str) else payload
        self.published.append((topic, b, qos, retain))

    # Test helper
    def deliver(self, topic, payload):
        if self.on_message:
            self.on_message(self, None, FakeMessage(topic, payload))


@pytest.fixture
def fake_client():
    return FakeMQTTClient()


@pytest.fixture
def app(monkeypatch, tmp_path, fake_client):
    """Build an App with FakeMQTTClient injected."""
    from io7app.app import App
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IO7_SERVER", "h")
    monkeypatch.setenv("IO7_APP_ID", "testapp")
    monkeypatch.setenv("IO7_TOKEN", "t")
    monkeypatch.delenv("IO7_CA", raising=False)
    monkeypatch.setattr(
        "io7app.app._build_mqtt_client",
        lambda app_id, token, ca: fake_client,
    )
    a = App(_connect=True)
    return a
```

Append to `tests/test_app.py`:
```python
def test_paho_client_built_with_credentials(app, fake_client):
    assert fake_client.username_pw == ("testapp", "t")
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_app.py::test_paho_client_built_with_credentials -v`
Expected: AttributeError — `_build_mqtt_client` not present.

- [ ] **Step 3: Add paho-mqtt wiring to App**

Modify `io7app/app.py`:

Add at the top:
```python
import json
import paho.mqtt.client as mqtt
```

Add module-level builder function:
```python
def _build_mqtt_client(app_id: str, token: str, ca: str | None) -> mqtt.Client:
    client = mqtt.Client(client_id=app_id, clean_session=True)
    client.username_pw_set(app_id, token)
    if ca:
        client.tls_set(ca_certs=ca)
    return client
```

Replace `_build_client` method:
```python
    def _build_client(self):
        self._client = _build_mqtt_client(self.app_id, self.token, self.ca)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, rc):
        if rc != 0:
            log.warning("io7 connect failed rc=%s", rc)
            return
        log.info("io7 connected as %s", self.app_id)
        # Re-subscribe to all currently-registered patterns
        for pattern in self._registered_patterns():
            self._client.subscribe(pattern)

    def _on_message(self, client, userdata, msg):
        # Filled in next task
        pass

    def _registered_patterns(self) -> set[str]:
        patterns: set[str] = set()
        patterns.update(self._router._exact.keys())
        patterns.update(p for _, _, p in self._router._single)
        patterns.update(p for _, _, p in self._router._multi)
        return patterns
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_app.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add io7app/app.py tests/conftest.py tests/test_app.py
git commit -m "app: paho-mqtt client wiring + FakeMQTTClient fixture"
```

---

### Task 15: `@app.on(pattern)` decorator + envelope unwrap + signature dispatch

**Files:**
- Modify: `/Users/yhur/tmp/io7app/io7app/app.py`
- Modify: `/Users/yhur/tmp/io7app/tests/test_app.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_app.py`:
```python
def test_on_decorator_registers_and_subscribes(app, fake_client):
    @app.on("iot3/lamp1/evt/status/fmt/json")
    def h(data):
        pass
    assert "iot3/lamp1/evt/status/fmt/json" in fake_client.subscribed


def test_unwraps_d(app, fake_client):
    seen = []
    @app.on("iot3/lamp1/evt/status/fmt/json")
    def h(data):
        seen.append(data)
    fake_client.deliver("iot3/lamp1/evt/status/fmt/json",
                        '{"d": {"lamp": "on"}, "t": 123}')
    assert seen == [{"lamp": "on"}]


def test_drops_when_no_d(app, fake_client):
    seen = []
    @app.on("iot3/lamp1/evt/status/fmt/json")
    def h(data):
        seen.append(data)
    fake_client.deliver("iot3/lamp1/evt/status/fmt/json", '{"oops": "no d"}')
    assert seen == []


def test_drops_when_not_dict(app, fake_client):
    seen = []
    @app.on("iot3/lamp1/evt/status/fmt/json")
    def h(data):
        seen.append(data)
    fake_client.deliver("iot3/lamp1/evt/status/fmt/json", '"just a string"')
    assert seen == []


def test_drops_malformed_json(app, fake_client, caplog):
    import logging
    seen = []
    @app.on("iot3/lamp1/evt/status/fmt/json")
    def h(data):
        seen.append(data)
    with caplog.at_level(logging.WARNING, logger="io7app"):
        fake_client.deliver("iot3/lamp1/evt/status/fmt/json", "{not json")
    assert seen == []
    assert any("malformed json" in r.message.lower() for r in caplog.records)


def test_signature_one_arg(app, fake_client):
    seen = []
    @app.on("iot3/lamp1/evt/status/fmt/json")
    def h(data):
        seen.append(data)
    fake_client.deliver("iot3/lamp1/evt/status/fmt/json", '{"d": {"x": 1}}')
    assert seen == [{"x": 1}]


def test_signature_two_args_topic_data(app, fake_client):
    seen = []
    @app.on("iot3/+/evt/+/fmt/json")
    def h(topic, data):
        seen.append((topic, data))
    fake_client.deliver("iot3/lamp1/evt/status/fmt/json", '{"d": {"x": 1}}')
    assert seen == [("iot3/lamp1/evt/status/fmt/json", {"x": 1})]


def test_signature_with_t(app, fake_client):
    seen = []
    @app.on("iot3/lamp1/evt/status/fmt/json")
    def h(data, t):
        seen.append((data, t))
    fake_client.deliver(
        "iot3/lamp1/evt/status/fmt/json", '{"d": {"x": 1}, "t": 999}')
    assert seen == [({"x": 1}, 999)]


def test_signature_with_topic_and_t(app, fake_client):
    seen = []
    @app.on("iot3/+/evt/+/fmt/json")
    def h(topic, data, t):
        seen.append((topic, data, t))
    fake_client.deliver(
        "iot3/lamp1/evt/status/fmt/json", '{"d": {"x": 1}, "t": 42}')
    assert seen == [("iot3/lamp1/evt/status/fmt/json", {"x": 1}, 42)]


def test_t_none_when_envelope_missing_t(app, fake_client):
    seen = []
    @app.on("iot3/lamp1/evt/status/fmt/json")
    def h(data, t):
        seen.append((data, t))
    fake_client.deliver("iot3/lamp1/evt/status/fmt/json", '{"d": {"x": 1}}')
    assert seen == [({"x": 1}, None)]


def test_utf8_format_no_unwrap(app, fake_client):
    seen = []
    @app.on("iot3/lamp1/evt/status/fmt/utf8")
    def h(data):
        seen.append(data)
    fake_client.deliver("iot3/lamp1/evt/status/fmt/utf8", "hello")
    assert seen == ["hello"]
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_app.py -v -k "on_decorator or unwraps or drops or signature or utf8 or t_none"`
Expected: failures — `App.on` not defined.

- [ ] **Step 3: Implement `@app.on` + decoder + dispatch**

Modify `io7app/app.py`:

Add `import inspect` and `import json` at the top.

Add inside `App` class:

```python
    def on(self, pattern: str):
        """Decorator: register `fn` as a handler for the topic `pattern`."""
        def decorator(fn):
            name = fn.__name__
            is_new = self._router.add(pattern, fn, name)
            if is_new and self._client is not None and self._client.connected:
                self._client.subscribe(pattern)
            elif is_new and self._client is not None:
                # not yet connected; connect-time on_connect resubscribes from router
                self._client.subscribe(pattern)
            return fn
        return decorator

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        raw = msg.payload
        entries = self._router.dispatch(topic)
        if not entries:
            return
        # Group decode by fmt
        for entry in entries:
            try:
                args = self._decode_for_entry(topic, raw, entry)
            except _DropMessage:
                continue
            try:
                self._invoke(entry.handler, topic, args["data"], args["t"])
            except Exception:
                log.exception("handler %r raised", entry.name)

    def _decode_for_entry(self, topic, raw, entry):
        fmt = entry.fmt
        if fmt == "json":
            try:
                body = json.loads(raw)
            except (ValueError, TypeError):
                log.warning("malformed json on %s", topic)
                raise _DropMessage
            if not isinstance(body, dict) or "d" not in body:
                raise _DropMessage  # silent drop per PRD #7
            return {"data": body["d"], "t": body.get("t")}
        if fmt == "utf8":
            try:
                return {"data": raw.decode("utf-8"), "t": None}
            except UnicodeDecodeError:
                raise _DropMessage
        # raw bytes
        return {"data": bytes(raw), "t": None}

    def _invoke(self, fn, topic, data, t):
        sig = self._sig_cache(fn)
        params = list(sig.parameters)
        n = len(params)
        wants_t = "t" in sig.parameters
        if n == 1:
            fn(data)
        elif n == 2 and not wants_t:
            fn(topic, data)
        elif n == 2 and wants_t:
            fn(data, t)
        elif n == 3 and wants_t:
            fn(topic, data, t)
        else:
            raise TypeError(
                f"unsupported handler signature for {fn.__name__}: {sig}"
            )

    def _sig_cache(self, fn):
        cache = getattr(self, "_sigs", None)
        if cache is None:
            cache = self._sigs = {}
        s = cache.get(fn)
        if s is None:
            s = inspect.signature(fn)
            cache[fn] = s
        return s


class _DropMessage(Exception):
    """Internal: raise to indicate a message should be silently dropped."""
```

(Place `_DropMessage` at module level above `App`.)

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_app.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add io7app/app.py tests/test_app.py
git commit -m "app: @on decorator, envelope unwrap, signature dispatch"
```

---

### Task 16: `@app.on_event(device, event)` sugar

**Files:**
- Modify: `/Users/yhur/tmp/io7app/io7app/app.py`
- Modify: `/Users/yhur/tmp/io7app/tests/test_app.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_app.py`:
```python
def test_on_event_topic_built(app, fake_client):
    @app.on_event("thermo1", "status")
    def h(data):
        pass
    assert "iot3/thermo1/evt/status/fmt/json" in fake_client.subscribed


def test_on_event_with_wildcards(app, fake_client):
    @app.on_event("+", "status")
    def h(topic, data):
        pass
    assert "iot3/+/evt/status/fmt/json" in fake_client.subscribed


def test_switch_lamp_round_trip(app, fake_client):
    @app.on_event("switch1", "status")
    def on_switch(data):
        app.send_cmd("lamp1", "lamp", {"lamp": data["switch"]})
    fake_client.deliver("iot3/switch1/evt/status/fmt/json",
                        '{"d": {"switch": "on"}}')
    assert fake_client.published, "no command published"
    topic, body, qos, retain = fake_client.published[0]
    assert topic == "iot3/lamp1/cmd/lamp/fmt/json"
    import json
    assert json.loads(body) == {"d": {"lamp": "on"}}
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_app.py -v -k "on_event or switch_lamp"`
Expected: failures — `on_event` and `send_cmd` not defined.

- [ ] **Step 3: Implement `on_event` and `send_cmd`**

Add to `App` class in `io7app/app.py`:

```python
    def on_event(self, device_id: str, event_id: str, fmt: str = "json"):
        topic = f"iot3/{device_id}/evt/{event_id}/fmt/{fmt}"
        return self.on(topic)

    def send_cmd(self, device_id: str, cmd_id: str, data, *,
                 fmt: str = "json", qos: int = 0, retain: bool = False):
        topic = f"iot3/{device_id}/cmd/{cmd_id}/fmt/{fmt}"
        body = {"d": data}
        if fmt == "json":
            payload = json.dumps(body).encode()
        elif fmt == "utf8":
            payload = str(body).encode()
        else:
            payload = body  # caller's responsibility for non-text fmts
        self._client.publish(topic, payload, qos=qos, retain=retain)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_app.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add io7app/app.py tests/test_app.py
git commit -m "app: on_event sugar + send_cmd auto-wraps {'d': data}"
```

---

### Task 17: `app.publish(topic, payload)` raw escape hatch

**Files:**
- Modify: `/Users/yhur/tmp/io7app/io7app/app.py`
- Modify: `/Users/yhur/tmp/io7app/tests/test_app.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_app.py`:
```python
def test_publish_raw_no_wrap(app, fake_client):
    app.publish("dashboard/foo", {"alive": True})
    assert fake_client.published
    topic, body, _, _ = fake_client.published[0]
    assert topic == "dashboard/foo"
    import json
    assert json.loads(body) == {"alive": True}  # not wrapped in 'd'
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_app.py::test_publish_raw_no_wrap -v`
Expected: AttributeError — `publish` not defined.

- [ ] **Step 3: Implement `publish`**

Add to `App` class:
```python
    def publish(self, topic: str, payload, *,
                fmt: str = "json", qos: int = 0, retain: bool = False):
        if fmt == "json":
            body = json.dumps(payload).encode()
        elif fmt == "utf8":
            body = payload.encode() if isinstance(payload, str) else bytes(payload)
        else:
            body = payload  # bytes
        self._client.publish(topic, body, qos=qos, retain=retain)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_app.py::test_publish_raw_no_wrap -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add io7app/app.py tests/test_app.py
git commit -m "app: publish raw escape hatch (no envelope wrapping)"
```

---

### Task 18: `@app.inject(...)` decorator

**Files:**
- Modify: `/Users/yhur/tmp/io7app/io7app/app.py`
- Modify: `/Users/yhur/tmp/io7app/tests/test_app.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_app.py`:
```python
def test_inject_registers_with_scheduler(app):
    @app.inject(every=0.05, payload={"k": 1})
    def heartbeat(data):
        pass
    # Job is registered; scheduler not started yet (run() does that)
    assert "heartbeat" in app._scheduler._jobs
    job = app._scheduler._jobs["heartbeat"]
    assert job.every == 0.05
    assert job.payload == {"k": 1}


def test_inject_validates_modes(app):
    import pytest
    with pytest.raises(ValueError):
        @app.inject()  # no mode
        def bad(d): pass
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_app.py -v -k inject`
Expected: AttributeError — `inject` not defined.

- [ ] **Step 3: Implement `@app.inject`**

Add to `App` class:
```python
    def inject(self, *, every=None, cron=None, at=None,
               at_start=False, payload=None):
        def decorator(fn):
            self._scheduler.schedule(
                fn.__name__, fn,
                every=every, cron=cron, at=at,
                at_start=at_start, payload=payload,
            )
            return fn
        return decorator
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_app.py -v -k inject`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add io7app/app.py tests/test_app.py
git commit -m "app: @inject decorator delegates to Scheduler"
```

---

### Task 19: `app.unregister(name)` — removes router + scheduler entries, unsubscribes

**Files:**
- Modify: `/Users/yhur/tmp/io7app/io7app/app.py`
- Modify: `/Users/yhur/tmp/io7app/tests/test_app.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_app.py`:
```python
def test_unregister_removes_handler(app, fake_client):
    seen = []
    @app.on_event("lamp1", "status")
    def h(data):
        seen.append(data)
    fake_client.deliver("iot3/lamp1/evt/status/fmt/json", '{"d": {"x": 1}}')
    assert seen == [{"x": 1}]
    app.unregister("h")
    fake_client.deliver("iot3/lamp1/evt/status/fmt/json", '{"d": {"x": 2}}')
    assert seen == [{"x": 1}]  # no further calls


def test_unregister_unsubscribes_when_pattern_empty(app, fake_client):
    @app.on_event("lamp1", "status")
    def h(data):
        pass
    assert "iot3/lamp1/evt/status/fmt/json" in fake_client.subscribed
    app.unregister("h")
    assert "iot3/lamp1/evt/status/fmt/json" in fake_client.unsubscribed


def test_unregister_keeps_pattern_alive_if_other_handlers(app, fake_client):
    @app.on_event("lamp1", "status")
    def a(data):
        pass
    @app.on_event("lamp1", "status")
    def b(data):
        pass
    app.unregister("a")
    assert "iot3/lamp1/evt/status/fmt/json" not in fake_client.unsubscribed


def test_unregister_cancels_inject(app):
    @app.inject(every=0.05)
    def beat(data):
        pass
    assert "beat" in app._scheduler._jobs
    app.unregister("beat")
    assert "beat" not in app._scheduler._jobs
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_app.py -v -k unregister`
Expected: AttributeError — `unregister` not defined.

- [ ] **Step 3: Implement `unregister`**

Add to `App` class:
```python
    def unregister(self, name: str) -> None:
        emptied = self._router.remove_by_name(name)
        if self._client is not None:
            for pattern in emptied:
                self._client.unsubscribe(pattern)
        # Cancel any inject by this name
        self._scheduler.cancel(name)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_app.py -v -k unregister`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add io7app/app.py tests/test_app.py
git commit -m "app: unregister(name) clears router + scheduler, unsubscribes empty patterns"
```

---

### Task 20: `run()` and `stop()` lifecycle + reconnect resubscribe

**Files:**
- Modify: `/Users/yhur/tmp/io7app/io7app/app.py`
- Modify: `/Users/yhur/tmp/io7app/tests/test_app.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_app.py`:
```python
def test_run_subscribes_all(app, fake_client):
    @app.on_event("lamp1", "status")
    def a(data):
        pass
    @app.on_event("thermo1", "status")
    def b(data):
        pass
    app.run(_block=False)
    assert "iot3/lamp1/evt/status/fmt/json" in fake_client.subscribed
    assert "iot3/thermo1/evt/status/fmt/json" in fake_client.subscribed
    app.stop()


def test_resubscribes_on_reconnect(app, fake_client):
    @app.on_event("lamp1", "status")
    def a(data):
        pass
    fake_client.subscribed.clear()
    # Simulate paho firing on_connect again after a reconnect
    fake_client.on_connect(fake_client, None, None, 0)
    assert "iot3/lamp1/evt/status/fmt/json" in fake_client.subscribed


def test_stop_cancels_scheduler(app, fake_client):
    @app.inject(every=0.05)
    def beat(d): pass
    app.run(_block=False)
    app.stop()
    assert "beat" not in app._scheduler._jobs or \
           app._scheduler._jobs["beat"].stop_event.is_set()
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_app.py -v -k "run_subscribes or resubscribes or stop_cancels"`
Expected: failures — `run`, `stop` missing or incomplete.

- [ ] **Step 3: Implement `run` and `stop`**

Add to `App` class:
```python
    def run(self, _block: bool = True):
        """Connect to broker, start scheduler, block on the MQTT loop."""
        if self._client is None:
            self._build_client()
        self._client.connect(self.server, self.port, keepalive=60)
        self._scheduler.start()
        self._running = True
        if _block:
            try:
                self._client.loop_forever()
            except KeyboardInterrupt:
                pass
            finally:
                self.stop()
        else:
            self._client.loop_start()

    def stop(self):
        if not self._running:
            return
        self._running = False
        self._scheduler.stop()
        if self._client is not None:
            try:
                self._client.loop_stop()
            except Exception:
                pass
            self._client.disconnect()
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_app.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add io7app/app.py tests/test_app.py
git commit -m "app: run/stop lifecycle, scheduler integration, reconnect resubscribe"
```

---

## Phase 4: Examples + final docs

### Task 21: Write the five example apps

**Files:**
- Create: `/Users/yhur/tmp/io7app/examples/01_switch_lamp.py`
- Create: `/Users/yhur/tmp/io7app/examples/02_thermostat_valve.py`
- Create: `/Users/yhur/tmp/io7app/examples/03_lux_auto_lamp.py`
- Create: `/Users/yhur/tmp/io7app/examples/04_scheduled_inject.py`
- Create: `/Users/yhur/tmp/io7app/examples/05_wildcard_trace.py`
- Create: `/Users/yhur/tmp/io7app/tests/test_examples.py`

- [ ] **Step 1: Write the example test that imports each module and asserts the expected handler is registered**

`tests/test_examples.py`:
```python
import importlib.util
import sys
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def _load(modname, app_fixture, monkeypatch):
    """Patch App so the example's `App()` returns our test app, then import."""
    from io7app import app as app_mod
    monkeypatch.setattr(app_mod, "App", lambda *a, **k: app_fixture)
    path = EXAMPLES / f"{modname}.py"
    spec = importlib.util.spec_from_file_location(modname, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[modname] = m
    # The example calls app.run(); patch run to no-op
    app_fixture.run = lambda *a, **k: None
    spec.loader.exec_module(m)
    return m


def test_switch_lamp(app, fake_client, monkeypatch):
    _load("01_switch_lamp", app, monkeypatch)
    assert "iot3/switch1/evt/status/fmt/json" in fake_client.subscribed
    fake_client.deliver("iot3/switch1/evt/status/fmt/json",
                        '{"d": {"switch": "on"}}')
    assert any(t == "iot3/lamp1/cmd/lamp/fmt/json"
               for t, *_ in fake_client.published)


def test_thermostat_valve(app, fake_client, monkeypatch):
    _load("02_thermostat_valve", app, monkeypatch)
    assert "iot3/thermo1/evt/status/fmt/json" in fake_client.subscribed
    # Cold reading drives valve on
    fake_client.deliver("iot3/thermo1/evt/status/fmt/json",
                        '{"d": {"temperature": 18.0, "target": 22.0}}')
    cmds = [t for t, *_ in fake_client.published]
    assert "iot3/valve1/cmd/valve/fmt/json" in cmds


def test_lux_auto_lamp(app, fake_client, monkeypatch):
    _load("03_lux_auto_lamp", app, monkeypatch)
    assert "iot3/lux1/evt/status/fmt/json" in fake_client.subscribed
    fake_client.deliver("iot3/lux1/evt/status/fmt/json", '{"d": {"lux": 10}}')
    assert any(t == "iot3/lamp1/cmd/lamp/fmt/json"
               for t, *_ in fake_client.published)


def test_scheduled_inject(app, fake_client, monkeypatch):
    _load("04_scheduled_inject", app, monkeypatch)
    assert any(name in app._scheduler._jobs
               for name in ("morning", "refresh"))


def test_wildcard_trace(app, fake_client, monkeypatch):
    _load("05_wildcard_trace", app, monkeypatch)
    assert "iot3/+/evt/+/fmt/json" in fake_client.subscribed
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_examples.py -v`
Expected: FileNotFoundError or import errors — example files don't exist yet.

- [ ] **Step 3: Write each example file**

`examples/01_switch_lamp.py`:
```python
"""Switch -> Lamp mirror. Pairs with iotlab101/3.iot-lamp-switch."""
from io7app import App

app = App()


@app.on_event("switch1", "status")
def on_switch(data):
    app.send_cmd("lamp1", "lamp", {"lamp": data["switch"]})


if __name__ == "__main__":
    app.run()
```

`examples/02_thermostat_valve.py`:
```python
"""Thermostat -> Valve with hysteresis. Pairs with iotlab101/12.io7Thermostat."""
from io7app import App

app = App()
state = {"valve": "off"}


@app.on_event("thermo1", "status")
def thermostat(data):
    temp = data["temperature"]
    target = data.get("target", 22.0)
    desired = (
        "on" if temp < target - 0.5
        else "off" if temp > target + 0.5
        else state["valve"]
    )
    if desired != state["valve"]:
        state["valve"] = desired
        app.send_cmd("valve1", "valve", {"valve": desired})


if __name__ == "__main__":
    app.run()
```

`examples/03_lux_auto_lamp.py`:
```python
"""Auto-lamp from light sensor. Pairs with iotlab101/5.io7uLux02."""
from io7app import App

app = App()


@app.on_event("lux1", "status")
def auto_lamp(data):
    desired = "on" if data["lux"] < 50 else "off"
    app.send_cmd("lamp1", "lamp", {"lamp": desired})


if __name__ == "__main__":
    app.run()
```

`examples/04_scheduled_inject.py`:
```python
"""Cron + interval scheduling. Daily morning lamp on; periodic command refresh."""
from io7app import App

app = App()
last_state = {"lamp": "off"}


@app.inject(cron="0 7 * * *", payload={"lamp": "on"})
def morning(data):
    last_state["lamp"] = data["lamp"]
    app.send_cmd("lamp1", "lamp", data)


@app.inject(every=300)
def refresh(data):
    """Re-send the desired state every 5 minutes -- defends against missed messages."""
    app.send_cmd("lamp1", "lamp", {"lamp": last_state["lamp"]})


if __name__ == "__main__":
    app.run()
```

`examples/05_wildcard_trace.py`:
```python
"""Cross-device trace; demonstrates dynamic unregister."""
import threading
from io7app import App

app = App()


@app.on("iot3/+/evt/+/fmt/json")
def trace(topic, data):
    print(f"[{topic}] {data}")


def stop_tracing_after(delay):
    threading.Timer(delay, lambda: app.unregister("trace")).start()


if __name__ == "__main__":
    stop_tracing_after(60)  # auto-stop after 60s
    app.run()
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_examples.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add examples/ tests/test_examples.py
git commit -m "examples: switch/lamp, thermostat/valve, lux, scheduled, wildcard trace"
```

---

### Task 22: README + run full test suite

**Files:**
- Create: `/Users/yhur/tmp/io7app/README.md`

- [ ] **Step 1: Write `README.md`**

```markdown
# io7app

A small Python framework for writing **io7 IoT app servers**.

```python
from io7app import App
app = App()

@app.on_event("switch1", "status")
def on_switch(data):
    app.send_cmd("lamp1", "lamp", {"lamp": data["switch"]})

app.run()
```

- See **[USER_GUIDE.md](USER_GUIDE.md)** for the full guide and examples.
- See **[docs/superpowers/specs/](docs/superpowers/specs/)** for the design.
- Devices publish events; apps publish commands. This library is the **app side** only.

## Install

```bash
pip install io7app
# Optional, for @inject(cron=...):
pip install croniter
```

## Configure

Drop a `.env` next to your script (see `.env.example`). TLS auto-engages if `IO7_CA` is set or `ca.pem` is in cwd.

## Test

```bash
pip install -e ".[dev]"
pytest
```
```

- [ ] **Step 2: Run the full test suite**

Run: `pytest -v`
Expected: every test in `test_router.py`, `test_scheduler.py`, `test_app.py`, `test_examples.py` passes.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: README pointing to USER_GUIDE.md and design"
```

---

## Self-review

**Spec coverage check:**

| Spec section | Covered by task |
|---|---|
| Router `add` / `dispatch` (exact) | Task 1 |
| Router `+` wildcard | Task 2 |
| Router `#` wildcard | Task 3 |
| `_subsumes` containment | Task 4 |
| Registration consolidation rules | Task 5 |
| `remove_by_name` + empty-pattern report | Task 6 |
| Scheduler `every`/cancel | Task 7 |
| Scheduler `at_start` | Task 8 |
| Scheduler `at="HH:MM"` | Task 9 |
| Scheduler `cron=` (lazy croniter) | Task 10 |
| Scheduler `t` kwarg pass-through | Task 11 |
| `App` config from `.env` + kwargs | Task 12 |
| TLS auto-detect (kwarg / env / `ca.pem`) | Task 13 |
| paho client wiring + reconnect resubscribe | Tasks 14, 20 |
| `@app.on` + envelope unwrap (PRD #7) | Task 15 |
| Signature dispatch (4 forms) | Task 15 |
| Malformed JSON dropped, non-`d` silently dropped | Task 15 |
| `@app.on_event` sugar | Task 16 |
| `send_cmd` auto-wrap | Task 16 |
| `publish` raw escape hatch | Task 17 |
| `@app.inject` | Task 18 |
| `app.unregister(name)` | Task 19 |
| `run` / `stop` | Task 20 |
| Examples 01–05 | Task 21 |
| README | Task 22 |

PRD requirements 0–8 are all covered. The USER_GUIDE.md "Tested by:" tags are honored by the test names defined in this plan.

**Type/method consistency check:** `App._client`, `App._router`, `App._scheduler` are referenced consistently. `Entry` namedtuple fields (`handler`, `name`, `pattern`, `fmt`) are consistent across router code and tests. The `_DropMessage` exception name is consistent.

No placeholders remain.
