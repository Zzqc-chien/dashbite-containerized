"""Integration test — a full pipeline cycle leaves no temp files behind."""

from __future__ import annotations

import pytest

from pipeline import infer, preprocess, simulator, train
from pipeline.config import Config
from pipeline.paths import data_root, features_dir, models_dir, predictions_dir, raw_dir


@pytest.mark.integration
def test_full_cycle_leaves_no_temp_files(tmp_path):
    cfg = Config(train_every_n_events=5, batch_size=20, corrupt_batch_rate=0.0)

    for tick in range(3):
        simulator.run_once(cfg=cfg, base=tmp_path, tick=tick)
    preprocess.process_new_raw_files(base=tmp_path)
    ckpt = train.maybe_train(cfg=cfg, base=tmp_path)
    preds = infer.run_once(cfg=cfg, base=tmp_path)

    assert len(list(raw_dir(tmp_path).glob("orders_*.csv"))) == 3
    assert len(list(features_dir(tmp_path).glob("features_*.csv"))) == 3
    assert ckpt is not None and ckpt.exists()
    assert (models_dir(tmp_path) / f"metrics_{ckpt.stem.removeprefix('checkpoint_')}.json").exists()
    assert (models_dir(tmp_path) / "train_state.json").exists()
    assert preds is not None and preds.parent == predictions_dir(tmp_path)

    assert list(data_root(tmp_path).rglob(".*.tmp")) == []
