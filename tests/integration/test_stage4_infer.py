"""Integration tests for Stage 4 — features + checkpoint → predictions."""

from __future__ import annotations

import shutil

import pytest

from pipeline.config import Config
from pipeline.infer import run_once
from pipeline.paths import features_dir, predictions_dir
from pipeline.train import maybe_train
from tests.conftest import FIXTURES


@pytest.mark.integration
def test_features_and_checkpoint_to_predictions(tmp_path):
    fdir = features_dir(tmp_path)
    fdir.mkdir(parents=True)
    shutil.copy(FIXTURES / "features_train.csv", fdir / "features_batch.csv")

    cfg = Config(train_every_n_events=5, random_seed=42)
    ckpt = maybe_train(cfg=cfg, base=tmp_path)
    assert ckpt is not None

    out = run_once(cfg=cfg, base=tmp_path)
    assert out is not None
    assert out.exists()
    assert out.parent == predictions_dir(tmp_path)

    # Already scored → None
    assert run_once(cfg=cfg, base=tmp_path) is None


@pytest.mark.integration
def test_infer_does_not_import_train():
    import pipeline.infer as infer_mod

    source = open(infer_mod.__file__).read()
    assert "pipeline.train" not in source
    assert "import train" not in source


@pytest.mark.integration
def test_infer_skips_when_no_checkpoint(tmp_path):
    fdir = features_dir(tmp_path)
    fdir.mkdir(parents=True)
    shutil.copy(FIXTURES / "features_train.csv", fdir / "features_batch.csv")
    assert run_once(base=tmp_path) is None
