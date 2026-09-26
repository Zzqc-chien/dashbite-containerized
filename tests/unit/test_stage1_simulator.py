"""Unit tests for Stage 1 — simulator."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from pipeline.simulator import RAW_COLUMNS, generate_batch


@pytest.mark.unit
def test_batch_has_required_columns_and_valid_ranges():
    df = generate_batch(10, seed=7, start_time=datetime(2024, 1, 1, tzinfo=timezone.utc))
    assert list(df.columns) == RAW_COLUMNS
    assert len(df) == 10
    assert (df["distance_km"] > 0).all()
    assert (df["prep_minutes"] > 0).all()
    assert (df["order_value"] > 0).all()
    assert set(df["was_late"].unique()).issubset({0, 1})
