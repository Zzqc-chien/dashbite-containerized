"""Integration tests for Stage 2 — raw → features handoff."""

from __future__ import annotations

import shutil

import pytest

from pipeline.paths import features_dir, raw_dir
from pipeline.preprocess import process_new_raw_files
from tests.conftest import FIXTURES


@pytest.mark.integration
def test_raw_to_features_handoff(tmp_path):
    rdir = raw_dir(tmp_path)
    rdir.mkdir(parents=True)
    shutil.copy(FIXTURES / "raw_seed123.csv", rdir / "orders_test.csv")

    written = process_new_raw_files(base=tmp_path)
    assert len(written) == 1
    assert written[0].parent == features_dir(tmp_path)
    assert written[0].exists()

    # second run is a no-op (already processed)
    assert process_new_raw_files(base=tmp_path) == []
