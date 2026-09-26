"""In-image check — /data belongs to the running user and is writable.

Docker copies the image's /data (owner included) into a fresh named volume,
so this directory decides whether the workers can write. Runs only inside the
image; skips everywhere else.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pipeline.paths import PROJECT_ROOT

IMAGE_DATA_DIR = Path("/data")


@pytest.mark.container
@pytest.mark.skipif(
    PROJECT_ROOT != Path("/app") or not IMAGE_DATA_DIR.is_dir(),
    reason="only runs inside the dashbite image",
)
def test_image_data_dir_owned_by_current_user_and_writable():
    info = IMAGE_DATA_DIR.stat()
    assert info.st_uid == os.getuid(), (
        f"/data is owned by uid {info.st_uid}, not the running uid {os.getuid()}; "
        "create and chown it in the Dockerfile before USER app"
    )
    probe = IMAGE_DATA_DIR / f".write_probe_{os.getpid()}"
    probe.write_text("ok")
    probe.unlink()
