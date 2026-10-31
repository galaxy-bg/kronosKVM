"""Virtual or real device identity and signed offline authorization verification."""

import argparse
import base64
import json
import os
import time
import uuid
from pathlib import Path

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.crypto import canonical, digest, public_key


def hardware_serial():
    for path in ("/sys/firmware/devicetree/base/serial-number", "/proc/device-tree/serial-number"):
        if Path(path).exists():
            return Path(path).read_bytes().rstrip(b"\0").decode().upper()
    for line in Path("/proc/cpuinfo").read_text().splitlines():
        if line.startswith("Serial"):
            return line.split(":", 1)[1].strip().upper()
    raise RuntimeError("Raspberry Pi serial unavailable; simulator requires --serial")


def write_private(path, data):
    path = Path(path)
    temp = path.with_suffix(".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(data, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def identity(root, serial=None):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / "identity.json"
    if not path.exists():
        key = Ed25519PrivateKey.generate()
        data = {
            "installation_id": str(uuid.uuid4()),
            "private_key": base64.b64encode(
                key.private_bytes(
                    serialization.Encoding.Raw,
                    serialization.PrivateFormat.Raw,
                    serialization.NoEncryption(),
                )
            ).decode(),
        }
        write_private(path, data)
    data = json.loads(path.read_text())
    key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(data["private_key"]))
    request = {
        "serial": (serial or hardware_serial()).upper(),
        "installation_id": data["installation_id"],
        "public_key": base64.b64encode(
            key.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            )
        ).decode(),
    }
    return request, key


def verify_offline(document, server_public_key, request, clock=None, last_clock=0):
    tick = int(time.time() if clock is None else clock)
    payload = document["payload"]
    public_key(server_public_key).verify(
        base64.b64decode(document["signature"]), canonical(payload).encode()
    )
    if (
        payload["aud"] != "kdx-infrabox-registration"
        or payload["v"] != 1
        or payload["status"] != "ACTIVE"
        or payload["serial"] != request["serial"]
        or payload["installation_id"] != request["installation_id"]
        or payload["key_hash"] != digest(request["public_key"])
        or not payload["issued_at"] <= tick < payload["expires_at"]
        or tick < last_clock
    ):
        raise ValueError("Offline authorization invalid, expired or bound to other hardware")
    return payload


def authenticate(client, request, key, token=None):
    challenge = client.post(
        "/api/v1/devices/challenge",
        json={**request, "purpose": "activate" if token else "authenticate"},
    )
    challenge.raise_for_status()
    challenge = challenge.json()
    proof = {
        "challenge_id": challenge["challenge_id"],
        "signature": base64.b64encode(key.sign(challenge["message"].encode())).decode(),
    }
    if token:
        proof["activation_token"] = token
    result = client.post("/api/v1/devices/" + ("activate" if token else "verify"), json=proof)
    result.raise_for_status()
    return result.json()


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["identity", "enroll", "authenticate", "activate"])
    parser.add_argument("--state", default="./device-state")
    parser.add_argument("--serial", help="Virtual Pi serial (16 hexadecimal characters)")
    parser.add_argument("--url", default="http://172.12.2.82:8080")
    parser.add_argument("--lab-http", action="store_true")
    parser.add_argument("--server-public-key", help="Out-of-band pinned Ed25519 server public key")
    args = parser.parse_args()
    request, key = identity(args.state, args.serial)
    if args.command == "identity":
        print(json.dumps(request, indent=2))
        return
    if not args.url.startswith("https://") and not args.lab_http:
        raise SystemExit("HTTPS required; use --lab-http only inside the isolated lab")
    cache_path = Path(args.state) / "authorization.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    try:
        with httpx.Client(base_url=args.url, timeout=10, follow_redirects=False) as client:
            if args.command == "enroll":
                response = client.post(
                    "/api/v1/devices/enroll",
                    json={**request, "model": "Galaxy-RP4", "firmware": "simulator-1"},
                )
                response.raise_for_status()
                print(json.dumps(response.json(), indent=2))
                return
            token = None
            if args.command == "activate":
                import getpass

                token = getpass.getpass("One-time activation token: ")
            result = authenticate(client, request, key, token)
            # Any authoritative denial invalidates previous offline authorization.
            if result["status"] != "ACTIVE":
                write_private(cache_path, {"denied": True, "last_clock": int(time.time())})
            elif args.server_public_key:
                verify_offline(result["authorization"], args.server_public_key, request)
                write_private(
                    cache_path,
                    {
                        "document": result["authorization"],
                        "last_clock": int(time.time()),
                        "denied": False,
                    },
                )
            print(json.dumps({k: v for k, v in result.items() if k != "session_token"}, indent=2))
    except (httpx.ConnectError, httpx.TimeoutException):
        if (
            args.command != "authenticate"
            or not args.server_public_key
            or cache.get("denied")
            or not cache.get("document")
        ):
            raise SystemExit("Server unavailable; no valid offline authorization") from None
        try:
            payload = verify_offline(
                cache["document"],
                args.server_public_key,
                request,
                last_clock=cache.get("last_clock", 0),
            )
        except (KeyError, ValueError, InvalidSignature):
            raise SystemExit("Server unavailable; offline authorization rejected") from None
        cache["last_clock"] = int(time.time())
        write_private(cache_path, cache)
        print(
            json.dumps(
                {"status": "ACTIVE", "mode": "offline-grace", "expires_at": payload["expires_at"]}
            )
        )
    except httpx.HTTPStatusError:
        write_private(cache_path, {"denied": True, "last_clock": int(time.time())})
        raise SystemExit("Server rejected request; cached authorization invalidated") from None


if __name__ == "__main__":
    run()
