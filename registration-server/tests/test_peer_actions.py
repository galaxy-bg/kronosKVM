import base64,secrets
from datetime import timedelta
from test_registration import env
from test_vpn_enrollment import pending,proof
from test_desktop_clients import DesktopController,payload
from app.models import Administrator,now
from app.crypto import digest

KEY=base64.b64encode(b'u'*32).decode()


def test_legacy_peer_delete_requires_admin_reason_and_exact_addresses(env):
    client,app,headers,_=env
    calls=[]
    class Controller:
        def apply(self,action,request):
            calls.append((action,request));return {'status':'DELETED'}
    app.state.vpn_controller=Controller()
    body={'public_key':KEY,'allowed_ips':['10.77.0.2/32'],'reason':'Remove old computer'}
    assert client.post('/api/v1/admin/vpn-peers/delete',json=body).status_code==401
    token=secrets.token_urlsafe(40)
    with app.state.sessions.begin() as db:db.add(Administrator(name='peer-viewer',role='viewer',token_hash=digest(token),expires_at=now()+timedelta(days=1)))
    assert client.post('/api/v1/admin/vpn-peers/delete',headers={'Authorization':'Bearer '+token},json=body).status_code==403
    for change in [{'reason':'x'},{'allowed_ips':['10.77.0.0/24']},{'allowed_ips':['10.77.0.2/32','10.77.0.2/32']},{'public_key':'bad'}]:
        assert client.post('/api/v1/admin/vpn-peers/delete',headers=headers,json={**body,**change}).status_code==422
    assert not calls
    result=client.post('/api/v1/admin/vpn-peers/delete',headers=headers,json=body)
    assert result.status_code==200,result.text
    assert calls==[('delete-unmanaged',{'version':3,'public_key':KEY,'allowed_ips':['10.77.0.2/32']})]
    assert client.get('/api/v1/admin/events',headers=headers).json()[0]['action']=='VPN_PEER_DELETED'


def test_managed_desktop_table_delete_uses_existing_lifecycle_and_checks_ip(env):
    client,app,headers,_=env;controller=DesktopController();app.state.vpn_controller=controller
    value=payload();made=client.post('/api/v1/admin/vpn-clients',headers=headers,json=value)
    assert made.status_code==200
    body={'public_key':value['public_key'],'allowed_ips':['10.77.0.13/32'],'reason':'Delete selected computer'}
    assert client.post('/api/v1/admin/vpn-peers/delete',headers=headers,json=body).status_code==409
    body['allowed_ips']=['10.77.0.12/32']
    assert client.post('/api/v1/admin/vpn-peers/delete',headers=headers,json=body).status_code==200
    assert controller.calls[-1][0]=='delete'
    assert client.get('/api/v1/admin/vpn-clients',headers=headers).json()==[]


def test_managed_infrabox_table_delete_still_sends_signed_device_cleanup(env):
    client,app,headers,_=env;identity,key,_,request=pending(env)
    ident=client.post('/api/v1/devices/vpn',json=proof(env,identity,key,request)).json()['id']
    assert client.post(f'/api/v1/admin/vpn/{ident}/approve',headers=headers,json={'reason':'Prepare managed box'}).status_code==200
    body={'public_key':request['public_key'],'allowed_ips':['10.77.0.11/32'],'reason':'Delete selected InfraBox'}
    assert client.post('/api/v1/admin/vpn-peers/delete',headers=headers,json=body).status_code==200
    assert app.state.vpn_controller.calls[-1][0]=='delete'
    assert client.post('/api/v1/devices/vpn',json=proof(env,identity,key,request)).json()['status']=='DELETED'
