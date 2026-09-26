"""Unit tests for pipeline.lifecycle."""

from __future__ import annotations

import time

import pytest

from pipeline.lifecycle import StopFlag, heartbeat_path, run_forever


@pytest.mark.unit
def test_requested_stop_cuts_sleep_short():
    flag = StopFlag()
    flag.request()
    started = time.monotonic()
    flag.sleep(5)
    assert time.monotonic() - started < 0.5


@pytest.mark.unit
def test_run_forever_steps_beats_and_stops(monkeypatch, tmp_path):
    monkeypatch.setenv("HEARTBEAT_DIR", str(tmp_path / "hb"))
    flag = StopFlag()
    calls = []

    def step():
        calls.append(1)
        if len(calls) == 3:
            flag.request()

    run_forever("demo", step, poll_interval=0.01, stop=flag)

    assert len(calls) == 3
    assert (tmp_path / "hb" / "demo.heartbeat").is_file()


@pytest.mark.unit
def test_no_heartbeat_when_dir_unset(tmp_path):
    flag = StopFlag()
    run_forever("demo", flag.request, poll_interval=0.01, stop=flag)
    assert heartbeat_path("demo") is None
    assert list(tmp_path.iterdir()) == []
