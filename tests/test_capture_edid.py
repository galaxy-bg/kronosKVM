from pathlib import Path

EDID = Path(__file__).resolve().parents[1] / "config/edid/infrabox-compat.hex"


def test_capture_edid_checksums_and_safe_timings():
    data = bytes.fromhex(EDID.read_text())
    assert data[:8] == bytes.fromhex("00ffffffffffff00")
    assert len(data) == 128 * (1 + data[126]) == 256
    assert all(sum(data[i:i + 128]) % 256 == 0 for i in (0, 128))

    modes = []
    for offset in range(54, 126, 18):
        dtd = data[offset:offset + 18]
        clock = int.from_bytes(dtd[:2], "little") * 10000
        if not clock:
            continue
        width = dtd[2] + ((dtd[4] >> 4) << 8)
        height = dtd[5] + ((dtd[7] >> 4) << 8)
        total_width = width + dtd[3] + ((dtd[4] & 15) << 8)
        total_height = height + dtd[6] + ((dtd[7] & 15) << 8)
        assert clock <= 80000000
        assert not dtd[17] & 128  # No interlaced modes.
        modes.append((width, height, round(clock / total_width / total_height)))
    assert modes == [(1280, 720, 60), (1920, 1080, 30)]
    assert data[35:38] == bytes.fromhex("210800")  # Legacy 60 Hz PC modes.
    assert data[38:54] == bytes.fromhex("0101" * 8)

    cta = data[128:]
    assert cta[:2] == bytes([2, 3])
    offset = 4
    vics = []
    while offset < cta[2]:
        header = cta[offset]
        payload = cta[offset + 1:offset + 1 + (header & 31)]
        assert len(payload) == header & 31
        if header >> 5 == 2:
            vics.extend(vic & 127 for vic in payload)
        offset += 1 + len(payload)
    assert offset == cta[2]
    assert vics == [4, 19, 34, 33, 32, 2, 17, 1]
