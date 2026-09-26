"""Container checks — compose.yaml and Dockerfile carry the agreed settings.

Compose is parsed with Docker's own parser (``docker compose config``), so no
YAML dependency is needed. These skip inside the image, where neither file nor
the Docker CLI exists.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from pipeline.paths import PROJECT_ROOT

COMPOSE_FILE = PROJECT_ROOT / "compose.yaml"
DOCKERFILE = PROJECT_ROOT / "Dockerfile"
PIPELINE_SERVICES = ("simulator", "preprocess", "train", "infer", "dashboard")

pytestmark = pytest.mark.container


def _compose_available() -> bool:
    if shutil.which("docker") is None:
        return False
    probe = subprocess.run(
        ["docker", "compose", "version"], capture_output=True, text=True
    )
    return probe.returncode == 0


@pytest.fixture(scope="module")
def compose_config() -> dict:
    if not COMPOSE_FILE.exists():
        pytest.skip("no compose.yaml (running inside the image?)")
    if not _compose_available():
        pytest.skip("Docker CLI with the Compose plugin is not installed")
    result = subprocess.run(
        ["docker", "compose", "--profile", "test", "config", "--format", "json"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _data_mount(service: dict) -> dict:
    mounts = [v for v in service.get("volumes", []) if v.get("target") == "/data"]
    assert len(mounts) == 1, service.get("volumes")
    return mounts[0]


def test_pipeline_services_share_volume_env_and_health(compose_config):
    services = compose_config["services"]
    for name in PIPELINE_SERVICES:
        service = services[name]
        assert service["image"] == "dashbite:local", name
        assert service["environment"]["DATA_ROOT"] == "/data", name
        mount = _data_mount(service)
        assert mount["type"] == "volume" and mount["source"] == "dashbite-data", name
        assert name in service["healthcheck"]["test"], name
    assert "dashbite-data" in compose_config["volumes"]


def test_dashboard_is_read_only_and_local_and_tests_is_isolated(compose_config):
    services = compose_config["services"]

    dashboard = services["dashboard"]
    assert _data_mount(dashboard).get("read_only") is True
    ports = {(p.get("host_ip"), str(p.get("published")), p.get("target")) for p in dashboard["ports"]}
    assert ports == {("127.0.0.1", "8501", 8501)}

    for name in ("simulator", "preprocess", "train", "infer"):
        assert not _data_mount(services[name]).get("read_only"), name

    tests = services["tests"]
    assert tests["profiles"] == ["test"]
    assert not tests.get("volumes")


def test_dockerfile_container_settings():
    if not DOCKERFILE.exists():
        pytest.skip("no Dockerfile (running inside the image?)")
    text = DOCKERFILE.read_text()
    for needle in ("PYTHONUNBUFFERED=1", "DATA_ROOT=/data", "HEARTBEAT_DIR=", "USER app"):
        assert needle in text, needle
