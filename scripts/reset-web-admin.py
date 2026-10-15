#!/usr/bin/env python3
"""Host-administrator recovery of the single web account."""

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

AUTH_FILE = Path("/var/lib/kronoskvm/state/web-auth.json")


def reset_credentials(path, runner=subprocess.run, owner=(10001, 20)):
    salt = secrets.token_hex(16)
    value = {
        "username": "admin",
        "salt": salt,
        "hash": hashlib.scrypt(
            b"ChangeMe", salt=bytes.fromhex(salt), n=32768, r=8, p=3, maxmem=64 * 1024 * 1024
        ).hex(),
        "must_change_password": False,
    }
    # Stop first: revoke sessions and avoid races with in-process credential changes.
    runner(["docker", "stop", "kronoskvm-api"], check=True, stdout=subprocess.DEVNULL)
    temporary = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=".web-auth-reset-", dir=path.parent)
        temporary = Path(name)
        with os.fdopen(descriptor, "w") as stream:
            os.fchown(stream.fileno(), *owner)
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        try:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        finally:
            runner(["docker", "start", "kronoskvm-api"], check=True, stdout=subprocess.DEVNULL)
    runner(
        [
            "logger",
            "--tag",
            "kdx-infrabox-auth",
            "Web admin credentials reset by host administrator",
        ],
        check=False,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Reset web admin to admin / ChangeMe. SSH accounts are unchanged."
    )
    parser.add_argument(
        "--yes", action="store_true", help="Confirm reset without an interactive prompt"
    )
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Run with sudo from the appliance host.")
    if not args.yes:
        if not sys.stdin.isatty():
            parser.error("Use an interactive terminal or explicitly pass --yes.")
        print(
            "This resets web admin and signs out all web sessions. SSH accounts remain unchanged."
        )
        if input("Type RESET to continue: ").strip() != "RESET":
            print("Cancelled.")
            return 0
    try:
        reset_credentials(AUTH_FILE)
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"Reset failed: {error}. Check the API container status.", file=sys.stderr)
        return 1
    print("Web login restored: admin / ChangeMe. Password replacement is optional.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
