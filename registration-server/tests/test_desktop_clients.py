import base64,json,secrets,uuid
from datetime import timedelta
from test_registration import env
from app.crypto import digest
from app.models import Administrator,VpnClient,now

KEY=base64.b64encode(b'p'*32).decode()
SERVER=base64.b64encode(b's'*32).decode()


class DesktopController:
    def __init__(self):self.calls=[];self.records={};self.fail=False
    def apply(self,action,request):
        assert request['version']==2 and 'device_id' not in request
        self.calls.append((action,request.copy()))
        registration={**request,'address':'10.77.0.12/32','server_public_key':SERVER,
                      'endpoint':'vpn.example.com:51820','allowed_ips':'10.77.0.0/24','keepalive':25}
        state={'approve':'ACTIVE','suspend':'SUSPENDED','resume':'ACTIVE','delete':'DELETED'}[action]
        self.records[request['client_id']]=state
        if self.fail:raise ValueError('Acknowledgment lost')
        return {'status':state,'registration':registration if state!='DELETED' else None}


def payload(**extra):
    return {'id':str(uuid.uuid4()),'name':'Test Mac','platform':'MACOS','owner_name':'Test user',
            'email':'user@example.com','public_key':KEY,**extra}


def test_desktop_creation_public_only_retry_and_access_lifecycle(env):
    client,app,headers,_=env;controller=DesktopController();app.state.vpn_controller=controller
    value=payload();result=client.post('/api/v1/admin/vpn-clients',headers=headers,json=value)
    assert result.status_code==200,result.text
    assert result.json()['status']=='ACTIVE' and result.json()['registration']['address']=='10.77.0.12/32'
    assert 'private_key' not in result.text and result.json()['registration']['version']==2
    assert client.post('/api/v1/admin/vpn-clients',headers=headers,json=value).json()['id']==value['id']
    assert len(controller.calls)==1
    for action,state in [('suspend','SUSPENDED'),('resume','ACTIVE'),('delete','DELETED')]:
        response=client.post(f'/api/v1/admin/vpn-clients/{value["id"]}/{action}',headers=headers,json={'reason':'Controlled client lifecycle test'})
        assert response.status_code==200,response.text
        assert response.json()['status']==state
    assert client.get('/api/v1/admin/vpn-clients',headers=headers).json()==[]
    assert client.post(f'/api/v1/admin/vpn-clients/{value["id"]}/resume',headers=headers,json={'reason':'Try to resurrect'}).status_code==409
    assert client.post('/api/v1/admin/vpn-clients',headers=headers,json=value).status_code==409
    assert client.post('/api/v1/admin/vpn-clients',headers=headers,json=payload()).status_code==409
    with app.state.sessions() as db:
        row=db.get(VpnClient,value['id']);assert row.status=='DELETED' and row.registration is None
        assert not any('private' in c.name for c in VpnClient.__table__.columns)


def test_lost_response_keeps_public_intent_and_same_key_retry_does_not_duplicate(env):
    client,app,headers,_=env;controller=DesktopController();app.state.vpn_controller=controller
    value=payload();controller.fail=True
    assert client.post('/api/v1/admin/vpn-clients',headers=headers,json=value).status_code==503
    listed=client.get('/api/v1/admin/vpn-clients',headers=headers).json()
    assert len(listed)==1 and listed[0]['status']=='PENDING'
    controller.fail=False
    assert client.post('/api/v1/admin/vpn-clients',headers=headers,json=value).json()['status']=='ACTIVE'
    assert len(controller.records)==1
    assert client.post('/api/v1/admin/vpn-clients',headers=headers,json={**value,'name':'Changed retry'}).status_code==409


def test_client_validation_viewer_and_archived_customer_guards(env):
    client,app,headers,_=env;controller=DesktopController();app.state.vpn_controller=controller
    token=secrets.token_urlsafe(40)
    with app.state.sessions.begin() as db:db.add(Administrator(name='desktop-viewer',role='viewer',token_hash=digest(token),expires_at=now()+timedelta(days=1)))
    viewer={'Authorization':'Bearer '+token}
    assert client.post('/api/v1/admin/vpn-clients',headers=viewer,json=payload()).status_code==403
    assert client.get('/api/v1/admin/vpn-clients',headers=viewer).status_code==200
    for override in [{'public_key':base64.b64encode(bytes(32)).decode()},{'name':'  '},{'email':'bad'},{'private_key':'DO-NOT-SEND'},{'platform':'UNSUPPORTED'}]:
        assert client.post('/api/v1/admin/vpn-clients',headers=headers,json=payload(**override)).status_code==422
    customer=client.post('/api/v1/admin/customers',headers=headers,json={'name':'Old company'}).json()
    assert client.post('/api/v1/admin/customers/'+customer['id']+'/archive',headers=headers,json={'reason':'Company retired'}).status_code==200
    assert client.post('/api/v1/admin/vpn-clients',headers=headers,json=payload(customer_id=customer['id'])).status_code==409
    assert not controller.calls
