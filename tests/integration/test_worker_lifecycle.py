"""Integration tests — each worker's loop stops cleanly and writes a heartbeat."""

from __future__ import annotations

import importlib
import os
import signal
import subprocess
import sys
import time

import pytest

from pipeline.lifecycle import StopFlag
from pipeline.paths import PROJECT_ROOT


class StopAfterFirstIteration(StopFlag):
    """A stop flag that asks to stop as soon as the loop first sleeps."""

    def sleep(self, seconds: float) -> None:
        self.request()


@pytest.mark.integration
@pytest.mark.parametrize("stage", ["simulator", "preprocess", "train", "infer"])
def test_run_loop_stops_and_beats(stage, monkeypatch, tmp_path):
    data = tmp_path / "data"
    hb = tmp_path / "hb"
    monkeypatch.setenv("DATA_ROOT", str(data))
    monkeypatch.setenv("HEARTBEAT_DIR", str(hb))
    monkeypatch.setenv("BATCH_SIZE", "5")

    module = importlib.import_module(f"pipeline.{stage}")
    module.run_loop(stop=StopAfterFirstIteration())

    assert (hb / f"{stage}.heartbeat").is_file()
    assert (data / "raw").is_dir()


@pytest.mark.integration
@pytest.mark.parametrize("stage", ["simulator", "preprocess", "train", "infer"])
def test_worker_exits_cleanly_on_sigterm(stage, tmp_path):
    """A real SIGTERM to ``python -m pipeline.<stage>`` ends in exit 0.

    Fails if a stage's ``main()`` stops installing the handlers: Python's
    default SIGTERM action would end the process with -15 and no log line.
    """
    data = tmp_path / "data"
    hb = tmp_path / "hb"
    env = {
        **os.environ,
        "DATA_ROOT": str(data),
        "HEARTBEAT_DIR": str(hb),
        "POLL_INTERVAL_SECONDS": "0.2",
        "BATCH_SIZE": "5",
        "PYTHONUNBUFFERED": "1",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", f"pipeline.{stage}"],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    output = ""
    try:
        heartbeat = hb / f"{stage}.heartbeat"
        deadline = time.monotonic() + 20
        while not heartbeat.exists() and time.monotonic() < deadline:
            assert proc.poll() is None, f"{stage} exited before its first heartbeat"
            time.sleep(0.1)
        assert heartbeat.exists(), "no heartbeat within 20 s"

        proc.send_signal(signal.SIGTERM)
        output, _ = proc.communicate(timeout=5)
    finally:
        if proc.poll() is None:
            proc.kill()
            extra, _ = proc.communicate()
            output += extra or ""

    assert proc.returncode == 0, output
    assert f"{stage} stopped" in output, output
    if stage == "simulator":
        assert list((data / "raw").glob("orders_*.csv")), output
