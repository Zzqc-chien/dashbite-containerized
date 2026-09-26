"""Integration test — a worker that is alive but stuck is reported unhealthy.

Preprocess is hung for real: a FIFO named like a raw batch has no writer, so
``read_csv`` blocks in ``open()`` forever. No test hooks in production code.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest

from pipeline.paths import PROJECT_ROOT


def _probe(env):
    return subprocess.run(
        [sys.executable, "-m", "pipeline.healthcheck", "preprocess"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )


@pytest.mark.integration
@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs os.mkfifo")
def test_stuck_preprocess_turns_unhealthy(tmp_path):
    data = tmp_path / "data"
    hb = tmp_path / "hb"
    env = {
        **os.environ,
        "DATA_ROOT": str(data),
        "HEARTBEAT_DIR": str(hb),
        "POLL_INTERVAL_SECONDS": "0.1",
        "HEARTBEAT_MAX_AGE_SECONDS": "1",
        "PYTHONUNBUFFERED": "1",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "pipeline.preprocess"],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    output = ""
    try:
        heartbeat = hb / "preprocess.heartbeat"
        deadline = time.monotonic() + 20
        while not heartbeat.exists() and time.monotonic() < deadline:
            assert proc.poll() is None, "preprocess exited before its first heartbeat"
            time.sleep(0.1)
        assert heartbeat.exists(), "no heartbeat within 20 s"

        healthy = _probe(env)
        assert healthy.returncode == 0, healthy.stdout + healthy.stderr

        os.mkfifo(data / "raw" / "orders_stuck.csv")
        time.sleep(2.5)

        assert proc.poll() is None, "preprocess should still be running (blocked)"
        stuck = _probe(env)
        assert stuck.returncode == 1, stuck.stdout + stuck.stderr
        assert "preprocess heartbeat" in stuck.stdout
    finally:
        # SIGTERM cannot interrupt the blocked open(), so kill outright.
        proc.kill()
        output, _ = proc.communicate()
    assert "DashBite preprocess started" in output
