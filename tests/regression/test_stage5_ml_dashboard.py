"""Regression tests for Stage 5 — expected ML KPI numbers from fixtures."""

from __future__ import annotations

import pandas as pd
import pytest

from pipeline.dashboard.ml_metrics import sample_volume, score_summary
from tests.conftest import FIXTURES


@pytest.mark.regression
def test_ml_kpis_from_fixtures():
    features = pd.read_csv(FIXTURES / "features_golden.csv")
    preds = pd.read_csv(FIXTURES / "predictions_sample.csv")
    assert sample_volume(features) == 5
    summary = score_summary(preds)
    assert summary["count"] == 3
    assert summary["mean_probability"] == pytest.approx(0.5333333333)
    assert summary["min_probability"] == pytest.approx(0.2)
    assert summary["max_probability"] == pytest.approx(0.8)
    assert summary["predicted_late_rate"] == pytest.approx(2 / 3)
