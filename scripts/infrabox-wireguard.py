#!/usr/bin/env python3
"""Root-only local CLI for the same Remote Assist provisioning controller."""

import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "kdx_remote_assist_host",
    Path(__file__).with_name("remote-assist-host.py"),
)
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "identity",
            "request",
            "status",
            "import",
            "connect",
            "disconnect",
            "restart",
            "boot-on",
            "boot-off",
            "auto-register",
        ],
    )
    parser.add_argument("registration", nargs="?", type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Run as root on the InfraBox")
    os.umask(0o077)
    try:
        with (host.STATE / "remote-assist.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if (host.STATE / "remote-assist-request.json").exists():
                raise ValueError("A GUI VPN request is pending")
            config = host.read_config()
            if args.command == "request":
                value = host.identity_public()
                if not value:
                    raise ValueError("Generate identity first")
            elif args.command == "status":
                host.snapshot(config)
                value = json.loads((host.STATE / "remote-assist-status.json").read_text())
            else:
                if args.command == "import":
                    if not args.registration or args.registration.stat().st_size > 4096:
                        raise ValueError("Provide approved public registration JSON under 4 KiB")
                    request = {
                        "action": "register",
                        "registration": json.loads(args.registration.read_text()),
                    }
                else:
                    request = {
                        "action": {
                            "identity": "generate-identity",
                            "connect": "enable",
                            "disconnect": "disable",
                        }.get(args.command, args.command)
                    }
                config = host.transactional_process(config, request)
                host.snapshot(config)
                value = host.identity_public() if args.command == "identity" else {"ok": True}
            print(json.dumps(value, indent=2))
    except Exception as error:
        # Never include raw input or subprocess output in a user-facing failure.
        print(
            str(error)
            if isinstance(error, (host.ProfileError, RuntimeError))
            else "VPN operation failed; check provisioning input and host service",
            file=host.sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
