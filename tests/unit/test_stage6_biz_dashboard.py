"""Unit tests for Stage 6 — business KPI helpers."""

from __future__ import annotations

import pandas as pd
import pytest

from pipeline.dashboard.biz_metrics import at_risk_order_value, late_rate


@pytest.mark.unit
def test_late_rate_and_at_risk_value():
    features = pd.DataFrame(
        {
            "order_id": ["a", "b", "c"],
            "order_value": [40.0, 20.0, 30.0],
            "was_late": [1, 0, 1],
        }
    )
    preds = pd.DataFrame(
        {
            "order_id": ["a", "b", "c"],
            "predicted_late": [1, 0, 1],
        }
    )
    assert late_rate(features) == pytest.approx(2 / 3)
    assert at_risk_order_value(features, preds) == pytest.approx(70.0)
