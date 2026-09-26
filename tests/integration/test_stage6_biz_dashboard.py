"""Integration tests for Stage 6 — reads features/predictions handoff."""

from __future__ import annotations

import shutil

import pandas as pd
import pytest

from pipeline.dashboard.biz_metrics import at_risk_order_value, late_rate
from pipeline.paths import features_dir, predictions_dir
from tests.conftest import FIXTURES


@pytest.mark.integration
def test_biz_helpers_read_features_and_predictions(tmp_path):
    fdir = features_dir(tmp_path)
    pdir = predictions_dir(tmp_path)
    fdir.mkdir(parents=True)
    pdir.mkdir(parents=True)
    shutil.copy(FIXTURES / "features_biz.csv", fdir / "features_a.csv")
    shutil.copy(FIXTURES / "predictions_sample.csv", pdir / "predictions_a.csv")

    features = pd.concat([pd.read_csv(p) for p in sorted(fdir.glob("features_*.csv"))])
    preds = pd.concat([pd.read_csv(p) for p in sorted(pdir.glob("predictions_*.csv"))])
    assert late_rate(features) == pytest.approx(2 / 3)
    assert at_risk_order_value(features, preds) == pytest.approx(70.0)
