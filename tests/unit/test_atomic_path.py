"""Unit tests for pipeline.paths.atomic_path."""

from __future__ import annotations

import pytest

from pipeline.paths import atomic_path


@pytest.mark.unit
def test_file_is_invisible_until_published(tmp_path):
    final = tmp_path / "orders_0001.csv"
    with atomic_path(final) as tmp:
        tmp.write_text("a,b\n1,2\n")
        assert tmp.parent == tmp_path
        assert tmp.name.startswith(".")
        assert not final.exists()
        assert list(tmp_path.glob("orders_*.csv")) == []

    assert final.read_text() == "a,b\n1,2\n"
    assert list(tmp_path.iterdir()) == [final]


@pytest.mark.unit
def test_failure_publishes_nothing_and_cleans_up(tmp_path):
    final = tmp_path / "orders_0001.csv"
    with pytest.raises(RuntimeError):
        with atomic_path(final) as tmp:
            tmp.write_text("half a file")
            raise RuntimeError("writer crashed")

    assert not final.exists()
    assert list(tmp_path.iterdir()) == []
