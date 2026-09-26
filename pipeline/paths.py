"""Data directory helpers shared by every stage."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from pipeline.config import PROJECT_ROOT

__all__ = [
    "PROJECT_ROOT",
    "DATA_SUBDIRS",
    "data_root",
    "raw_dir",
    "features_dir",
    "models_dir",
    "predictions_dir",
    "quality_dir",
    "ensure_data_dirs",
    "atomic_path",
]


DATA_SUBDIRS = ("raw", "features", "models", "predictions", "quality")


def data_root(base: Path | None = None) -> Path:
    """Return the pipeline data directory.

    Resolution order:

    1. ``base`` given -> ``base / "data"``. Note that ``base`` is a *project
       root*, not the data directory itself (tests rely on this).
    2. ``$DATA_ROOT`` set and non-blank -> used as-is. It names the data
       directory itself (the folder that holds ``raw/``, ``features/``, ...).
       Read at call time, so ``monkeypatch.setenv`` works in tests.
    3. Otherwise ``<project>/data``.
    """
    if base is not None:
        return base / "data"
    env = os.environ.get("DATA_ROOT", "").strip()
    if env:
        return Path(env)
    return PROJECT_ROOT / "data"


def raw_dir(base: Path | None = None) -> Path:
    return data_root(base) / "raw"


def features_dir(base: Path | None = None) -> Path:
    return data_root(base) / "features"


def models_dir(base: Path | None = None) -> Path:
    return data_root(base) / "models"


def predictions_dir(base: Path | None = None) -> Path:
    return data_root(base) / "predictions"


def quality_dir(base: Path | None = None) -> Path:
    return data_root(base) / "quality"


def ensure_data_dirs(base: Path | None = None) -> dict[str, Path]:
    """Create the standard data folders and return their paths."""
    root = data_root(base)
    paths = {name: root / name for name in DATA_SUBDIRS}
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


@contextmanager
def atomic_path(final: Path) -> Iterator[Path]:
    """Write to a hidden temp file, then publish it as ``final`` in one rename.

    Yields ``<dir>/.<name>.tmp`` in the same folder as ``final`` (same folder
    is what makes ``os.replace`` atomic; the leading dot keeps it out of every
    reader's glob). On normal exit the temp file replaces ``final``; if the
    block raises, ``final`` is left untouched and the temp file is removed.
    """
    final = Path(final)
    tmp = final.with_name(f".{final.name}.tmp")
    try:
        yield tmp
        os.replace(tmp, final)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
