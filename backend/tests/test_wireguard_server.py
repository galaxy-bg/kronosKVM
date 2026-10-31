import base64
import importlib.util
import ipaddress
import json
import stat
import uuid
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("wg_server", Path("scripts/kdx-wg-server.py"))
server_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server_module)
Server, Error = server_module.Server, server_module.ProvisionError


def key(byte):
    return base64.b64encode(bytes([byte]) * 32).decode()


@pytest.fixture
def setup(tmp_path, monkeypatch):
    config = tmp_path / "wg0.conf"
    text = ("[Interface]\nPrivateKey = SERVER-SECRET\nAddress = 10.77.0.1/24\n"
            "ListenPort = 51820\n\n[Peer]\nPublicKey = " + key(1)
            + "\nAllowedIPs = 10.77.0.2/32\n\n[Peer]\nPublicKey = " + key(2)
            + "\nAllowedIPs = 10.77.0.10/32\n")
    config.write_text(text)
    runtime = {key(1): "10.77.0.2/32", key(2): "10.77.0.10/32"}
    calls = []
    fail = [False]

    def wg(*args):
        calls.append(args)
        if args[:3] == ("show", "wg0", "allowed-ips"):
            return "\n".join(k + "\t" + v for k, v in runtime.items())
        if args[:3] == ("show", "wg0", "public-key"):
            return key(9)
        if args[:2] == ("showconf", "wg0"):
            return "[Interface]\nPrivateKey = SERVER-SECRET\n" + "".join(
                "\n[Peer]\nPublicKey = " + k + "\nAllowedIPs = " + v + "\n"
                for k, v in runtime.items())
        if args[0] == "set":
            if fail[0]:
                fail[0] = False
                raise Error("mock command failure")
            if args[-1] == "remove":
                runtime.pop(args[3], None)
            else:
                runtime[args[3]] = args[-1]
        return ""

    monkeypatch.setattr(server_module, "wg", wg)
    server = Server(config, tmp_path / "registry.json", endpoint="vpn.example.com:51820")
    request = {"version": 1, "device_id": "10000000000865dd", "hostname": "infrabox-000865dd",
               "public_key": key(3), "request_id": str(uuid.uuid4())}
    return server, request, runtime, calls, fail, text


def test_add_allocates_first_free_ip_and_preserves_unmanaged_peers(setup):
    server, request, runtime, calls, _, original = setup
    metadata = server.add(request)
    assert metadata["address"] == "10.77.0.11/32"
    assert metadata["allowed_ips"] == "10.77.0.0/24"
    assert runtime[key(1)] == "10.77.0.2/32" and runtime[key(2)] == "10.77.0.10/32"
    assert server.config.read_text().startswith(original.rstrip())
    assert "SECRET" not in json.dumps(metadata)
    assert "private_key" not in metadata
    assert all(c[0] != "setconf" and c[0] != "syncconf" for c in calls)
    assert stat.S_IMODE(server.registry.stat().st_mode) == 0o600
    backups = list((server.config.parent / "kdx-backups").glob("peer-*"))
    assert (backups[0] / "interface.conf").read_text() == original
    assert stat.S_IMODE((backups[0] / "interface.conf").stat().st_mode) == 0o600


def test_duplicate_name_key_serial_and_request_are_rejected(setup):
    server, request, _, _, _, _ = setup
    server.add(request)
    for override in ({}, {"hostname": "other"}, {"public_key": key(4)},
                     {"public_key": key(4), "hostname": "other"}):
        with pytest.raises(Error, match="Duplicate"):
            server.add({**request, **override})


def test_allocation_reserves_file_live_registry_and_interface_addresses(setup):
    server, request, runtime, _, _, _ = setup
    runtime[key(5)] = "10.77.0.11/32"
    file = server.config.read_text().replace("Address = 10.77.0.1/24",
                                          "Address = 10.77.0.1/24, 10.77.0.12/32")
    server.config.write_text(file)
    assert server.add(request)["address"] == "10.77.0.13/32"


def test_pool_exhaustion_and_duplicate_requested_ip_do_not_write(setup):
    server, request, runtime, _, _, original = setup
    runtime[key(5)] = "10.77.0.11/32"
    server.end = ipaddress.IPv4Address("10.77.0.11")
    with pytest.raises(Error, match="exhausted"):
        server.add(request)
    with pytest.raises(Error, match="outside"):
        server.add(request, "10.77.0.2")
    assert server.config.read_text() == original
    assert not server.registry.exists()


def test_saveconfig_true_is_rejected_before_any_modification(setup):
    server, request, _, calls, _, original = setup
    configured = original.replace("ListenPort = 51820", "ListenPort = 51820\nSaveConfig = true")
    server.config.write_text(configured)
    with pytest.raises(Error, match="SaveConfig=true"):
        server.add(request)
    assert server.config.read_text() == configured
    assert not any(c[0] == "set" for c in calls)


def test_add_failure_rolls_back_files_registry_and_target_peer(setup):
    server, request, runtime, _, fail, original = setup
    fail[0] = True
    with pytest.raises(Error, match="previous state restored"):
        server.add(request)
    assert server.config.read_text() == original
    assert not server.registry.exists()
    assert request["public_key"] not in runtime
    assert set(runtime) == {key(1), key(2)}


def test_remove_rejects_unmanaged_and_external_edits(setup):
    server, request, runtime, _, _, _ = setup
    with pytest.raises(Error, match="Only peers"):
        server.remove("existing-peer")
    server.add(request)
    runtime[request["public_key"]] = "10.77.0.12/32"
    with pytest.raises(Error, match="changed outside"):
        server.remove(request["hostname"])


def test_remove_only_changes_registered_peer(setup):
    server, request, runtime, _, _, original = setup
    server.add(request)
    server.remove(request["hostname"])
    assert set(runtime) == {key(1), key(2)}
    assert server.config.read_text().strip() == original.strip()
    assert server.records() == {}


def test_mutations_are_locked(setup):
    server, request, _, _, _, _ = setup
    with server.locked():
        with pytest.raises(Error, match="Another provisioning"):
            server.add(request)


@pytest.mark.parametrize("value", ["bad", "a" * 44, key(0), "$(touch /tmp/oops)"])
def test_invalid_keys_are_rejected(value):
    with pytest.raises(Error):
        server_module.public_key(value)
