"""Choose a gadget mode without silently truncating oversized ISO images."""

from pathlib import Path
import struct
import sys


CDROM_SECTOR_LIMIT = 256 * 60 * 75


def detect(path: Path) -> str:
    if path.suffix.lower() == ".img":
        return "disk"
    if path.suffix.lower() != ".iso":
        raise ValueError("Only ISO and IMG files are supported")
    size = path.stat().st_size
    if size // 2048 < CDROM_SECTOR_LIMIT:
        return "cdrom"
    with path.open("rb") as source:
        header = source.read(1024)
    if header[510:512] == b"\x55\xaa":
        for offset in range(446, 510, 16):
            kind = header[offset + 4]
            start, count = struct.unpack_from("<II", header, offset + 8)
            if kind and count and (start + count) * 512 <= size:
                if kind != 0xEE or header[512:520] == b"EFI PART":
                    return "disk"
    raise ValueError(
        "ISO exceeds the USB CD-ROM size limit and has no disk partition table; "
        "use a hybrid ISO or bootable IMG image"
    )


if __name__ == "__main__":
    try:
        print(detect(Path(sys.argv[1])))
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
