import json
import sqlite3
from uuid import uuid4

from test_gateway import dashboard_env, registration_env, login, ORIGIN, gateway
from kdx_dashboard_backend.tasks import TaskStore


def test_tasks_capture_outcomes_without_payloads_and_enforce_auth(dashboard_env):
    client, env = dashboard_env
    assert client.get('/api/tasks').status_code == 401
    headers = login(dashboard_env)
    response = client.post('/api/customers', json={'name':'Secret customer name','email':'private@example.com'}, headers=headers)
    assert response.status_code == 200, response.text
    ident = response.headers['X-KDX-Task-ID']
    tasks = client.get('/api/tasks').json()
    assert tasks['active'] == 0
    task = client.get('/api/tasks/'+ident).json()
    assert task['title'] == 'Create customer'
    assert task['status'] == 'successful' and task['progress'] == 100
    assert [e['status'] for e in task['events']] == ['queued','running','successful']
    assert 'Secret customer' not in json.dumps(task)
    assert 'private@example.com' not in json.dumps(task)
    assert env[2]['Authorization'].removeprefix('Bearer ') not in json.dumps(task)
    response = client.post('/api/devices', json={}, headers=headers)
    assert response.status_code == 422
    failed = client.get('/api/tasks/'+response.headers['X-KDX-Task-ID']).json()
    assert failed['status'] == 'failed' and failed['error'] == 'Request validation failed. Review the form fields.'
    count = len(client.get('/api/tasks').json()['items'])
    assert client.post('/api/customers',json={'name':'Blocked'},headers=ORIGIN).status_code == 403
    assert len(client.get('/api/tasks').json()['items']) == count
    assert client.post('/api/tasks/events',json={'kind':'vpn_config_download','target':str(uuid4()),'private_key':'DO NOT STORE'},headers=headers).status_code == 422
    event = client.post('/api/tasks/events',json={'kind':'vpn_config_download','target':str(uuid4())},headers=headers)
    assert event.status_code == 200, event.text
    assert client.get('/api/tasks/'+event.json()['task_id']).json()['status'] == 'successful'
    assert client.delete('/api/tasks/completed',headers=headers).status_code == 200
    remaining = client.get('/api/tasks').json()['items']
    assert len(remaining) == 1 and remaining[0]['operation'] == 'tasks.clear'


def test_task_store_restart_retains_completed_and_marks_interrupted_unknown(tmp_path):
    path = tmp_path/'state/tasks.sqlite3'
    store = TaskStore(str(path))
    done = store.start('devices.update','Update device','admin',str(uuid4()))
    store.finish(done,'successful',200)
    interrupted = store.start('vpn.approve','Approve device VPN access','admin')
    store.close()
    store = TaskStore(str(path))
    assert store.detail(done)['status'] == 'successful'
    assert store.detail(interrupted)['status'] == 'unknown'
    assert store.detail(interrupted)['error'] == 'Service restarted before the outcome was confirmed.'
    running = store.start('devices.create','Create device','admin')
    assert store.clear() == 2
    assert store.detail(running)['status'] == 'running'
    assert path.stat().st_mode & 0o777 == 0o600
    store.close()


def test_task_store_failure_prevents_upstream_mutation(dashboard_env,monkeypatch):
    client,env=dashboard_env
    headers=login(dashboard_env)
    def broken(*args,**kwargs):raise sqlite3.OperationalError('disk full')
    monkeypatch.setattr(TaskStore,'start',broken)
    response=client.post('/api/customers',json={'name':'Do not create'},headers=headers)
    assert response.status_code==503
    assert not client.get('/api/overview').json()['customers']


def test_upstream_timeout_is_unknown_and_not_replayed(dashboard_env,monkeypatch):
    import httpx
    client,env=dashboard_env
    headers=login(dashboard_env)
    original=client.app.state.upstream.request
    calls=[]
    async def timed_out(method,path,**kwargs):
        if method=='POST':
            calls.append(path)
            raise httpx.ReadTimeout('private upstream error must not be stored')
        return await original(method,path,**kwargs)
    monkeypatch.setattr(client.app.state.upstream,'request',timed_out)
    response=client.post('/api/customers',json={'name':'Unconfirmed'},headers=headers)
    assert response.status_code==503
    task=client.get('/api/tasks/'+response.headers['X-KDX-Task-ID']).json()
    assert task['status']=='unknown'
    assert 'private upstream' not in json.dumps(task)
    client.get('/api/tasks')
    assert len(calls)==1
