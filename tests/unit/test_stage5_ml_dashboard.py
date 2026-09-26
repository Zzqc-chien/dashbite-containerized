"""Unit tests for Stage 5 — ML dashboard helpers."""

from __future__ import annotations

import pandas as pd
import pytest

from pipeline.dashboard.ml_metrics import sample_volume, score_summary


@pytest.mark.unit
def test_sample_volume_and_score_summary():
    features = pd.DataFrame({"order_id": ["a", "b", "c"]})
    assert sample_volume(features) == 3
    assert sample_volume(pd.DataFrame()) == 0

    preds = pd.DataFrame(
        {
            "late_probability": [0.1, 0.9, 0.5],
            "predicted_late": [0, 1, 1],
        }
    )
    summary = score_summary(preds)
    assert summary["count"] == 3
    assert summary["mean_probability"] == pytest.approx(0.5)
    assert summary["min_probability"] == pytest.approx(0.1)
    assert summary["max_probability"] == pytest.approx(0.9)
    assert summary["predicted_late_rate"] == pytest.approx(2 / 3)
