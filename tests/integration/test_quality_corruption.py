"""Integration: dirty raw batch → features + quality log."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from pipeline.paths import features_dir, quality_dir, raw_dir
from pipeline.preprocess import QUALITY_LOG, process_new_raw_files
from pipeline.simulator import corrupt_batch, generate_batch, write_batch


@pytest.mark.integration
def test_corrupted_batch_writes_quality_log(tmp_path):
    df = generate_batch(
        12, seed=9, start_time=datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc)
    )
    dirty = corrupt_batch(df, seed=9, row_frac=0.5)
    write_batch(dirty, raw_dir(tmp_path), tick=0)

    written = process_new_raw_files(base=tmp_path)
    assert len(written) == 1
    assert written[0].exists()
    assert written[0].parent == features_dir(tmp_path)

    qpath = quality_dir(tmp_path) / QUALITY_LOG
    assert qpath.exists()
    text = qpath.read_text()
    assert "rows_in" in text
    assert "fail_distance_km" in text
