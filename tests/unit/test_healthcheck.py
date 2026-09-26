"""Unit tests for pipeline.healthcheck."""

from __future__ import annotations

import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from pipeline.healthcheck import heartbeat_max_age, main


def _age(path, seconds):
    old = time.time() - seconds
    os.utime(path, (old, old))


@pytest.mark.unit
def test_worker_heartbeat_missing_fresh_and_stale(monkeypatch, tmp_path):
    monkeypatch.setenv("HEARTBEAT_DIR", str(tmp_path))
    beat = tmp_path / "train.heartbeat"

    assert main(["train"]) == 1  # missing
    beat.touch()
    assert main(["train"]) == 0  # fresh
    _age(beat, 120)
    assert main(["train"]) == 1  # 120 s old, default limit 30 s


@pytest.mark.unit
def test_limit_scales_with_poll_interval(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("HEARTBEAT_DIR", str(tmp_path))
    monkeypatch.setenv("POLL_INTERVAL_SECONDS", "60")
    assert heartbeat_max_age() == 180

    beat = tmp_path / "infer.heartbeat"
    beat.touch()
    _age(beat, 120)
    assert main(["infer"]) == 0
    assert "limit 180s" in capsys.readouterr().out


@pytest.mark.unit
def test_unknown_stage_is_usage_error():
    assert main(["nope"]) == 2
    assert main([]) == 2


class _OkHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (stdlib naming)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *_):
        pass


@pytest.mark.unit
def test_dashboard_probe_against_stub(monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), _OkHandler)
    port = server.server_address[1]
    monkeypatch.setenv("DASHBOARD_HEALTH_URL", f"http://127.0.0.1:{port}/_stcore/health")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert main(["dashboard"]) == 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    assert main(["dashboard"]) == 1
