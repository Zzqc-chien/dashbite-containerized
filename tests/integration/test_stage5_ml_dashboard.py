"""Integration tests for Stage 5 — helpers read real-shaped data dirs."""

from __future__ import annotations

import shutil

import pandas as pd
import pytest

from pipeline.dashboard.ml_metrics import sample_volume, score_summary
from pipeline.paths import features_dir, predictions_dir
from tests.conftest import FIXTURES


@pytest.mark.integration
def test_ml_helpers_read_data_tree(tmp_path):
    fdir = features_dir(tmp_path)
    pdir = predictions_dir(tmp_path)
    fdir.mkdir(parents=True)
    pdir.mkdir(parents=True)
    shutil.copy(FIXTURES / "features_golden.csv", fdir / "features_a.csv")
    shutil.copy(FIXTURES / "predictions_sample.csv", pdir / "predictions_a.csv")

    features = pd.concat([pd.read_csv(p) for p in fdir.glob("features_*.csv")])
    preds = pd.concat([pd.read_csv(p) for p in pdir.glob("predictions_*.csv")])
    assert sample_volume(features) == 5
    assert score_summary(preds)["count"] == 3
