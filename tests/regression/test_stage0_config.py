"""Regression tests for Stage 0 — frozen default config."""

from __future__ import annotations

import pytest

from pipeline.config import DEFAULT_CONFIG


EXPECTED_DEFAULTS = {
    "train_every_n_events": 2000,
    "batch_size": 50,
    "poll_interval_seconds": 2.0,
    "feature_columns": ("distance_km", "prep_minutes"),
    "random_seed": 42,
    "corrupt_batch_rate": 0.25,
}


@pytest.mark.regression
def test_default_config_matches_frozen_dict():
    assert DEFAULT_CONFIG.to_dict() == EXPECTED_DEFAULTS
