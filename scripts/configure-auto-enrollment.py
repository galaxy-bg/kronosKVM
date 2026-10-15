#!/usr/bin/env python3
"""Administrator-only setup of a pinned, short-lived enrollment SSH credential."""

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.services.device_identity import read_identity  # noqa: E402
from backend.app.services.wireguard_auto import ROOT, read_transport  # noqa: E402


def atomic(path, value):
    temporary = path.with_suffix(".tmp")
    fd = os.open(temporary, os.O_CREAT | os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(value)
    temporary.replace(path)


def public_key(text):
    parts = text.strip().split()
    if len(parts) not in {2, 3} or parts[0] != "ssh-ed25519":
        raise ValueError("Require a pinned Ed25519 SSH host key")
    blob = base64.b64decode(parts[1], validate=True)
    if len(blob) != 51 or blob[:19] != b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20":
        raise ValueError("Invalid SSH public key")
    return "ssh-ed25519 " + parts[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "authorize"])
    parser.add_argument("--host")
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--host-key-file", type=Path)
    parser.add_argument("--grant", type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Run as root on the InfraBox")
    os.umask(0o077)
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        if args.command == "prepare":
            if (
                not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,252}", args.host or "")
                or not 1 <= args.port <= 65535
            ):
                raise ValueError("Invalid enrollment host or port")
            host_key = public_key(args.host_key_file.read_text())
            if not (ROOT / "id_ed25519").exists():
                (ROOT / "id_ed25519.pub").unlink(missing_ok=True)
                result = subprocess.run(
                    [
                        "ssh-keygen",
                        "-q",
                        "-t",
                        "ed25519",
                        "-N",
                        "",
                        "-C",
                        "kdx-one-time-enrollment",
                        "-f",
                        str(ROOT / "id_ed25519"),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode:
                    raise ValueError("Could not create local enrollment SSH key")
            host = args.host if args.port == 22 else f"[{args.host}]:{args.port}"
            atomic(ROOT / "known_hosts", host + " " + host_key + "\n")
            atomic(ROOT / "transport.json", json.dumps({"host": args.host, "port": args.port}))
            # Only the transport PUBLIC key is returned to the approving administrator.
            print(public_key((ROOT / "id_ed25519.pub").read_text()))
        else:
            grant = json.loads(args.grant.read_text())
            transport = read_transport()
            if (
                grant["device_id"] != read_identity()["serial"]
                or grant["hostname"] != os.uname().nodename
                or public_key(grant["ssh_public_key"])
                != public_key((ROOT / "id_ed25519.pub").read_text())
                or grant.get("state") != "authorized"
                or type(grant.get("expires_at")) is not int
                or str(uuid.UUID(grant["lease_id"])) != grant["lease_id"]
            ):
                raise ValueError("Grant does not match this device and transport key")
            atomic(
                ROOT / "transport.json",
                json.dumps(
                    {
                        **transport,
                        "expires_at": grant["expires_at"],
                        "lease_id": grant["lease_id"],
                        "completed": False,
                    }
                ),
            )
            print("Automatic registration authorized; use Generate & Register in Settings.")
    except Exception:
        print("Enrollment setup failed; verify the grant and pinned host key", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
