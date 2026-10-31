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
