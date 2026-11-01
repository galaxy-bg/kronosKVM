import base64
import json
import uuid

import pytest
from test_registration import env, enroll, virtual
from app.models import Administrator, now
from app.crypto import digest
from datetime import timedelta

WG_KEY = base64.b64encode(b'w'*32).decode()
SERVER_KEY = base64.b64encode(b's'*32).decode()


class FakeController:
    def __init__(self):
        self.calls = []
        self.fail = False
        self.missing = False
        self.allocated = False

    def apply(self, action, request):
        self.calls.append((action,request))
        if self.fail:
            raise ValueError('Connection unavailable')
        if action == 'inspect': return {'status':'MISSING' if self.missing or not self.allocated else 'PRESENT'}
        if action in {'approve','resume'}: self.allocated = True
        if action == 'delete': self.allocated = False
        return {'status':{'delete':'DELETED','approve':'ACTIVE','resume':'ACTIVE','suspend':'SUSPENDED','archive':'ARCHIVED'}[action],
            'registration':{**request,'address':'10.77.0.11/32','endpoint':'vpn.example.com:51820',
                'server_public_key':SERVER_KEY,'allowed_ips':'10.77.0.0/24','keepalive':25}}


def pending(env):
    identity, key = virtual()
    device = enroll(env, identity)
    request = {'version':1,'device_id':identity['serial'].lower(),'hostname':'infrabox-test',
        'public_key':WG_KEY,'request_id':str(uuid.uuid4())}
    env[1].state.vpn_controller = FakeController()
    return identity,key,device,request


def proof(env, identity, key, request, operation="sync"):
    response = env[0].post('/api/v1/devices/challenge',json={**identity,'purpose':'vpn','vpn_request':request,'vpn_operation':operation})
    assert response.status_code == 200, response.text
    challenge = response.json()
    return {'challenge_id':challenge['challenge_id'],
        'signature':base64.b64encode(key.sign(challenge['message'].encode())).decode(),'request':request,'operation':operation}


def test_pending_unlicensed_device_requires_separate_vpn_approval(env):
    client, app, headers, _ = env
    identity,key,device,request = pending(env)
    response = client.post('/api/v1/devices/vpn',json=proof(env,identity,key,request))
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'PENDING' and 'document' not in response.json()
    ident = response.json()['id']
    assert all(action == "inspect" for action,_ in app.state.vpn_controller.calls)
    assert client.get('/api/v1/admin/vpn',headers=headers).json()[0]['device_id'] == device
    for action,state in [('approve','ACTIVE'),('suspend','SUSPENDED'),('resume','ACTIVE'),('delete','DELETED')]:
        result = client.post(f'/api/v1/admin/vpn/{ident}/{action}',headers=headers,json={'reason':'Explicit operator approval'})
        assert result.status_code == 200, result.text
        assert result.json()['status'] == state
        status = client.post('/api/v1/devices/vpn',json=proof(env,identity,key,request)).json()
        assert status['status'] == state
        assert ('document' in status) == (state in {'ACTIVE','DELETED'})
    assert client.post(f'/api/v1/admin/vpn/{ident}/resume',headers=headers,json={'reason':'Try to restore archived'}).status_code == 409


def test_proof_binds_exact_wg_request_and_prevents_replay_and_key_replacement(env):
    identity,key,_,request = pending(env)
    payload = proof(env,identity,key,request)
    altered = {**payload,'request':{**request,'public_key':SERVER_KEY}}
    assert env[0].post('/api/v1/devices/vpn',json=altered).status_code == 401
    assert env[0].post('/api/v1/devices/vpn',json=payload).status_code == 401
    response = env[0].post('/api/v1/devices/vpn',json=proof(env,identity,key,request))
    assert response.status_code == 200
    assert env[0].post('/api/v1/devices/vpn',json=proof(env,identity,key,{**request,'public_key':SERVER_KEY})).status_code == 409
    challenge = env[0].post('/api/v1/devices/challenge',json=identity).json()
    wrong = {'challenge_id':challenge['challenge_id'],'signature':base64.b64encode(key.sign(challenge['message'].encode())).decode(),'request':request}
    assert env[0].post('/api/v1/devices/vpn',json=wrong).status_code == 401


def test_failed_remote_operation_does_not_report_granted_and_viewer_cannot_mutate(env):
    identity,key,_,request = pending(env)
    ident = env[0].post('/api/v1/devices/vpn',json=proof(env,identity,key,request)).json()['id']
    controller = env[1].state.vpn_controller
    controller.fail = True
    assert env[0].post(f'/api/v1/admin/vpn/{ident}/approve',headers=env[2],json={'reason':'Approve test request'}).status_code == 503
    assert env[0].get('/api/v1/admin/vpn',headers=env[2]).json()[0]['status'] == 'PENDING'
    with env[1].state.sessions.begin() as db:
        db.add(Administrator(name='viewer',token_hash=digest('v'*40),role='viewer',expires_at=now()+timedelta(days=1)))
    viewer={'Authorization':'Bearer '+'v'*40}
    assert env[0].get('/api/v1/admin/vpn',headers=viewer).status_code == 200
    assert env[0].post(f'/api/v1/admin/vpn/{ident}/approve',headers=viewer,json={'reason':'Attempt viewer mutation'}).status_code == 403
    assert controller.calls[-1][0] == "approve"


def test_device_delete_and_fresh_generation_never_restore_old_key(env):
    client,app,headers,_=env
    identity,key,device,request=pending(env)
    ident=client.post('/api/v1/devices/vpn',json=proof(env,identity,key,request)).json()['id']
    assert client.post(f'/api/v1/admin/vpn/{ident}/approve',headers=headers,json={'reason':'Approve initial key'}).status_code==200
    payload=proof(env,identity,key,request)
    assert client.post('/api/v1/devices/vpn',json={**payload,'operation':'delete'}).status_code==401
    response=client.post('/api/v1/devices/vpn',json=proof(env,identity,key,request,'delete'))
    assert response.status_code==200,response.text
    assert response.json()['status']=='DELETED'
    assert client.get('/api/v1/admin/vpn',headers=headers).json()==[]
    new={**request,'public_key':base64.b64encode(b'n'*32).decode(),'request_id':str(uuid.uuid4())}
    assert client.post('/api/v1/devices/vpn',json=proof(env,identity,key,{**request,'request_id':str(uuid.uuid4())})).status_code==409
    created=client.post('/api/v1/devices/vpn',json=proof(env,identity,key,new))
    assert created.status_code==200,created.text
    assert created.json()['status']=='PENDING'
    assert client.post(f'/api/v1/admin/vpn/{ident}/approve',headers=headers,json={'reason':'Approve fresh key'}).status_code==200
    before=len(app.state.vpn_controller.calls)
    for operation in ['sync','delete']:
        assert client.post('/api/v1/devices/vpn',json=proof(env,identity,key,request,operation)).json()['status']=='DELETED'
    assert len(app.state.vpn_controller.calls)==before
    active=client.get('/api/v1/admin/vpn',headers=headers).json()[0]
    assert active['status']=='ACTIVE' and active['public_key']==new['public_key']


def test_server_removal_is_propagated_and_unconfirmed_delete_is_retryable(env):
    client,app,headers,_=env
    identity,key,_,request=pending(env)
    ident=client.post('/api/v1/devices/vpn',json=proof(env,identity,key,request)).json()['id']
    assert client.post(f'/api/v1/admin/vpn/{ident}/approve',headers=headers,json={'reason':'Approve initial key'}).status_code==200
    controller=app.state.vpn_controller
    controller.fail=True
    assert client.post('/api/v1/devices/vpn',json=proof(env,identity,key,request,'delete')).status_code==503
    assert client.get('/api/v1/admin/vpn',headers=headers).json()[0]['status']=='ACTIVE'
    controller.fail=False;controller.missing=True
    result=client.post('/api/v1/devices/vpn',json=proof(env,identity,key,request))
    assert result.status_code==200 and result.json()['status']=='DELETED'
    assert controller.calls[-2][0]=='inspect' and controller.calls[-1][0]=='delete'
    assert client.get('/api/v1/admin/vpn',headers=headers).json()==[]
