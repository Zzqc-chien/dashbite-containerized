"""Unit tests for Stage 0 — config and paths."""

from __future__ import annotations

import os

import pytest

from pipeline.config import DEFAULT_CONFIG, Config, load_config
from pipeline.paths import DATA_SUBDIRS, ensure_data_dirs, raw_dir


@pytest.mark.unit
def test_default_config_train_every_n_events():
    assert DEFAULT_CONFIG.train_every_n_events == 2000
    assert DEFAULT_CONFIG.batch_size == 50


@pytest.mark.unit
def test_load_config_from_env(monkeypatch):
    monkeypatch.setenv("TRAIN_EVERY_N_EVENTS", "10")
    monkeypatch.setenv("BATCH_SIZE", "5")
    cfg = load_config()
    assert cfg.train_every_n_events == 10
    assert cfg.batch_size == 5


@pytest.mark.unit
def test_required_data_dir_helpers(tmp_path):
    ensure_data_dirs(tmp_path)
    assert raw_dir(tmp_path).exists()
    assert raw_dir(tmp_path).name == "raw"
