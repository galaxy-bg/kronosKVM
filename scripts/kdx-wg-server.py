#!/usr/bin/env python3
"""Approved local peer registration; no daemon or internet enrollment endpoint."""

import argparse
import base64
import contextlib
import fcntl
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path


class ProvisionError(ValueError):
    pass


def public_key(value):
    try:
        if not isinstance(value, str) or len(base64.b64decode(value, validate=True)) != 32:
            raise ValueError
    except (ValueError, TypeError):
        raise ProvisionError("Invalid WireGuard public key") from None
    if base64.b64decode(value) == bytes(32):
        raise ProvisionError("All-zero public key is invalid")
    return value


def name(value):
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", value):
        raise ProvisionError("Peer name must use lowercase letters, digits and hyphens")
    return value


def atomic(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".kdx-wg-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def wg(*args):
    result = subprocess.run(["wg", *args], capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise ProvisionError("WireGuard operation failed; no secret output was printed")
    return result.stdout.strip()


def blocks(text):
    return re.split(r"(?m)(?=^\s*\[(?:Interface|Peer)\]\s*(?:#.*)?$)", text)


def fields(block):
    data = {}
    for line in block.splitlines():
        line = line.split("#", 1)[0].strip()
        if "=" in line:
            k, v = line.split("=", 1)
            data.setdefault(k.strip().lower(), []).append(v.strip())
    return data


def peers(text):
    found = {}
    for block in blocks(text):
        if not re.match(r"\s*\[Peer\]", block):
            continue
        data = fields(block)
        keys = data.get("publickey", [])
        if len(keys) != 1 or keys[0] in found:
            raise ProvisionError("Duplicate or invalid peer in server configuration")
        pub = public_key(keys[0])
        try:
            networks = [ipaddress.ip_network(n.strip(), strict=False)
                        for line in data.get("allowedips", []) for n in line.split(",")]
        except ValueError:
            raise ProvisionError("Invalid AllowedIPs in server configuration") from None
        found[pub] = networks
    return found


def validate_request(request):
    if not isinstance(request, dict) or set(request) != {
        "version", "device_id", "hostname", "public_key", "request_id",
    } or type(request.get("version")) is not int or request["version"] != 1:
        raise ProvisionError("Invalid public registration request")
    name(request["hostname"])
    public_key(request["public_key"])
    if (not isinstance(request["device_id"], str)
            or not re.fullmatch(r"[0-9a-f]{16}", request["device_id"])
            or not int(request["device_id"], 16)):
        raise ProvisionError("Invalid device serial")
    if str(uuid.UUID(request["request_id"])) != request["request_id"]:
        raise ProvisionError("Invalid request identifier")
    return request.copy()


class Server:
    def __init__(self, config, registry, interface="wg0", network="10.77.0.0/24",
                 start="10.77.0.11", end="10.77.0.254", endpoint=None):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,15}", interface):
            raise ProvisionError("Invalid interface")
        self.config, self.registry = Path(config), Path(registry)
        self.interface, self.endpoint = interface, endpoint
        self.network = ipaddress.IPv4Network(network)
        if not any(self.network.subnet_of(ipaddress.IPv4Network(private))
                   for private in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")):
            raise ProvisionError("Use a specific private IPv4 VPN subnet")
        self.start, self.end = ipaddress.IPv4Address(start), ipaddress.IPv4Address(end)
        if (self.start not in self.network or self.end not in self.network or self.start > self.end
                or self.start <= self.network.network_address
                or self.end >= self.network.broadcast_address):
            raise ProvisionError("Invalid allocation pool")

    @contextlib.contextmanager
    def locked(self):
        self.registry.parent.mkdir(parents=True, exist_ok=True)
        path = self.registry.with_suffix(".lock")
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ProvisionError("Another provisioning operation is running") from None
            yield

    def records(self):
        try:
            value = json.loads(self.registry.read_text())
        except FileNotFoundError:
            return {}
        if not isinstance(value, dict):
            raise ProvisionError("Invalid peer registry")
        return value

    def runtime(self):
        values = {}
        for line in wg("show", self.interface, "allowed-ips").splitlines():
            pub, _, allowed = line.partition("\t")
            values[public_key(pub)] = [ipaddress.ip_network(n, strict=False)
                                      for n in allowed.replace(",", " ").split()
                                      if n != "(none)"]
        return values

    def inventory(self):
        text = self.config.read_text()
        if any(v.lower() == "true" for v in fields(text).get("saveconfig", [])):
            raise ProvisionError("SaveConfig=true: refuse mutation; reconcile file/live peers and "
                                 "set SaveConfig=false under operator approval first")
        return text, peers(text), self.runtime(), self.records()

    def allocate(self, file_peers, live_peers, records, requested=None):
        used = [n for p in (file_peers, live_peers) for nets in p.values() for n in nets]
        for record in records.values():
            used.append(ipaddress.ip_network(record["address"]))
        # Also reserve every configured interface address, including secondary addresses.
        for item in fields(self.config.read_text()).get("address", []):
            for address in item.split(","):
                used.append(ipaddress.ip_network(str(ipaddress.ip_interface(address.strip()).ip)))
        candidates = [ipaddress.IPv4Address(requested)] if requested else (
            ipaddress.IPv4Address(i) for i in range(int(self.start), int(self.end) + 1))
        for address in candidates:
            if not self.start <= address <= self.end:
                raise ProvisionError("Requested IP is outside allocation pool")
            if not any(address.version == n.version and address in n for n in used):
                return str(address) + "/32"
        raise ProvisionError("Requested IP is occupied or allocation pool is exhausted")

    def metadata(self, request, address):
        endpoint = self.endpoint or ""
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,252}:[0-9]{1,5}", endpoint):
            raise ProvisionError("Specify --endpoint hostname:port")
        if not 1 <= int(endpoint.rsplit(":", 1)[1]) <= 65535:
            raise ProvisionError("Invalid endpoint port")
        return {**request, "address": address, "endpoint": endpoint,
                "server_public_key": public_key(wg("show", self.interface, "public-key")),
                "allowed_ips": str(self.network), "keepalive": 25}

    def transaction(self, before, after, old_records, new_records, pub, new_address, live):
        backups = self.config.parent / "kdx-backups"
        backups.mkdir(mode=0o700, exist_ok=True)
        os.chmod(backups, 0o700)
        backup = Path(tempfile.mkdtemp(prefix="peer-", dir=backups))
        shutil.copy2(self.config, backup / "interface.conf")
        os.chmod(backup / "interface.conf", 0o600)
        registry_existed = self.registry.exists()
        atomic(backup / "registry.json", json.dumps(old_records))
        atomic(backup / "operation.json", json.dumps({"peer": pub, "address": new_address}))
        # Change only the selected peer; never replace other peers or restart wg0.
        previous_peer = "".join(b for b in blocks(wg("showconf", self.interface))
                                if fields(b).get("publickey") == [pub])
        if pub in live and not previous_peer:
            raise ProvisionError("Could not capture previous peer for rollback")
        atomic(backup / "live-peer.conf", previous_peer)
        changed_live = False
        try:
            atomic(self.config, after)
            atomic(self.registry, json.dumps(new_records, indent=2) + "\n")
            changed_live = True
            if new_address is None:
                wg("set", self.interface, "peer", pub, "remove")
            else:
                wg("set", self.interface, "peer", pub, "allowed-ips", new_address)
        except Exception:
            atomic(self.config, before)
            if registry_existed:
                atomic(self.registry, json.dumps(old_records, indent=2) + "\n")
            else:
                self.registry.unlink(missing_ok=True)
            if changed_live:
                try:
                    if pub in live:
                        wg("addconf", self.interface, str(backup / "live-peer.conf"))
                    else:
                        wg("set", self.interface, "peer", pub, "remove")
                except Exception:
                    raise ProvisionError("Rollback needs operator recovery; root-only backup: "
                                         + str(backup)) from None
            raise ProvisionError("Peer change failed; previous state restored; backup: "
                                 + str(backup)) from None
        return str(backup)

    def add(self, request, requested=None):
        validate_request(request)
        peer_name, pub = request["hostname"], request["public_key"]
        with self.locked():
            before, file_peers, live, records = self.inventory()
            if peer_name in records or pub in file_peers or pub in live or any(
                r["public_key"] == pub or r["device_id"] == request["device_id"] or
                r["request_id"] == request["request_id"] for r in records.values()
            ):
                raise ProvisionError("Duplicate name, device, public key or registration request")
            address = self.allocate(file_peers, live, records, requested)
            metadata = self.metadata(request, address)
            after = before.rstrip() + (f"\n\n[Peer]\n# KDX InfraBox {peer_name}\n"
                                       f"PublicKey = {pub}\nAllowedIPs = {address}\n")
            self.transaction(before, after, records, {**records, peer_name: metadata},
                             pub, address, live)
            return metadata

    def remove(self, peer_name):
        name(peer_name)
        with self.locked():
            before, file_peers, live, records = self.inventory()
            if peer_name not in records:
                raise ProvisionError("Only peers registered by this tool can be removed")
            record = records[peer_name]
            pub = record["public_key"]
            expected = [ipaddress.ip_network(record["address"])]
            if file_peers.get(pub) != expected or (pub in live and live[pub] != expected):
                raise ProvisionError("Peer changed outside provisioning; reconcile before removal")
            after = "".join(b for b in blocks(before)
                            if fields(b).get("publickey") != [pub])
            new_records = {k: v for k, v in records.items() if k != peer_name}
            backup = self.transaction(before, after, records, new_records, pub, None, live)
            return {"removed": peer_name, "backup": backup}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["add", "remove", "list", "status", "export"])
    parser.add_argument("name", nargs="?")
    parser.add_argument("--request", type=Path, help="Public device registration JSON")
    parser.add_argument("--ip")
    parser.add_argument("--endpoint")
    parser.add_argument("--interface", default="wg0")
    parser.add_argument("--config", default="/etc/wireguard/wg0.conf")
    parser.add_argument("--registry", default="/etc/wireguard/kdx-peers.json")
    parser.add_argument("--network", default="10.77.0.0/24")
    parser.add_argument("--pool-start", default="10.77.0.11")
    parser.add_argument("--pool-end", default="10.77.0.254")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Run locally as root on the approved VPN server")
    os.umask(0o077)
    try:
        server = Server(args.config, args.registry, args.interface, args.network,
                        args.pool_start, args.pool_end, args.endpoint)
        if args.command == "add":
            if not args.request or args.request.stat().st_size > 4096:
                raise ProvisionError("Specify --request with public registration JSON under 4 KiB")
            result = server.add(json.loads(args.request.read_text()), args.ip)
        elif args.command == "remove":
            result = server.remove(args.name or "")
        else:
            with server.locked():
                records = server.records()
                if args.command == "export":
                    if args.name not in records:
                        raise ProvisionError("Unknown registered peer")
                    result = records[args.name]
                elif args.command == "list":
                    result = list(records.values())
                else:
                    result = {"interface": args.interface, "peers": server.runtime(),
                              "handshakes": wg("show", args.interface, "latest-handshakes"),
                              "transfer": wg("show", args.interface, "transfer")}
        print(json.dumps(result, indent=2, default=str))
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as error:
        # Input and subprocess exception strings can contain secrets from malformed input.
        print(str(error) if isinstance(error, ProvisionError) else
              "Provisioning failed; inspect local configuration and public input", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
