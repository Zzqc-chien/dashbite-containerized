"""Regression tests for Stage 4 — scoring with a fixed checkpoint."""

from __future__ import annotations

import pandas as pd
import pytest

from pipeline.infer import score_frame
from pipeline.train import train_model


@pytest.mark.regression
def test_score_frame_ids_and_probability_bounds():
    train_df = pd.DataFrame(
        {
            "distance_km": [1.0, 8.0, 2.0, 9.0, 1.5, 8.5],
            "prep_minutes": [10.0, 40.0, 12.0, 42.0, 11.0, 39.0],
            "was_late": [0, 1, 0, 1, 0, 1],
        }
    )
    model, _ = train_model(train_df, seed=42)
    bundle = {
        "model": model,
        "feature_columns": ["distance_km", "prep_minutes"],
        "checkpoint_id": "testckpt",
    }
    rows = pd.DataFrame(
        {
            "order_id": ["x", "y"],
            "distance_km": [1.0, 9.0],
            "prep_minutes": [10.0, 40.0],
        }
    )
    preds = score_frame(rows, bundle)
    assert list(preds["order_id"]) == ["x", "y"]
    assert list(preds["checkpoint_id"]) == ["testckpt", "testckpt"]
    assert (preds["late_probability"] >= 0).all()
    assert (preds["late_probability"] <= 1).all()
    assert set(preds["predicted_late"]).issubset({0, 1})
    # Separable signal: short trip less late than long
    assert preds.loc[0, "late_probability"] < preds.loc[1, "late_probability"]
