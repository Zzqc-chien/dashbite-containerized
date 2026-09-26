"""Stage 6 — business KPI helpers (late rate + orders at risk)."""

from __future__ import annotations

import pandas as pd


def late_rate(features: pd.DataFrame) -> float:
    """Fraction of labeled orders that were late."""
    if features is None or features.empty or "was_late" not in features.columns:
        return 0.0
    labeled = features.dropna(subset=["was_late"])
    if labeled.empty:
        return 0.0
    return float(labeled["was_late"].astype(int).mean())


def at_risk_order_value(
    features: pd.DataFrame,
    predictions: pd.DataFrame,
) -> float:
    """Sum of order_value for orders predicted late."""
    if (
        features is None
        or predictions is None
        or features.empty
        or predictions.empty
        or "order_value" not in features.columns
        or "predicted_late" not in predictions.columns
    ):
        return 0.0

    merged = predictions.merge(
        features[["order_id", "order_value"]],
        on="order_id",
        how="inner",
    )
    at_risk = merged[merged["predicted_late"].astype(int) == 1]
    if at_risk.empty:
        return 0.0
    return float(at_risk["order_value"].astype(float).sum())
