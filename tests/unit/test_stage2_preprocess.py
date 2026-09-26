"""Unit tests for Stage 2 — preprocess (including dirty types)."""

from __future__ import annotations

import pandas as pd
import pytest

from pipeline.preprocess import (
    add_features,
    coerce_types,
    drop_invalid,
    preprocess_frame,
    preprocess_with_quality,
)


@pytest.mark.unit
def test_drop_invalid_and_add_features():
    df = pd.DataFrame(
        {
            "order_id": ["a", "b", "c"],
            "timestamp": [
                "2024-06-15T12:00:00+00:00",
                "2024-06-15T10:00:00+00:00",
                "bad",
            ],
            "distance_km": [1.0, -1.0, 2.0],
            "prep_minutes": [10.0, 10.0, 10.0],
            "order_value": [20.0, 20.0, 20.0],
            "was_late": [0, 1, 0],
        }
    )
    cleaned = drop_invalid(df)
    # b: invalid distance; c: bad timestamp → only a survives
    assert list(cleaned["order_id"]) == ["a"]
    featured = add_features(cleaned)
    assert featured.loc[0, "hour"] == 12
    assert featured.loc[0, "is_peak"] == 1

    full = preprocess_frame(df)
    assert "hour" in full.columns
    assert "is_peak" in full.columns


@pytest.mark.unit
def test_field_failures_on_nan_and_bad_types():
    df = pd.DataFrame(
        {
            "order_id": ["a", "b", "c"],
            "timestamp": [
                "2024-06-15T12:00:00+00:00",
                "NOT_A_TIMESTAMP",
                "2024-06-15T13:00:00+00:00",
            ],
            "distance_km": [1.0, "not_a_number", None],
            "prep_minutes": [10.0, "ten", 12.0],
            "order_value": [20.0, 20.0, 20.0],
            "was_late": [0, "maybe", 1],
        }
    )
    _, failures = coerce_types(df)
    assert failures["distance_km"] >= 2  # bad type + null
    assert failures["timestamp"] >= 1
    assert failures["was_late"] >= 1
    assert failures["prep_minutes"] >= 1

    features, quality = preprocess_with_quality(df)
    assert quality["rows_in"] == 3
    assert quality["rows_out"] == len(features)
    assert quality["rows_out"] < quality["rows_in"]
    assert quality["fail_distance_km"] >= 1
