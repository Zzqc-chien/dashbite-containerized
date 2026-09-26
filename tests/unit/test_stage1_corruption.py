"""Unit tests for simulator corruption."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from pipeline.simulator import corrupt_batch, generate_batch


@pytest.mark.unit
def test_corrupt_batch_injects_nans_and_bad_types():
    df = generate_batch(
        20, seed=1, start_time=datetime(2024, 1, 1, tzinfo=timezone.utc)
    )
    dirty = corrupt_batch(df, seed=2, row_frac=0.5)
    # At least one NaN in a numeric column (may be object dtype after mixed types)
    has_nan = dirty["distance_km"].isna().any() or dirty["prep_minutes"].isna().any()
    has_bad_type = dirty["distance_km"].astype(str).str.contains("not_a_number").any()
    assert has_nan or has_bad_type
    assert len(dirty) == len(df)
