"""Shared fixture paths for tests."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# Variables the Docker image sets. Tests must not depend on the machine they
# run on, so every test starts with these cleared and sets what it needs.
_CONTAINER_ENV = ("DATA_ROOT", "HEARTBEAT_DIR", "HEARTBEAT_MAX_AGE_SECONDS")


@pytest.fixture(autouse=True)
def _isolate_container_env(monkeypatch):
    for name in _CONTAINER_ENV:
        monkeypatch.delenv(name, raising=False)
