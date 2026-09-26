"""Data directory helpers shared by every stage."""

from __future__ import annotations

from pathlib import Path

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
]


DATA_SUBDIRS = ("raw", "features", "models", "predictions", "quality")


def data_root(base: Path | None = None) -> Path:
    """Return the data root (default: <project>/data)."""
    return (base or PROJECT_ROOT) / "data"


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
