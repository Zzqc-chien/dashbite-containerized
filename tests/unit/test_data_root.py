"""Unit tests for the DATA_ROOT override in pipeline.paths."""

from __future__ import annotations

import pytest

from pipeline.paths import PROJECT_ROOT, data_root, raw_dir


@pytest.mark.unit
def test_default_is_project_data():
    assert data_root() == PROJECT_ROOT / "data"


@pytest.mark.unit
def test_env_is_used_as_is(monkeypatch, tmp_path):
    target = tmp_path / "shared"
    monkeypatch.setenv("DATA_ROOT", str(target))
    assert data_root() == target
    assert raw_dir() == target / "raw"


@pytest.mark.unit
def test_explicit_base_wins_over_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "from_env"))
    assert data_root(tmp_path) == tmp_path / "data"


@pytest.mark.unit
def test_blank_env_is_ignored(monkeypatch):
    monkeypatch.setenv("DATA_ROOT", "   ")
    assert data_root() == PROJECT_ROOT / "data"
