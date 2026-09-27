"""Integration tests — handoff files are published atomically, with no leftovers."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pipeline import infer, preprocess, simulator, train
from pipeline.config import Config
from pipeline.paths import data_root, features_dir, models_dir, predictions_dir, raw_dir


def _run_full_cycle(base: Path):
    cfg = Config(train_every_n_events=5, batch_size=20, corrupt_batch_rate=0.0)
    for tick in range(3):
        simulator.run_once(cfg=cfg, base=base, tick=tick)
    preprocess.process_new_raw_files(base=base)
    ckpt = train.maybe_train(cfg=cfg, base=base)
    preds = infer.run_once(cfg=cfg, base=base)
    return ckpt, preds


@pytest.mark.integration
def test_full_cycle_leaves_no_temp_files(tmp_path):
    ckpt, preds = _run_full_cycle(tmp_path)

    assert len(list(raw_dir(tmp_path).glob("orders_*.csv"))) == 3
    assert len(list(features_dir(tmp_path).glob("features_*.csv"))) == 3
    assert ckpt is not None and ckpt.exists()
    assert (models_dir(tmp_path) / f"metrics_{ckpt.stem.removeprefix('checkpoint_')}.json").exists()
    assert (models_dir(tmp_path) / "train_state.json").exists()
    assert preds is not None and preds.parent == predictions_dir(tmp_path)

    assert list(data_root(tmp_path).rglob(".*.tmp")) == []


@pytest.mark.integration
def test_handoff_files_are_published_by_rename(monkeypatch, tmp_path):
    """Every file a later stage reads appears through one os.replace from a
    hidden temp file in the same folder, never by writing the final name.

    Fails if any call site goes back to writing its output directly, even
    though that would still leave no temp files behind.
    """
    renames: dict[Path, Path] = {}
    real_replace = os.replace

    def spy(src, dst, *args, **kwargs):
        renames[Path(dst)] = Path(src)
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "replace", spy)
    ckpt, preds = _run_full_cycle(tmp_path)
    assert ckpt is not None and preds is not None

    mdir = models_dir(tmp_path)
    handoff = [
        *raw_dir(tmp_path).glob("orders_*.csv"),
        *features_dir(tmp_path).glob("features_*.csv"),
        ckpt,
        mdir / f"metrics_{ckpt.stem.removeprefix('checkpoint_')}.json",
        mdir / "train_state.json",
        preds,
    ]
    assert len(handoff) == 3 + 3 + 4

    for final in handoff:
        assert final in renames, f"{final.name} was not published with os.replace"
        src = renames[final]
        assert src.parent == final.parent, f"{final.name}: temp file in another folder"
        assert src.name == f".{final.name}.tmp", f"{final.name}: unexpected temp name {src.name}"
