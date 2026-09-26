"""Health probe for every DashBite service (stdlib only, no pandas import).

Usage::

    python -m pipeline.healthcheck {simulator|preprocess|train|infer|dashboard}

Exit codes: 0 = healthy, 1 = unhealthy, 2 = usage error. Prints one line,
which Docker records in ``docker inspect ... .State.Health.Log``.

- Workers are healthy when ``$HEARTBEAT_DIR/<stage>.heartbeat`` exists and is
  younger than ``HEARTBEAT_MAX_AGE_SECONDS`` (default
  ``max(30, 3 * POLL_INTERVAL_SECONDS)``). This is liveness, not progress.
- The dashboard is healthy when Streamlit's ``/_stcore/health`` returns 200
  (URL overridable with ``DASHBOARD_HEALTH_URL``).
"""

from __future__ import annotations

import os
import sys
import time
import urllib.error
import urllib.request

from pipeline.config import load_config
from pipeline.lifecycle import heartbeat_path

WORKERS = ("simulator", "preprocess", "train", "infer")
STAGES = WORKERS + ("dashboard",)

HEALTHY, UNHEALTHY, USAGE = 0, 1, 2

DEFAULT_DASHBOARD_URL = "http://127.0.0.1:8501/_stcore/health"
MIN_HEARTBEAT_AGE_SECONDS = 30.0


def heartbeat_max_age() -> float:
    """Staleness limit: the override, or ``max(30, 3 x poll interval)``."""
    override = os.environ.get("HEARTBEAT_MAX_AGE_SECONDS", "").strip()
    if override:
        return float(override)
    poll = load_config().poll_interval_seconds
    return max(MIN_HEARTBEAT_AGE_SECONDS, 3 * poll)


def check_worker(stage: str) -> tuple[int, str]:
    path = heartbeat_path(stage)
    if path is None:
        return UNHEALTHY, f"{stage}: HEARTBEAT_DIR is not set, no heartbeat to check"
    limit = heartbeat_max_age()
    try:
        age = time.time() - path.stat().st_mtime
    except FileNotFoundError:
        return UNHEALTHY, f"{stage}: no heartbeat yet at {path} (limit {limit:g}s)"
    if age > limit:
        return UNHEALTHY, f"{stage} heartbeat {age:.1f}s old (limit {limit:g}s)"
    return HEALTHY, f"{stage} heartbeat {age:.1f}s old (limit {limit:g}s)"


def check_dashboard() -> tuple[int, str]:
    url = os.environ.get("DASHBOARD_HEALTH_URL", "").strip() or DEFAULT_DASHBOARD_URL
    # An empty ProxyHandler ignores *_proxy variables, so a proxy injected into
    # the container cannot intercept a localhost probe.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=4) as resp:
            status = resp.status
    except urllib.error.HTTPError as exc:
        return UNHEALTHY, f"dashboard: {url} returned HTTP {exc.code}"
    except (urllib.error.URLError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        return UNHEALTHY, f"dashboard: {url} unreachable ({reason})"
    if status != 200:
        return UNHEALTHY, f"dashboard: {url} returned HTTP {status}"
    return HEALTHY, f"dashboard: {url} returned HTTP 200"


def check(stage: str) -> tuple[int, str]:
    if stage == "dashboard":
        return check_dashboard()
    return check_worker(stage)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or args[0] not in STAGES:
        print(
            f"usage: python -m pipeline.healthcheck {{{'|'.join(STAGES)}}}",
            file=sys.stderr,
        )
        return USAGE
    code, message = check(args[0])
    print(message)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
