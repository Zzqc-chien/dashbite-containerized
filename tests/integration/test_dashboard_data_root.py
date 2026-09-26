"""Integration tests — the dashboard follows DATA_ROOT instead of the source tree."""

from __future__ import annotations

import inspect
import shutil

import pytest

from pipeline.dashboard import app
from tests.conftest import FIXTURES


@pytest.mark.integration
def test_dashboard_loaders_follow_data_root(monkeypatch, tmp_path):
    root = tmp_path / "shared"
    (root / "features").mkdir(parents=True)
    (root / "predictions").mkdir(parents=True)
    shutil.copy(FIXTURES / "features_golden.csv", root / "features" / "features_a.csv")
    shutil.copy(FIXTURES / "predictions_sample.csv", root / "predictions" / "predictions_a.csv")
    monkeypatch.setenv("DATA_ROOT", str(root))

    assert len(app.load_features()) == 5
    assert len(app.load_predictions()) == 3
    assert len(app.load_quality_log()) == 0


@pytest.mark.integration
def test_dashboard_does_not_pin_project_root():
    source = inspect.getsource(app)
    assert "PROJECT_ROOT" not in source
