"""Read-only interpretation of Witty Pi 4 MCU registers and host snapshots."""

import datetime as dt
import json
import os
import time
from pathlib import Path


def bcd(value):
    if value & 15 > 9 or value >> 4 > 9:
        raise ValueError("Invalid RTC BCD")
    return (value >> 4) * 10 + (value & 15)


def sample(read, now=None):
    value = {"updated_at": time.time(), "present": False, "rtc_valid": False}
    identity, revision = read(0), read(12)
    value.update(firmware_id=f"0x{identity:02x}", firmware_revision=f"0x{revision:02x}")
    if identity != 0x26:
        value["message"] = "Unsupported Witty Pi model; power control is not enabled"
        return value
    value.update(present=True, model="Witty Pi 4")
    # Retry rollover rather than combining seconds from one minute with another.
    for _ in range(3):
        seconds = read(58)
        fields = [read(reg) for reg in range(59, 65)]
        if seconds == read(58):
            break
    else:
        value["message"] = "RTC read was not stable"
        return value
    try:
        minute, hour, day, weekday, month, year = fields
        calendar = dt.datetime(2000 + bcd(year), bcd(month & 31), bcd(day & 63),
                               bcd(hour & 63), bcd(minute & 127), bcd(seconds & 127),
                               tzinfo=dt.timezone.utc)
        if seconds & 128 or calendar.year < 2024 or weekday > 7:
            raise ValueError("RTC needs initialization")
    except ValueError:
        value["message"] = "RTC needs initialization from synchronized system time"
        return value
    now = now or dt.datetime.now(dt.timezone.utc)
    value.update(rtc_valid=True, rtc_time_utc=calendar.isoformat(),
                 rtc_offset_seconds=round((calendar - now).total_seconds(), 2),
                 message="RTC available (UTC)")
    return value


def snapshot(path=None):
    path = path or Path(os.environ.get("KRONOSKVM_STATE_PATH", "/state")) / "wittypi-status.json"
    try:
        value = json.loads(path.read_text())
        if (not isinstance(value, dict) or type(value.get("updated_at")) not in (int, float)
                or not 0 <= time.time() - value["updated_at"] <= 30):
            return {}
        return value
    except (OSError, ValueError, TypeError):
        return {}
