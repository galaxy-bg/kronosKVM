import asyncio
import base64
import importlib.util
import ipaddress
import json
import time
import uuid
from contextlib import nullcontext
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

from backend.app.api import remote_assist
from backend.app.main import create_app
from backend.app.services import wireguard_quick as quick
from backend.app.services.remote_assist_config import ProfileError


@pytest.fixture
def reply():
    def key(n):
        return base64.b64encode(bytes([n]) * 32).decode()
    return {'version': 1, 'device_id': '100000001234abcd', 'hostname': 'infrabox-1234abcd',
            'public_key': key(1), 'request_id': str(uuid.uuid4()), 'address': '10.77.0.11/32',
            'server_public_key': key(2), 'endpoint': 'vpn.example.com:51820',
            'allowed_ips': '10.77.0.0/24', 'keepalive': 25}


def public(reply):
    return {k: reply[k] for k in ('version', 'device_id', 'hostname', 'public_key', 'request_id')}


@pytest.mark.parametrize('value', [{'host':'host;id'}, {'host':'host', 'port':True}, []])
def test_target_rejects_commands_and_invalid_ports(value):
    with pytest.raises(ProfileError):
        quick.target(value)


def test_changed_host_key_prevents_password_authentication(reply, monkeypatch):
    monkeypatch.setattr(quick, 'server_key', AsyncMock(return_value=Mock(
        get_fingerprint=lambda: 'SHA256:NEW')))
    connect = Mock()
    monkeypatch.setattr(quick.asyncssh, 'connect', connect)
    with pytest.raises(ProfileError, match='identity changed'):
        asyncio.run(quick.register({'host':'vpn.example.com', 'username':'root',
                                   'password':'PRIVATE-ONE-TIME',
                                   'fingerprint':'SHA256:OLD'}, public(reply)))
    connect.assert_not_called()


def test_api_queues_only_public_reply_and_never_password(tmp_path, monkeypatch, reply):
    monkeypatch.setattr(remote_assist, 'STATE', tmp_path)
    (tmp_path/'remote-assist-status.json').write_text(json.dumps({
        'installed':True, 'updated_at':time.time(), 'enrollment':public(reply), 'enabled':False,
    }))
    register = AsyncMock(return_value=reply)
    monkeypatch.setattr(quick, 'register', register)
    client = TestClient(create_app())
    response = client.post('/api/v1/wireguard/quick-register', json={
        'host':'vpn.example.com', 'username':'root', 'password':'PRIVATE-ONE-TIME',
        'fingerprint':'SHA256:TEST',
    })
    assert response.status_code == 202
    queued = (tmp_path/'remote-assist-request.json').read_text()
    assert 'PRIVATE-ONE-TIME' not in queued + response.text
    assert json.loads(queued)['action'] == 'register-connect'
    assert json.loads(queued)['registration'] == reply
    assert register.await_args.args[0] == {}  # Credential dictionary cleared after use.


def test_server_reuses_exact_existing_peer_but_rejects_changed_key(tmp_path, monkeypatch, reply):
    spec = importlib.util.spec_from_file_location('quick_server', 'scripts/kdx-wg-register.py')
    wrapper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wrapper)
    monkeypatch.setattr(wrapper, 'SETTINGS', tmp_path/'settings.json')
    expected = [ipaddress.ip_network(reply['address'])]
    manager = Mock()
    manager.locked.side_effect = lambda: nullcontext()
    manager.inventory.return_value = ('', {reply['public_key']:expected},
                                     {reply['public_key']:expected}, {reply['hostname']:reply})
    monkeypatch.setattr(wrapper.server, 'Server', lambda *a: manager)
    assert wrapper.register({'request':public(reply), 'endpoint':''}) == reply
    manager.add.assert_not_called()
    request = {**public(reply), 'request_id':str(uuid.uuid4())}
    with pytest.raises(wrapper.server.ProvisionError, match='differs'):
        wrapper.register({'request':request, 'endpoint':''})
    manager.inventory.return_value = ('', {}, {}, {reply['hostname']:reply})
    with pytest.raises(wrapper.server.ProvisionError, match='peer differs'):
        wrapper.register({'request':public(reply), 'endpoint':''})


def test_password_setup_over_real_ssh_with_pinned_host_key(reply):
    import asyncssh

    class Login(asyncssh.SSHServer):
        def begin_auth(self, username):
            return True

        def password_auth_supported(self):
            return True

        def validate_password(self, username, password):
            return username == 'root' and password == 'EPHEMERAL-TEST-PASSWORD'

    async def scenario():
        seen = []

        async def handle(process):
            seen.append((process.command, json.loads(await process.stdin.read())))
            process.stdout.write(json.dumps(reply))
            process.exit(0)

        async with await asyncssh.create_server(
            Login, '127.0.0.1', 0, server_host_keys=[asyncssh.generate_private_key('ssh-ed25519')],
            process_factory=handle,
        ) as listener:
            value = {'host':'127.0.0.1', 'port':listener.get_port(), 'username':'root',
                     'password':'EPHEMERAL-TEST-PASSWORD'}
            value['fingerprint'] = (await quick.server_key(value)).get_fingerprint()
            assert await quick.register(value, public(reply)) == reply
        assert seen == [(quick.COMMAND, {'request':public(reply), 'endpoint':''})]
        assert 'EPHEMERAL-TEST-PASSWORD' not in json.dumps(seen)

    asyncio.run(scenario())
