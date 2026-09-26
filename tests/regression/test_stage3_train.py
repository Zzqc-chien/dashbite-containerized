"""Regression tests for Stage 3 — metrics shape from fixed features."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from pipeline.train import train_model
from tests.conftest import FIXTURES


@pytest.mark.regression
def test_train_metrics_shape_from_fixture():
    df = pd.read_csv(FIXTURES / "features_train.csv")
    _, metrics = train_model(df, seed=42)
    assert set(metrics.keys()) == {"accuracy", "n_train", "n_test"}
    assert 0.0 <= metrics["accuracy"] <= 1.0
    assert metrics["n_train"] > 0
    # Held-out test when enough rows; otherwise n_test may be 0
    assert metrics["n_test"] >= 0
    assert metrics["accuracy"] >= 0.5
    json.dumps(metrics)
