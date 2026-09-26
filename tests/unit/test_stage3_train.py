"""Unit tests for Stage 3 — train threshold and checkpoint writing."""

from __future__ import annotations

import pandas as pd
import pytest

from pipeline.config import Config
from pipeline.paths import models_dir
from pipeline.train import maybe_train, should_retrain, write_checkpoint, train_model


@pytest.mark.unit
def test_should_retrain_threshold():
    assert should_retrain(labeled_count=20, last_count=0, threshold=10) is True
    assert should_retrain(labeled_count=9, last_count=0, threshold=10) is False
    assert should_retrain(labeled_count=25, last_count=20, threshold=10) is False
    assert should_retrain(labeled_count=30, last_count=20, threshold=10) is True


@pytest.mark.unit
def test_write_checkpoint_creates_file(tmp_path):
    df = pd.DataFrame(
        {
            "distance_km": [1.0, 8.0, 2.0, 9.0],
            "prep_minutes": [10.0, 40.0, 12.0, 42.0],
            "was_late": [0, 1, 0, 1],
        }
    )
    model, metrics = train_model(df, seed=0)
    path = write_checkpoint(model, metrics, base=tmp_path, stamp="20240101_000000")
    assert path.exists()
    assert path.parent == models_dir(tmp_path)
    assert path.name == "checkpoint_20240101_000000.joblib"
    assert (models_dir(tmp_path) / "metrics_20240101_000000.json").exists()
