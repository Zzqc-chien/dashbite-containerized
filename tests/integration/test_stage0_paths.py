"""Integration tests for Stage 0 — data directory creation."""

from __future__ import annotations

import pytest

from pipeline.paths import DATA_SUBDIRS, ensure_data_dirs


@pytest.mark.integration
def test_ensure_data_dirs_in_temp_workspace(tmp_path):
    paths = ensure_data_dirs(tmp_path)
    assert set(paths.keys()) == set(DATA_SUBDIRS)
    for name, path in paths.items():
        assert path.is_dir()
        assert path.name == name
        assert path.parent == tmp_path / "data"
