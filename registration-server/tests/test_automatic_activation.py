from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import ActivationToken, Device, License, LicenseBinding, now
from simulator.device import authenticate
from test_registration import active, enroll, env, proof, provision, virtual


def automatic_approval(env, request, device, license_id):
    return env[0].post(
        f'/api/v1/admin/devices/{device}/approve', headers=env[2],
        json={'installation_id': request['installation_id'], 'public_key': request['public_key'],
              'license_id': license_id, 'reason': 'Verified device identity and customer',
              'automatic_activation': True},
    )


def setup_approval(env):
    identity, key = virtual()
    device = enroll(env, identity)
    manual_token, license_id = provision(env, identity, device)
    response = automatic_approval(env, identity, device, license_id)
    assert response.status_code == 200, response.text
    assert response.json()['automatic_activation'] is True
    assert 'activation_token' not in response.json()
    return identity, key, device, license_id, manual_token


def test_explicit_automatic_approval_activates_only_on_signed_device_sync(env):
    identity, key, device, license_id, _ = setup_approval(env)
    with env[1].state.sessions() as db:
        assert db.get(Device, device).status == 'ACTIVATION_REQUIRED'
        assert db.get(LicenseBinding, device) is None
    result = authenticate(env[0], identity, key)
    assert result['status'] == 'ACTIVE' and 'authorization' in result
    assert authenticate(env[0], identity, key)['status'] == 'ACTIVE'
    with env[1].state.sessions() as db:
        assert db.get(LicenseBinding, device).license_id == license_id
        assert db.scalar(select(ActivationToken).where(
            ActivationToken.automatic_activation.is_(True))).used_at


def test_automatic_approval_cannot_be_consumed_by_bad_signature_or_other_installation(env):
    identity, key, device, _, _ = setup_approval(env)
    payload = proof(env, identity, key)
    payload['signature'] = 'A' * 86 + '=='
    assert env[0].post('/api/v1/devices/verify', json=payload).status_code == 401
    other, other_key = virtual(identity['serial'])
    assert enroll(env, other) == device
    assert authenticate(env[0], other, other_key)['status'] == 'PENDING'
    assert authenticate(env[0], identity, key)['status'] == 'ACTIVE'


@pytest.mark.parametrize('failure', ['expired_approval', 'suspended_device', 'expired_license', 'capacity'])
def test_activation_rechecks_current_authorization(env, failure):
    identity, key, device, license_id, _ = setup_approval(env)
    with env[1].state.sessions.begin() as db:
        if failure == 'expired_approval':
            db.scalar(select(ActivationToken).where(
                ActivationToken.automatic_activation.is_(True))).expires_at = now() - timedelta(seconds=1)
        elif failure == 'suspended_device':
            db.get(Device, device).status = 'SUSPENDED'
        elif failure == 'expired_license':
            lic = db.get(License, license_id)
            lic.kind = 'DEMO'; lic.expires_at = now() - timedelta(seconds=1)
        else:
            # Another device can occupy the last slot after approval but before sync.
            other = Device(serial='10000000ABC12346', model='Test', firmware='test')
            db.add(other); db.flush()
            db.add(LicenseBinding(device_id=other.id, license_id=license_id))
    response = env[0].post('/api/v1/devices/verify', json=proof(env, identity, key))
    if failure == 'expired_approval':
        assert response.status_code == 200 and response.json()['status'] == 'PENDING'
    else:
        assert response.status_code in (403, 409)
    with env[1].state.sessions() as db:
        assert db.get(LicenseBinding, device) is None


def test_automatic_approval_refuses_full_license_before_issuing_grant(env):
    _, _, _, license_id, _ = active(env)
    identity, _ = virtual('10000000ABC12346')
    device = enroll(env, identity)
    response = automatic_approval(env, identity, device, license_id)
    assert response.status_code == 409 and 'capacity' in response.json()['detail'].lower()
    with env[1].state.sessions() as db:
        assert db.scalar(select(ActivationToken).where(ActivationToken.device_id == device)) is None


def test_new_approval_retires_previous_manual_token(env):
    identity, key, _, _, token = setup_approval(env)
    response = env[0].post('/api/v1/devices/activate', json={
        **proof(env, identity, key, 'activate'), 'activation_token': token,
    })
    assert response.status_code == 401
    assert authenticate(env[0], identity, key)['status'] == 'ACTIVE'
