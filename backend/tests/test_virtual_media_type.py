import importlib.util
from pathlib import Path
import struct

import pytest


spec = importlib.util.spec_from_file_location(
    "media_type", Path(__file__).resolve().parents[2] / "scripts/detect-virtual-media-type.py"
)
media_type = importlib.util.module_from_spec(spec)
spec.loader.exec_module(media_type)
LIMIT = media_type.CDROM_SECTOR_LIMIT * 2048


@pytest.mark.parametrize("size,expected", [(LIMIT - 1, "cdrom"), (LIMIT, "disk"), (6482409472, "disk")])
def test_hybrid_iso_boundary(tmp_path, size, expected):
    path = tmp_path / "ubuntu.iso"
    header = bytearray(1024)
    header[510:512] = b"\x55\xaa"
    header[450] = 0xEE
    struct.pack_into("<II", header, 454, 1, size // 512 - 1)
    header[512:520] = b"EFI PART"
    with path.open("wb") as output:
        output.write(header)
        output.truncate(size)
    assert media_type.detect(path) == expected


def test_large_nonhybrid_iso_rejected(tmp_path):
    path = tmp_path / "optical.iso"
    with path.open("wb") as output:
        output.truncate(LIMIT)
    with pytest.raises(ValueError, match="size limit"):
        media_type.detect(path)


def test_img_is_disk(tmp_path):
    assert media_type.detect(tmp_path / "boot.IMG") == "disk"
