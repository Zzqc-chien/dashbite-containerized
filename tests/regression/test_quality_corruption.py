"""Regression: corrupted batch quality record shape."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from pipeline.preprocess import preprocess_with_quality
from pipeline.simulator import corrupt_batch, generate_batch


@pytest.mark.regression
def test_corrupted_batch_quality_keys():
    df = generate_batch(
        10, seed=5, start_time=datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc)
    )
    df = corrupt_batch(df, seed=5, row_frac=0.4)
    _, quality = preprocess_with_quality(df)
    for key in (
        "rows_in",
        "rows_out",
        "rows_dropped",
        "drop_rate",
        "fail_distance_km",
        "fail_timestamp",
        "fail_was_late",
    ):
        assert key in quality
    assert quality["rows_in"] == 10
    assert quality["rows_out"] <= quality["rows_in"]
