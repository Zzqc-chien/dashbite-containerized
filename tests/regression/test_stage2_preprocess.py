"""Regression tests for Stage 2 — golden features CSV."""

from __future__ import annotations

import pandas as pd
import pytest

from pipeline.preprocess import preprocess_frame
from tests.conftest import FIXTURES


@pytest.mark.regression
def test_raw_fixture_to_golden_features():
    raw = pd.read_csv(FIXTURES / "raw_seed123.csv")
    features = preprocess_frame(raw)
    golden = pd.read_csv(FIXTURES / "features_golden.csv")
    pd.testing.assert_frame_equal(
        features.reset_index(drop=True),
        golden.reset_index(drop=True),
        check_dtype=False,
    )
