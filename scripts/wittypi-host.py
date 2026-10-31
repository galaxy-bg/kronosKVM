#!/usr/bin/env python3
"""Root-only Witty Pi preflight, UTC RTC initialization and public status snapshot."""

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend/app/hardware"))
from wittypi import sample  # noqa: E402

STATE = Path("/var/lib/kronoskvm/state")


def command(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=3, check=False)
    if result.returncode:
        raise RuntimeError("Witty Pi communication failed")
    return result.stdout.strip()


def read(reg):
    return int(command(["i2cget", "-y", "1", "0x08", str(reg), "b"]), 16)


def write(reg, value):
    command(["i2cset", "-y", "1", "0x08", str(reg), str(value), "b"])


def synchronized():
    return command(["timedatectl", "show", "-p", "NTPSynchronized", "--value"]) == "yes"


def prepare():
    value = sample(read)
    if not value["present"]:
        raise RuntimeError("Only the verified Witty Pi 4 model is supported")
    if command(["gpio", "-g", "read", "4"]) != "1":
        raise RuntimeError("Release the Witty Pi button before starting the daemon")
    if command(["gpio", "-g", "read", "14"]) != "1":
        raise RuntimeError("UART TXD must be idle high before starting Witty Pi")
    initialize(value)
    print("Witty Pi 4 preflight passed", flush=True)


def initialize(value=None):
    value = value or sample(read)
    if not value["present"]:
        raise RuntimeError("Verified Witty Pi 4 is required")
    if synchronized():
        # Preserve configured alarms; initialize only a board without a saved schedule.
        if not value["rtc_valid"] and any(read(reg) for reg in range(27, 37)):
            raise RuntimeError("Uninitialized RTC has saved alarms; operator review required")
        now = dt.datetime.now(dt.timezone.utc)
        fields = {59:now.minute, 60:now.hour, 61:now.day, 62:now.isoweekday(),
                  63:now.month, 64:now.year - 2000, 58:now.second}
        for reg, number in fields.items():
            write(reg, (number // 10) * 16 + number % 10)
        value = sample(read)
        if not value["rtc_valid"] or abs(value["rtc_offset_seconds"]) > 3:
            raise RuntimeError("RTC synchronization could not be verified")
        print("RTC synchronized from NTP system time (UTC)", flush=True)
    elif not value["rtc_valid"]:
        raise RuntimeError("RTC invalid and NTP unavailable; refusing to change system time")

def publish():
    try:
        value = sample(read)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        value = {"updated_at": dt.datetime.now(dt.timezone.utc).timestamp(),
                 "present": False, "rtc_valid": False,
                 "message":"Witty Pi is not reachable on I2C1"}
    STATE.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".wittypi-", dir=STATE)
    try:
        with os.fdopen(fd, "w") as stream:
            os.fchown(stream.fileno(), 10001, 20)
            os.fchmod(stream.fileno(), 0o640)
            json.dump(value, stream)
        Path(temporary).replace(STATE / "wittypi-status.json")
    finally:
        Path(temporary).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "initialize", "snapshot"])
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Run as root")
    try:
        if args.action == "prepare":
            prepare()
        elif args.action == "initialize":
            initialize()
        publish()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(str(error) if isinstance(error, RuntimeError) else "Witty Pi host operation failed",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
