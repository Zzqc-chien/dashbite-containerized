"""Integration tests for Stage 3 — features → checkpoint; no infer import."""

from __future__ import annotations

import shutil

import pytest

from pipeline.config import Config
from pipeline.paths import features_dir, models_dir
from pipeline.train import maybe_train
from tests.conftest import FIXTURES


@pytest.mark.integration
def test_features_to_checkpoint(tmp_path):
    fdir = features_dir(tmp_path)
    fdir.mkdir(parents=True)
    shutil.copy(FIXTURES / "features_train.csv", fdir / "features_batch.csv")

    cfg = Config(train_every_n_events=5, random_seed=42)
    ckpt = maybe_train(cfg=cfg, base=tmp_path)
    assert ckpt is not None
    assert ckpt.exists()
    assert ckpt.parent == models_dir(tmp_path)

    # Below threshold on second call
    assert maybe_train(cfg=cfg, base=tmp_path) is None


@pytest.mark.integration
def test_train_does_not_import_infer():
    import pipeline.train as train_mod

    source = open(train_mod.__file__).read()
    assert "pipeline.infer" not in source
    assert "import infer" not in source
