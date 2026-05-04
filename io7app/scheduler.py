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
