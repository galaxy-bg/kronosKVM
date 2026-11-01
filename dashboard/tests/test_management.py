from test_gateway import dashboard_env, registration_env, login
from test_registration import active, virtual, enroll


def test_customer_management_and_archival(dashboard_env):
    client, env = dashboard_env
    headers = login(dashboard_env)
    made = client.post('/api/customers', headers=headers, json={'name':'Customer','contact_name':'Contact','email':'a@EXAMPLE.COM'})
    assert made.status_code == 200, made.text
    ident = made.json()['id']
    edited = client.patch('/api/customers/'+ident, headers=headers, json={'name':'Updated','email':'new@example.com','reason':'Contact updated'})
    assert edited.status_code == 200, edited.text
    assert edited.json()['email_verified'] is False
    path = '/api/actions/customers/'+ident
    assert client.post(path+'/archive',headers=headers,json={'reason':'No longer in use'}).status_code == 200
    assert not client.get('/api/overview').json()['customers']
    assert client.get('/api/overview?include_archived=true').json()['customers'][0]['archived_at']
    assert client.post(path+'/restore',headers=headers,json={'reason':'Customer returned'}).status_code == 200
    assert client.get('/api/overview').json()['customers'][0]['name'] == 'Updated'
    assert client.patch('/api/customers/'+ident,headers=headers,json={'name':'Bad','email':'invalid','reason':'Invalid email'}).status_code == 422


def test_precreated_device_enrolls_without_activation_and_restores_revoked(dashboard_env):
    client, env = dashboard_env
    headers = login(dashboard_env)
    identity, _ = virtual()
    payload = {'serial':identity['serial'],'model':'RP4','display_name':'Lab box'}
    created = client.post('/api/devices',headers=headers,json=payload)
    assert created.status_code == 200, created.text
    device = created.json()
    assert device['status'] == 'PENDING' and device['license_id'] is None
    assert enroll(env, identity) == device['id']
    assert client.post('/api/devices',headers=headers,json=payload).status_code == 409
    assert client.post('/api/devices',headers=headers,json={**payload,'status':'ACTIVE'}).status_code == 422
    assert client.patch('/api/devices/'+device['id'],headers=headers,json={'serial':'1000000000000001','reason':'Change identity'}).status_code == 422
    assert client.patch('/api/devices/'+device['id'],headers=headers,json={'display_name':'Renamed','reason':'Update box name'}).status_code == 200
    path = '/api/actions/devices/'+device['id']
    assert client.post(path+'/archive',headers=headers,json={'reason':'Retired device'}).status_code == 200
    assert not client.get('/api/overview').json()['devices']
    assert client.get('/api/overview?include_archived=true').json()['devices'][0]['status'] == 'REVOKED'
    assert client.post(path+'/restore',headers=headers,json={'reason':'Device returned'}).status_code == 200
    restored = client.get('/api/devices/'+device['id']).json()
    assert restored['status'] == 'REVOKED' and len(restored['installations']) == 1


def test_active_records_are_protected_and_mutations_require_csrf(dashboard_env):
    client, env = dashboard_env
    active(env)
    headers = login(dashboard_env)
    overview = client.get('/api/overview').json()
    device, customer = overview['devices'][0], overview['customers'][0]
    for entity, record in [('devices',device),('customers',customer)]:
        assert client.post(f'/api/actions/{entity}/{record["id"]}/archive',headers=headers,json={'reason':'Try active removal'}).status_code == 409
        assert client.patch(f'/api/{entity}/{record["id"]}',headers={'Origin':'http://testserver'},json={'reason':'Missing CSRF'}).status_code == 403
    assert client.patch('/api/devices/'+device['id'],headers=headers,json={'customer_id':None,'reason':'Change owner silently'}).status_code == 409


def test_vpn_requests_require_session_and_mutations_require_csrf(dashboard_env):
    client, env = dashboard_env
    assert client.get('/api/vpn/requests').status_code == 401
    headers = login(dashboard_env)
    assert client.get('/api/vpn/requests').json() == []
    path='/api/actions/vpn/00000000-0000-4000-8000-000000000001/approve'
    assert client.post(path,headers={'Origin':'http://testserver'},json={'reason':'No CSRF present'}).status_code == 403
    assert client.post(path,headers=headers,json={'reason':'Unknown grant'}).status_code == 404


def test_desktop_client_gateway_guards(dashboard_env):
    import uuid
    from test_desktop_clients import DesktopController,payload
    client,env=dashboard_env;env[1].state.vpn_controller=DesktopController()
    assert client.get('/api/vpn/clients').status_code==401
    headers=login(dashboard_env)
    assert client.post('/api/vpn/clients',headers={'Origin':'http://testserver'},json=payload()).status_code==403
    result=client.post('/api/vpn/clients',headers=headers,json=payload())
    assert result.status_code==200,result.text
    assert 'private_key' not in result.text
    assert len(client.get('/api/vpn/clients').json())==1
    path='/api/actions/vpn-clients/'+result.json()['id']+'/delete'
    assert client.post(path,headers=headers,json={'reason':'Gateway cleanup test'}).status_code==200
    assert client.get('/api/vpn/clients').json()==[]


def test_table_peer_delete_requires_csrf_and_suppresses_old_sample(dashboard_env,monkeypatch):
    import time,base64
    from test_gateway import gateway
    client,env=dashboard_env
    key=base64.b64encode(b'u'*32).decode()
    class Controller:
        def apply(self,action,request):return {'status':'DELETED'}
    env[1].state.vpn_controller=Controller()
    async def read(self,devices):
        return {'configured':True,'sampled_at':int(time.time())-10,'peers':[{'public_key':key,'connection_state':'recent','device':None,'received_bytes':10,'sent_bytes':20}], 'totals':{'peers':1,'recent':1,'matched':0,'received_bytes':10,'sent_bytes':20}}
    monkeypatch.setattr(gateway.Reader,'read',read)
    headers=login(dashboard_env)
    body={'public_key':key,'allowed_ips':['10.77.0.2/32'],'reason':'Remove obsolete peer'}
    assert client.post('/api/vpn/peers/delete',headers={'Origin':'http://testserver'},json=body).status_code==403
    assert client.post('/api/vpn/peers/delete',headers=headers,json=body).status_code==200
    after=client.get('/api/vpn').json()
    assert after['peers']==[] and after['totals']['peers']==0
    assert after['totals']['received_bytes']==0 and after['totals']['sent_bytes']==0
