"""Integration tests for Stage 1 — raw landing zone."""

from __future__ import annotations

import pytest

from pipeline.config import Config
from pipeline.paths import raw_dir
from pipeline.simulator import run_once


@pytest.mark.integration
def test_run_once_writes_raw_file(tmp_path):
    cfg = Config(batch_size=3, train_every_n_events=2000)
    path = run_once(cfg=cfg, base=tmp_path, tick=0)
    assert path.exists()
    assert path.parent == raw_dir(tmp_path)
    assert path.name.startswith("orders_")
