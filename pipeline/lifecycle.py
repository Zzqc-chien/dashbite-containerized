"""Process lifecycle helpers shared by the worker stages.

Stdlib only, so the health probe can import it cheaply.

- ``StopFlag``: set by a signal handler, polled by the run loop.
- ``install_stop_handlers``: route SIGTERM and SIGINT to a ``StopFlag``.
- ``beat`` / ``heartbeat_path``: touch ``$HEARTBEAT_DIR/<stage>.heartbeat``
  after every loop iteration (no-op when ``HEARTBEAT_DIR`` is unset).
- ``run_forever``: the shared *step -> beat -> sleep* loop.
"""

from __future__ import annotations

import os
import signal
import time
from pathlib import Path
from typing import Callable

__all__ = [
    "StopFlag",
    "install_stop_handlers",
    "heartbeat_path",
    "beat",
    "run_forever",
]

# How often StopFlag.sleep checks for a stop request.
_SLEEP_SLICE_SECONDS = 0.2


class StopFlag:
    """A stop request that is safe to set from a signal handler.

    A plain bool rather than ``threading.Event``: ``Event.set()`` takes a
    non-reentrant lock, so a handler running while the main thread is inside
    ``Event.wait()`` could deadlock. Assigning a bool cannot.
    """

    def __init__(self) -> None:
        self.requested = False

    def request(self, *_: object) -> None:
        """Ask the loop to stop. Signature fits ``signal.signal`` handlers."""
        self.requested = True

    def sleep(self, seconds: float) -> None:
        """Sleep up to ``seconds``; return early once a stop is requested."""
        deadline = time.monotonic() + seconds
        while not self.requested:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(_SLEEP_SLICE_SECONDS, remaining))


def install_stop_handlers(flag: StopFlag | None = None) -> StopFlag:
    """Make SIGTERM and SIGINT set ``flag``. Call only from a stage's ``main()``."""
    flag = flag or StopFlag()
    signal.signal(signal.SIGTERM, flag.request)
    signal.signal(signal.SIGINT, flag.request)
    return flag


def heartbeat_path(stage: str) -> Path | None:
    """``$HEARTBEAT_DIR/<stage>.heartbeat``, or None when heartbeats are off."""
    directory = os.environ.get("HEARTBEAT_DIR", "").strip()
    if not directory:
        return None
    return Path(directory) / f"{stage}.heartbeat"


def beat(stage: str) -> None:
    """Touch the stage's heartbeat file (no-op when ``HEARTBEAT_DIR`` is unset)."""
    path = heartbeat_path(stage)
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


def run_forever(
    stage: str,
    step: Callable[[], object],
    poll_interval: float,
    stop: StopFlag | None = None,
) -> None:
    """Repeat *step -> beat -> sleep* until ``stop`` is requested.

    Any heartbeat left by an earlier process is deleted first: ``/tmp``
    survives a container restart, and an old file would make the new process
    look healthy before it has finished a single iteration.

    Exceptions from ``step`` are not caught: a crash should end the process
    so the container's restart policy can handle it.
    """
    stop = stop or StopFlag()
    stale = heartbeat_path(stage)
    if stale is not None:
        stale.unlink(missing_ok=True)
    while not stop.requested:
        step()
        beat(stage)
        stop.sleep(poll_interval)
    print(f"{stage} stopped")
