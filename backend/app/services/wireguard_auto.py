"""Pinned SSH enrollment transport; never uses or stores a server password."""

import json
import re
import subprocess
import time
from pathlib import Path

from backend.app.services.remote_assist_config import ProfileError
from backend.app.services.wireguard_provisioning import registration_response

ROOT = Path("/etc/kronoskvm/remote-assist/enrollment-ssh")


def read_transport():
    try:
        value = json.loads((ROOT / "transport.json").read_text())
    except (OSError, ValueError):
        raise ProfileError("Administrator must authorize automatic registration first") from None
    host = value.get("host", "")
    port = value.get("port", 22)
    if (
        not isinstance(host, str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,252}", host)
        or type(port) is not int
        or not 1 <= port <= 65535
    ):
        raise ProfileError("Invalid automatic registration transport")
    return value


def cached_response(public):
    path = ROOT / "registration.json"
    if not path.exists():
        return None
    try:
        response = registration_response(json.loads(path.read_text()))
    except (ValueError, TypeError, AttributeError):
        raise ProfileError("Cached registration invalid; administrator recovery required") from None
    if any(response[k] != public[k] for k in public):
        raise ProfileError("Cached registration belongs to another identity")
    return response


def status():
    try:
        transport = read_transport()
    except ProfileError:
        return {"ready": False, "state": "not_authorized"}
    expires = transport.get("expires_at", 0)
    valid = isinstance(expires, (int, float)) and time.time() < expires
    ready = valid and all((ROOT / f).is_file() for f in ("id_ed25519", "known_hosts"))
    cached = (ROOT / "registration.json").exists()
    return {
        "ready": bool((ready or cached) and not transport.get("completed")),
        "state": "registered"
        if transport.get("completed")
        else "reply_cached"
        if cached
        else "authorized"
        if ready
        else "expired",
        "expires_at": expires if isinstance(expires, (int, float)) else 0,
        "server": transport["host"],
    }


def request_registration(public):
    cached = cached_response(public)
    if cached:
        return cached
    transport = read_transport()
    if not status()["ready"]:
        raise ProfileError("Automatic registration grant is unavailable or expired")
    result = subprocess.run(
        [
            "ssh",
            "-F",
            "/dev/null",
            "-T",
            "-p",
            str(transport.get("port", 22)),
            "-i",
            str(ROOT / "id_ed25519"),
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "IdentityAgent=none",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "UserKnownHostsFile=" + str(ROOT / "known_hosts"),
            "-o",
            "GlobalKnownHostsFile=/dev/null",
            "-o",
            "ConnectTimeout=8",
            "-o",
            "ConnectionAttempts=1",
            "-o",
            "ClearAllForwardings=yes",
            "-o",
            "ServerAliveInterval=5",
            "-o",
            "ServerAliveCountMax=3",
            "root@" + transport["host"],
            "enroll",
        ],
        input=json.dumps(public),
        capture_output=True,
        text=True,
        timeout=75,
    )
    if result.returncode:
        raise ProfileError("Automatic registration failed; check the grant and server access")
    if len(result.stdout) > 4096:
        raise ProfileError("Server registration response is too large")
    try:
        response = registration_response(json.loads(result.stdout))
    except (ValueError, TypeError, AttributeError):
        raise ProfileError("Server returned invalid public registration metadata") from None
    if any(response[k] != public[k] for k in public):
        raise ProfileError("Server registration response does not match this device")
    return response
