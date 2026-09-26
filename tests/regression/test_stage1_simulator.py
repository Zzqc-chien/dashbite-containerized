"""Regression tests for Stage 1 — seeded generator golden CSV."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from pipeline.simulator import generate_batch
from tests.conftest import FIXTURES


@pytest.mark.regression
def test_seeded_generator_matches_golden_csv():
    df = generate_batch(
        5,
        seed=123,
        start_time=datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc),
    )
    df = df.copy()
    df["order_id"] = [f"ord-{i}" for i in range(5)]
    golden = pd.read_csv(FIXTURES / "raw_seed123.csv")
    pd.testing.assert_frame_equal(
        df.reset_index(drop=True),
        golden.reset_index(drop=True),
        check_dtype=False,
    )
