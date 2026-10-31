"""InfraBox host registration agent. Private keys never leave this host."""

import argparse
import base64
import fcntl
import hashlib
import json
import os
import secrets
import socket
import ssl
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


class Denied(Exception):
    pass


class Unavailable(Exception):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def read_serial():
    for path in ("/sys/firmware/devicetree/base/serial-number", "/proc/device-tree/serial-number"):
        if Path(path).exists():
            value = Path(path).read_bytes().rstrip(b"\0").decode().upper()
            break
    else:
        value = ""
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("Serial"):
                value = line.split(":", 1)[1].strip().upper()
                break
    if len(value) != 16 or any(c not in "0123456789ABCDEF" for c in value):
        raise Denied("HARDWARE_SERIAL_UNAVAILABLE")
    return value


def atomic_json(path, value, mode=0o600):
    path = Path(path)
    temp = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w") as stream:
            stream.write(canonical(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def read_json(path, fallback=None):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return fallback


def identity(directory):
    path = Path(directory) / "identity.json"
    if not path.exists():
        key = Ed25519PrivateKey.generate()
        atomic_json(
            path,
            {
                "installation_id": str(uuid.uuid4()),
                "private_key": base64.b64encode(
                    key.private_bytes(
                        serialization.Encoding.Raw,
                        serialization.PrivateFormat.Raw,
                        serialization.NoEncryption(),
                    )
                ).decode(),
            },
        )
    data = read_json(path)
    key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(data["private_key"], validate=True))
    public = base64.b64encode(
        key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    ).decode()
    return {
        "serial": read_serial(),
        "installation_id": data["installation_id"],
        "public_key": public,
    }, key


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Transport:
    def __init__(self, config, url=None):
        self.url = (url or config["server_url"]).rstrip("/")
        parsed = urlsplit(self.url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in ("", "/")
        ):
            raise Denied("INVALID_SERVER_URL")
        if parsed.scheme != "https" and not config.get("allow_lab_http", False):
            raise Denied("HTTPS_REQUIRED")
        self.timeout = min(max(int(config.get("timeout_seconds", 8)), 1), 30)
        # Ignore proxy environment variables and refuse redirects carrying proofs/tokens.
        try:
            context = ssl.create_default_context()
            if config.get("ca_bundle"):
                certificate = Path(config["ca_bundle"]).read_text()
                expected = config.get("ca_certificate_sha256", "").replace(":", "").lower()
                fingerprint = hashlib.sha256(ssl.PEM_cert_to_DER_cert(certificate)).hexdigest()
                if not expected or not secrets.compare_digest(fingerprint, expected):
                    raise Denied("TLS_TRUST_ANCHOR_MISMATCH")
                context.load_verify_locations(cafile=config["ca_bundle"])
            self.opener = build_opener(
                ProxyHandler({}), NoRedirects(), HTTPSHandler(context=context)
            )
        except (OSError, ValueError, ssl.SSLError):
            raise Denied("TLS_CONFIGURATION_INVALID") from None

    def post(self, path, value):
        request = Request(
            self.url + path,
            data=canonical(value).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                body = response.read(65537)
                if len(body) > 65536:
                    raise Denied("INVALID_SERVER_RESPONSE")
                return json.loads(body)
        except HTTPError as error:
            # A reachable server error cannot resurrect a previous ACTIVE document.
            try:
                body = json.loads(error.read(16384))
                detail = body.get("detail", "")
            except (ValueError, AttributeError):
                detail = ""
            if detail not in {"HARDWARE_MISMATCH", "IDENTITY_MISMATCH", "KEY_REUSE"}:
                detail = "SERVER_REJECTED_REQUEST"
            raise Denied(detail) from None
        except URLError as error:
            if isinstance(error.reason, ssl.SSLError):
                raise Denied("TLS_VALIDATION_FAILED") from None
            raise Unavailable("SERVER_UNREACHABLE") from None
        except (TimeoutError, socket.timeout, ConnectionError):
            raise Unavailable("SERVER_UNREACHABLE") from None
        except (ValueError, TypeError):
            raise Denied("INVALID_SERVER_RESPONSE") from None


def verify_document(document, pinned_key, request, device_id, last_clock=0, clock=None):
    tick = int(time.time() if clock is None else clock)
    payload = document["payload"]
    public = Ed25519PublicKey.from_public_bytes(base64.b64decode(pinned_key, validate=True))
    public.verify(
        base64.b64decode(document["signature"], validate=True), canonical(payload).encode()
    )
    if (
        payload["v"] != 1
        or payload["aud"] != "kdx-infrabox-registration"
        or payload["status"] != "ACTIVE"
        or payload["serial"] != request["serial"]
        or payload["installation_id"] != request["installation_id"]
        or payload["key_hash"] != digest(request["public_key"])
        or payload["device_id"] != device_id
        or not isinstance(payload["license_id"], str)
        or payload["issued_at"] > tick + 30
        or tick >= payload["expires_at"]
        or payload["expires_at"] - payload["issued_at"] > 604800
        or tick < last_clock
    ):
        raise Denied("INVALID_AUTHORIZATION_DOCUMENT")
    return payload


def prove(transport, request, key, token=None):
    purpose = "activate" if token else "authenticate"
    challenge = transport.post("/api/v1/devices/challenge", {**request, "purpose": purpose})
    message = challenge["message"]
    value = json.loads(message)
    # Only sign the expected protocol, identity, purpose and a live server nonce.
    tick = int(time.time())
    if (
        value["aud"] != "kdx-infrabox-registration"
        or value["v"] != 1
        or value["purpose"] != purpose
        or value["serial"] != request["serial"]
        or value["installation_id"] != request["installation_id"]
        or value["key_hash"] != digest(request["public_key"])
        or value["challenge_id"] != challenge["challenge_id"]
        or not tick <= value["expires_at"] <= tick + 300
        or not isinstance(value["nonce"], str)
        or len(value["nonce"]) < 32
    ):
        raise Denied("INVALID_SERVER_CHALLENGE")
    proof = {
        "challenge_id": challenge["challenge_id"],
        "signature": base64.b64encode(key.sign(message.encode())).decode(),
    }
    if token:
        proof["activation_token"] = token
    return transport.post("/api/v1/devices/" + ("activate" if token else "verify"), proof)


def synchronize(config, directory, transport=None, token=None):
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    request, key = identity(directory)
    tick = int(time.time())
    cache = read_json(directory / "authorization.json", {})
    status = {
        "serial": request["serial"],
        "installation_id": request["installation_id"],
        "public_key": request["public_key"],
        "checked_at": tick,
        "server_url": config["server_url"],
        "authorized": False,
    }
    try:
        transport = transport or Transport(config)
        enrollment = transport.post(
            "/api/v1/devices/enroll",
            {
                **request,
                "model": config.get("model", "Galaxy-RP4"),
                "firmware": config.get("firmware", "0.3.46"),
            },
        )
        device_id = str(uuid.UUID(enrollment["device_id"]))
        status["device_id"] = device_id
        if enrollment["installation_id"] != request["installation_id"]:
            raise Denied("INVALID_ENROLLMENT_RESPONSE")
        result = prove(transport, request, key, token)
        if result["device_id"] != device_id:
            raise Denied("INVALID_DEVICE_BINDING")
        status.update(status=result["status"], mode="online")
        if result["status"] == "ACTIVE":
            payload = verify_document(
                result["authorization"],
                config["server_public_key"],
                request,
                device_id,
                last_clock=cache.get("last_clock", 0),
            )
            atomic_json(
                directory / "authorization.json",
                {
                    "document": result["authorization"],
                    "device_id": device_id,
                    "last_clock": tick,
                    "denied": False,
                },
            )
            status.update(
                authorized=True,
                license_id=payload["license_id"],
                authorization_expires_at=payload["expires_at"],
            )
        else:
            atomic_json(directory / "authorization.json", {"denied": True, "last_clock": tick})
    except Unavailable:
        status.update(status="UNAVAILABLE", mode="offline", error="SERVER_UNREACHABLE")
        if not token and cache.get("document") and not cache.get("denied"):
            try:
                payload = verify_document(
                    cache["document"],
                    config["server_public_key"],
                    request,
                    cache["device_id"],
                    cache.get("last_clock", 0),
                )
                status.update(
                    status="ACTIVE",
                    mode="offline-grace",
                    authorized=True,
                    device_id=cache["device_id"],
                    license_id=payload["license_id"],
                    authorization_expires_at=payload["expires_at"],
                )
                cache["last_clock"] = tick
                atomic_json(directory / "authorization.json", cache)
            except (Denied, InvalidSignature, KeyError, ValueError, TypeError):
                status["error"] = "OFFLINE_AUTHORIZATION_INVALID_OR_EXPIRED"
    except (Denied, InvalidSignature, KeyError, ValueError, TypeError) as error:
        reason = str(error) if isinstance(error, Denied) else "INVALID_SERVER_RESPONSE"
        status.update(status="DENIED", mode="online", error=reason)
        if reason == "HARDWARE_MISMATCH":
            status["status"] = reason
        atomic_json(directory / "authorization.json", {"denied": True, "last_clock": tick})
    status["transport"] = "https" if config["server_url"].startswith("https://") else "lab-http"
    atomic_json(directory / "status.json", status)
    if config.get("public_status_directory"):
        public_dir = Path(config["public_status_directory"])
        public_dir.mkdir(mode=0o755, parents=True, exist_ok=True)
        allowed = {
            "serial",
            "installation_id",
            "device_id",
            "license_id",
            "checked_at",
            "authorization_expires_at",
            "server_url",
            "authorized",
            "status",
            "mode",
            "transport",
            "error",
        }
        atomic_json(
            public_dir / "status.json",
            {k: v for k, v in status.items() if k in allowed},
            mode=0o644,
        )
    return status


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["sync", "activate", "identity", "status"])
    parser.add_argument("--config", default="/etc/kdx-registration-client/config.json")
    parser.add_argument("--state", default="/var/lib/kdx-registration")
    parser.add_argument("--url", help="Explicit temporary lab transport override")
    args = parser.parse_args()
    directory = Path(args.state)
    if args.command == "status":
        print(
            json.dumps(read_json(directory / "status.json", {"status": "NOT_CONFIGURED"}), indent=2)
        )
        return
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (directory / "agent.lock").open("a") as lock:
        os.chmod(directory / "agent.lock", 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.command == "identity":
            print(json.dumps(identity(directory)[0], indent=2))
            return
        config = read_json(args.config)
        token = None
        if args.command == "activate":
            import getpass

            token = getpass.getpass("One-time activation token: ")
        if args.url:
            config["server_url"] = args.url
        status = synchronize(config, directory, token=token)
        print(json.dumps(status, indent=2))
        if status["status"] in ("DENIED", "HARDWARE_MISMATCH", "UNAVAILABLE"):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
