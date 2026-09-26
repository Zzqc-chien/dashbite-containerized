"""Stage 5 — ML monitoring helpers (sample volume + score summary)."""

from __future__ import annotations

import pandas as pd


def sample_volume(features: pd.DataFrame) -> int:
    """Count of feature samples available."""
    if features is None or features.empty:
        return 0
    return int(len(features))


def score_summary(predictions: pd.DataFrame) -> dict:
    """Simple summary of late_probability distribution."""
    if predictions is None or predictions.empty or "late_probability" not in predictions.columns:
        return {
            "count": 0,
            "mean_probability": 0.0,
            "min_probability": 0.0,
            "max_probability": 0.0,
            "predicted_late_rate": 0.0,
        }
    probs = predictions["late_probability"].astype(float)
    pred_late = (
        predictions["predicted_late"].astype(int).mean()
        if "predicted_late" in predictions.columns
        else 0.0
    )
    return {
        "count": int(len(predictions)),
        "mean_probability": float(probs.mean()),
        "min_probability": float(probs.min()),
        "max_probability": float(probs.max()),
        "predicted_late_rate": float(pred_late),
    }
