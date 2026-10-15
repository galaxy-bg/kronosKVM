"""Exercise frontend framing and display ordering without camera hardware."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is required for frontend tests")
def test_complete_kvm_frames():
    subprocess.run(
        ["node", str(ROOT / "tests/fixtures/kvm-video.cjs")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        timeout=15,
    )
