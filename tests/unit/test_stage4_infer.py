"""Unit tests for Stage 4 — newest checkpoint selection."""

from __future__ import annotations

import pytest

from pipeline.infer import newest_checkpoint
from pipeline.paths import models_dir


@pytest.mark.unit
def test_newest_checkpoint_selection(tmp_path):
    mdir = models_dir(tmp_path)
    mdir.mkdir(parents=True)
    older = mdir / "checkpoint_20240101_000000.joblib"
    newer = mdir / "checkpoint_20240102_120000.joblib"
    older.write_bytes(b"old")
    newer.write_bytes(b"new")
    assert newest_checkpoint(tmp_path) == newer


@pytest.mark.unit
def test_newest_checkpoint_none_when_empty(tmp_path):
    models_dir(tmp_path).mkdir(parents=True)
    assert newest_checkpoint(tmp_path) is None
