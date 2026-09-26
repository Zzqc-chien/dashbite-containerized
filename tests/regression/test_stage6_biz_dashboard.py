"""Regression tests for Stage 6 — expected business KPIs from fixtures."""

from __future__ import annotations

import pandas as pd
import pytest

from pipeline.dashboard.biz_metrics import at_risk_order_value, late_rate
from tests.conftest import FIXTURES


@pytest.mark.regression
def test_biz_kpis_from_fixtures():
    features = pd.read_csv(FIXTURES / "features_biz.csv")
    preds = pd.read_csv(FIXTURES / "predictions_sample.csv")
    assert late_rate(features) == pytest.approx(2 / 3)
    # ord-a (40) + ord-c (30) predicted late
    assert at_risk_order_value(features, preds) == pytest.approx(70.0)
