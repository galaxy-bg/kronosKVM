import importlib.util
import json
import sys
from pathlib import Path

import pytest

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "registration-server"))
sys.path.insert(0, str(root / "registration-server/tests"))
from test_registration import provision, env  # noqa: E402,F401

pytest_plugins = ["test_registration"]

spec = importlib.util.spec_from_file_location(
    "device_registration_client", root / "device-registration/client.py"
)
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


class API:
    def __init__(self, env):
        self.client = env[0]
        self.payloads = []

    def post(self, path, value):
        self.payloads.append((path, value))
        response = self.client.post(path, json=value)
        if response.status_code >= 400:
            detail = response.json().get("detail")
            raise agent.Denied(detail if isinstance(detail, str) else "SERVER_REJECTED_REQUEST")
        return response.json()


class Offline:
    def post(self, path, value):
        raise agent.Unavailable()


@pytest.fixture
def setup(env, tmp_path, monkeypatch):
    import base64

    from cryptography.hazmat.primitives import serialization

    monkeypatch.setattr(agent, "read_serial", lambda: "10000000000865DD")
    public = base64.b64encode(
        env[3].public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    ).decode()
    config = {
        "server_url": "http://registration.test",
        "server_public_key": public,
        "allow_lab_http": True,
    }
    return env, tmp_path, config, API(env)


def activate(setup):
    env, directory, config, api = setup
    first = agent.synchronize(config, directory, api)
    request, _ = agent.identity(directory)
    token, _ = provision(env, request, first["device_id"], kind="DEMO")
    result = agent.synchronize(config, directory, api, token)
    assert result["status"] == "ACTIVE" and result["authorized"]
    return result


def test_first_boot_pending_and_private_material_not_transmitted(setup):
    env, directory, config, api = setup
    result = agent.synchronize(config, directory, api)
    assert result["status"] == "PENDING" and not result["authorized"]
    private = json.loads((directory / "identity.json").read_text())["private_key"]
    assert private not in json.dumps(api.payloads)
    assert private not in (directory / "status.json").read_text()
    assert (directory / "identity.json").stat().st_mode & 0o777 == 0o600
    assert directory.stat().st_mode & 0o777 == 0o700


def test_restart_retains_identity_and_authenticates(setup):
    _, directory, config, api = setup
    result = activate(setup)
    before = (directory / "identity.json").read_bytes()
    second = agent.synchronize(config, directory, api)
    assert second["status"] == "ACTIVE" and second["device_id"] == result["device_id"]
    assert before == (directory / "identity.json").read_bytes()
    assert "session_token" not in (directory / "status.json").read_text()


def test_unavailable_fresh_device_fails_closed(setup):
    _, directory, config, _ = setup
    status = agent.synchronize(config, directory, Offline())
    assert status["status"] == "UNAVAILABLE" and not status["authorized"]


def test_offline_grace_then_expiration(setup, monkeypatch):
    _, directory, config, _ = setup
    active = activate(setup)
    result = agent.synchronize(config, directory, Offline())
    assert result["authorized"] and result["mode"] == "offline-grace"
    monkeypatch.setattr(agent.time, "time", lambda: active["authorization_expires_at"] + 1)
    result = agent.synchronize(config, directory, Offline())
    assert not result["authorized"] and result["status"] == "UNAVAILABLE"


def test_hardware_clone_rejected_online_and_offline(setup, monkeypatch):
    _, directory, config, api = setup
    activate(setup)
    monkeypatch.setattr(agent, "read_serial", lambda: "10000000DEF67890")
    result = agent.synchronize(config, directory, Offline())
    assert not result["authorized"]
    result = agent.synchronize(config, directory, api)
    assert result["status"] == "HARDWARE_MISMATCH" and not result["authorized"]
    assert json.loads((directory / "authorization.json").read_text())["denied"]


def test_revocation_prevents_later_offline_grace(setup):
    env, directory, config, api = setup
    active = activate(setup)
    response = env[0].post(
        "/api/v1/admin/devices/" + active["device_id"] + "/revoke",
        headers=env[2],
        json={"reason": "Device revoked for integration test"},
    )
    assert response.status_code == 200
    result = agent.synchronize(config, directory, api)
    assert result["status"] == "REVOKED" and not result["authorized"]
    result = agent.synchronize(config, directory, Offline())
    assert result["status"] == "UNAVAILABLE" and not result["authorized"]


def test_wrong_server_signing_key_invalidates_cache(setup):
    import base64

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    _, directory, config, api = setup
    activate(setup)
    config["server_public_key"] = base64.b64encode(
        Ed25519PrivateKey.generate()
        .public_key()
        .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    ).decode()
    result = agent.synchronize(config, directory, api)
    assert result["status"] == "DENIED" and not result["authorized"]
    result = agent.synchronize(config, directory, Offline())
    assert not result["authorized"]


def test_transport_requires_explicit_lab_http_and_refuses_url_credentials():
    with pytest.raises(agent.Denied, match="HTTPS_REQUIRED"):
        agent.Transport({"server_url": "http://registration.test"})
    with pytest.raises(agent.Denied, match="INVALID_SERVER_URL"):
        agent.Transport({"server_url": "https://user:password@registration.test"})


def test_malicious_challenge_is_not_signed(setup):
    _, directory, _, _ = setup
    request, key = agent.identity(directory)

    class WrongServer:
        def post(self, path, value):
            assert path.endswith("/challenge")
            return {"challenge_id": "fake", "message": json.dumps({"aud": "other-server"})}

    with pytest.raises(agent.Denied, match="INVALID_SERVER_CHALLENGE"):
        agent.prove(WrongServer(), request, key)


def test_small_clock_skew_only_applies_to_issue_time(setup):
    import base64

    env, directory, config, _ = setup
    active = activate(setup)
    request, _ = agent.identity(directory)
    document = json.loads((directory / "authorization.json").read_text())["document"]
    tick = int(agent.time.time())
    document["payload"]["issued_at"] = tick + 16
    document["payload"]["expires_at"] = tick + 86416
    document["signature"] = base64.b64encode(
        env[3].sign(agent.canonical(document["payload"]).encode())
    ).decode()
    assert (
        agent.verify_document(
            document, config["server_public_key"], request, active["device_id"], clock=tick
        )["status"]
        == "ACTIVE"
    )
    with pytest.raises(agent.Denied):
        agent.verify_document(
            document, config["server_public_key"], request, active["device_id"], clock=tick - 15
        )
    with pytest.raises(agent.Denied):
        agent.verify_document(
            document, config["server_public_key"], request, active["device_id"], clock=tick + 86416
        )


def test_public_snapshot_never_contains_identity_secrets(setup, tmp_path):
    _, directory, config, api = setup
    config["public_status_directory"] = str(tmp_path / "public")
    result = activate(setup)
    value = json.loads((tmp_path / "public/status.json").read_text())
    assert value["device_id"] == result["device_id"] and value["authorized"]
    assert value["transport"] == "lab-http"
    for field in (
        "private_key",
        "public_key",
        "activation_token",
        "session_token",
        "authorization",
    ):
        assert field not in value
    assert (tmp_path / "public/status.json").stat().st_mode & 0o777 == 0o644
    assert (directory / "identity.json").stat().st_mode & 0o777 == 0o600


@pytest.fixture
def tls_server(tmp_path):
    import datetime
    import hashlib
    import ipaddress
    import ssl
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    now = datetime.datetime.now(datetime.timezone.utc)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Ephemeral registration test CA")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=2))
        .add_extension(x509.BasicConstraints(ca=True, path_length=1), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=False,
                content_commitment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), False)
        .sign(ca_key, hashes.SHA256())
    )
    key = ec.generate_private_key(ec.SECP256R1())
    leaf = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")]))
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), False
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), False
        )
        .sign(ca_key, hashes.SHA256())
    )
    ca_path = tmp_path / "ca.crt"
    ca_path.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    cert = tmp_path / "server.crt"
    cert.write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    private = tmp_path / "server.key"
    private.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, private)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config = {
        "server_url": f"https://127.0.0.1:{server.server_port}",
        "ca_bundle": str(ca_path),
        "ca_certificate_sha256": hashlib.sha256(
            ca.public_bytes(serialization.Encoding.DER)
        ).hexdigest(),
    }
    try:
        yield config
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_trusted_tls_validates_ca_and_ip_identity(tls_server):
    config = tls_server
    assert agent.Transport(config).post("/health", {}) == {"ok": True}
    with pytest.raises(agent.Denied, match="TLS_VALIDATION_FAILED"):
        agent.Transport({"server_url": config["server_url"]}).post("/health", {})
    with pytest.raises(agent.Denied, match="TLS_VALIDATION_FAILED"):
        agent.Transport(config, url=config["server_url"].replace("127.0.0.1", "localhost")).post(
            "/health", {}
        )
    with pytest.raises(agent.Denied, match="TLS_TRUST_ANCHOR_MISMATCH"):
        agent.Transport({**config, "ca_certificate_sha256": "0" * 64})


def test_invalid_tls_never_uses_previous_offline_cache(setup, tls_server):
    _, directory, config, _ = setup
    activate(setup)
    failed = {**config, "server_url": tls_server["server_url"]}
    result = agent.synchronize(failed, directory)
    assert result["status"] == "DENIED" and not result["authorized"]
    assert result["error"] == "TLS_VALIDATION_FAILED"
    assert json.loads((directory / "authorization.json").read_text())["denied"]


def test_public_snapshot_readable_with_restrictive_service_umask(tmp_path):
    import os

    previous = os.umask(0o077)
    try:
        agent.atomic_json(tmp_path / "public.json", {"status": "PENDING"}, mode=0o644)
        agent.atomic_json(tmp_path / "private.json", {"private_key": "fixture"})
    finally:
        os.umask(previous)
    assert (tmp_path / "public.json").stat().st_mode & 0o777 == 0o644
    assert (tmp_path / "private.json").stat().st_mode & 0o777 == 0o600


def test_vpn_request_uses_device_signature_without_license_or_ssh_password(setup):
    import base64
    import uuid
    from test_vpn_enrollment import FakeController
    env, directory, config, api = setup
    env[1].state.vpn_controller = FakeController()
    request = {"version":1,"device_id":"10000000000865dd","hostname":"infrabox-test",
        "public_key":base64.b64encode(b"w"*32).decode(),"request_id":str(uuid.uuid4())}
    result = agent.vpn_sync(config,directory,request,api)
    assert result["status"] == "PENDING" and "document" not in result
    assert all("password" not in json.dumps(x) and "private_key" not in json.dumps(x) for x in api.payloads)
    response = env[0].post('/api/v1/admin/vpn/'+result['id']+'/approve',headers=env[2],json={"reason":"Approve key request"})
    assert response.status_code == 200, response.text
    result = agent.vpn_sync(config,directory,request,api)
    registration = agent.verify_vpn_document(result['document'],config['server_public_key'],request)
    assert registration['public_key'] == request['public_key']
    with pytest.raises(agent.Denied):
        agent.verify_vpn_document(result['document'],config['server_public_key'],{**request,'hostname':'other'})
    altered = json.loads(json.dumps(result['document']))
    altered['payload']['registration']['endpoint']='attacker.test:51820'
    from cryptography.exceptions import InvalidSignature
    with pytest.raises(InvalidSignature):
        agent.verify_vpn_document(altered,config['server_public_key'],request)


def test_signed_deletion_is_bound_to_exact_vpn_generation(setup):
    import base64,uuid
    from test_vpn_enrollment import FakeController
    env,directory,config,api=setup
    env[1].state.vpn_controller=FakeController()
    request={"version":1,"device_id":"10000000000865dd","hostname":"infrabox-test",
        "public_key":base64.b64encode(b"w"*32).decode(),"request_id":str(uuid.uuid4())}
    agent.vpn_sync(config,directory,request,api)
    deleted=agent.vpn_sync(config,directory,request,api,operation="delete")
    assert agent.verify_vpn_deletion(deleted['document'],config['server_public_key'],request)['status']=='DELETED'
    with pytest.raises(agent.Denied):
        agent.verify_vpn_deletion(deleted['document'],config['server_public_key'],{**request,'request_id':str(uuid.uuid4())})
    altered=json.loads(json.dumps(deleted['document']));altered['payload']['request']['hostname']='other'
    from cryptography.exceptions import InvalidSignature
    with pytest.raises(InvalidSignature):
        agent.verify_vpn_deletion(altered,config['server_public_key'],request)
