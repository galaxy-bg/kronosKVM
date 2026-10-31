#!/usr/bin/env python3
"""Short-lived, device-bound SSH forced command for one approved registration."""

import argparse
import base64
import datetime
import fcntl
import importlib.util
import json
import os
import re
import signal
import sys
import time
import uuid
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "kdx_wg_server", Path(__file__).with_name("kdx-wg-server.py"),
)
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

LEASES = Path("/var/lib/kdx-wg-enrollment")
AUTHORIZED_KEYS = Path("/root/.ssh/authorized_keys")
COMMAND = "/usr/local/sbin/kdx-wg-enroll.py"


def ssh_public(value):
    parts = value.strip().split()
    if len(parts) not in {2, 3} or parts[0] != "ssh-ed25519":
        raise server.ProvisionError("Use one Ed25519 enrollment public key")
    try:
        blob = base64.b64decode(parts[1], validate=True)
    except (ValueError, TypeError):
        raise server.ProvisionError("Invalid enrollment public key") from None
    if (len(blob) != 51 or blob[:19] != b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20"
            or blob[19:] == bytes(32)):
        raise server.ProvisionError("Invalid enrollment public key")
    return "ssh-ed25519 " + parts[1]


def lease_path(lease_id):
    if str(uuid.UUID(lease_id)) != lease_id:
        raise server.ProvisionError("Invalid enrollment grant")
    return LEASES / (lease_id + ".json")


def authorize(device_id, hostname, public, endpoint, ttl=900):
    if not re.fullmatch(r"[0-9a-f]{16}", device_id) or not int(device_id, 16):
        raise server.ProvisionError("Invalid device serial")
    server.name(hostname)
    if not 60 <= ttl <= 1800:
        raise server.ProvisionError("Enrollment lifetime must be 60–1800 seconds")
    if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,252}:[0-9]{1,5}", endpoint)
            or not 1 <= int(endpoint.rsplit(":", 1)[1]) <= 65535):
        raise server.ProvisionError("Invalid VPN endpoint")
    public = ssh_public(public)
    LEASES.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(LEASES, 0o700)
    AUTHORIZED_KEYS.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    lease_id = str(uuid.uuid4())
    expires = int(time.time()) + ttl
    grant = {"lease_id": lease_id, "expires_at": expires, "device_id": device_id,
             "hostname": hostname, "ssh_public_key": public, "endpoint": endpoint,
             "state": "authorized"}
    timestamp = datetime.datetime.fromtimestamp(expires, datetime.timezone.utc).strftime(
        "%Y%m%d%H%M%SZ",
    )
    # Restricted key cannot open shells, PTYs, forwarding or user rc files.
    line = (f'restrict,expiry-time="{timestamp}",command="{COMMAND} serve --lease {lease_id}" '
            f'{public} kdx-enroll-{lease_id}\n')
    with (LEASES / "authorized-keys.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        before = AUTHORIZED_KEYS.read_text() if AUTHORIZED_KEYS.exists() else ""
        # Never allow a key with existing broader access to masquerade as a restricted grant.
        if public.split()[1] in before:
            raise server.ProvisionError("Use a fresh enrollment SSH key; key is already authorized")
        server.atomic(lease_path(lease_id), json.dumps(grant))
        try:
            server.atomic(AUTHORIZED_KEYS, before.rstrip("\n") + "\n" + line)
        except Exception:
            lease_path(lease_id).unlink(missing_ok=True)
            raise
    return grant


def receive(lease_id, request):
    server.validate_request(request)
    path = lease_path(lease_id)
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        grant = json.loads(path.read_text())
        if grant["state"] == "revoked" or time.time() >= grant["expires_at"]:
            raise server.ProvisionError("Enrollment grant expired or revoked")
        if request["device_id"] != grant["device_id"] or request["hostname"] != grant["hostname"]:
            raise server.ProvisionError("Enrollment grant belongs to a different device")
        if grant["state"] == "completed":
            # Retrieving the same public reply is safe after a lost SSH response. No new peer.
            if request != grant.get("request"):
                raise server.ProvisionError("Enrollment grant has already been used")
            return grant["registration"]
        manager = server.Server("/etc/wireguard/wg0.conf", "/etc/wireguard/kdx-peers.json",
                                endpoint=grant["endpoint"])
        # Bind the grant before mutation: a failed/lost response cannot register another key.
        if grant.get("request") and grant["request"] != request:
            raise server.ProvisionError("Enrollment grant is bound to an earlier request")
        grant["request"] = request
        server.atomic(path, json.dumps(grant))
        records = manager.records()
        existing = records.get(request["hostname"])
        if existing and all(existing.get(k) == request[k] for k in request):
            registration = existing
        else:
            registration = manager.add(request)
        grant.update(state="completed", registration=registration)
        server.atomic(path, json.dumps(grant))
        return registration


def revoke(lease_id):
    path = lease_path(lease_id)
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        grant = json.loads(path.read_text())
        grant["state"] = "revoked"
        server.atomic(path, json.dumps(grant))
        with (LEASES / "authorized-keys.lock").open("a") as key_lock:
            fcntl.flock(key_lock, fcntl.LOCK_EX)
            text = AUTHORIZED_KEYS.read_text()
            marker = "kdx-enroll-" + lease_id
            server.atomic(AUTHORIZED_KEYS, "".join(
                line for line in text.splitlines(keepends=True)
                if not line.rstrip().endswith(marker)
            ))
    return {"revoked": lease_id}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["authorize", "serve", "revoke"])
    parser.add_argument("--device-id")
    parser.add_argument("--hostname")
    parser.add_argument("--ssh-public-key-file", type=Path)
    parser.add_argument("--endpoint")
    parser.add_argument("--ttl", type=int, default=900)
    parser.add_argument("--lease")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Run as root on the approved VPN server")
    os.umask(0o077)
    try:
        if args.command == "authorize":
            result = authorize(args.device_id or "", args.hostname or "",
                               args.ssh_public_key_file.read_text(), args.endpoint or "", args.ttl)
        elif args.command == "revoke":
            result = revoke(args.lease or "")
        else:
            if os.environ.get("SSH_ORIGINAL_COMMAND", "") not in {"", "enroll"}:
                raise server.ProvisionError("Only the enrollment command is permitted")
            # Bound input time; never interrupt a peer transaction/rollback with an alarm.
            signal.signal(signal.SIGALRM, lambda *a: (_ for _ in ()).throw(
                server.ProvisionError("Enrollment input timed out")))
            signal.alarm(10)
            try:
                raw = sys.stdin.buffer.read(4097)
            finally:
                signal.alarm(0)
            if len(raw) > 4096:
                raise server.ProvisionError("Public enrollment request exceeds 4 KiB")
            result = receive(args.lease or "", json.loads(raw))
        print(json.dumps(result, indent=2))
    except Exception as error:
        print(str(error) if isinstance(error, server.ProvisionError) else
              "Enrollment failed; inspect approved grant and server configuration", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
