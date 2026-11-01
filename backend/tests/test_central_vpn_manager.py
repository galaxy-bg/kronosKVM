import importlib.util
import json
from pathlib import Path
import pytest
from test_wireguard_server import setup, key, server_module

spec=importlib.util.spec_from_file_location('central_vpn_manager',Path('scripts/kdx-vpn-manage.py'))
manager_module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(manager_module)
manager_module.server = server_module


def test_adoption_is_noop_and_disable_resume_archive_preserve_other_peers(setup):
    manager,request,runtime,calls,_,_=setup
    manager.add(request)
    before=manager.config.read_bytes()
    calls.clear()
    approved=manager_module.apply(manager,'approve',request)
    assert approved['status']=='ACTIVE' and approved['registration']['address']=='10.77.0.11/32'
    assert manager.config.read_bytes()==before and not any(c[0]=='set' for c in calls)
    for action,state,present in [('suspend','SUSPENDED',False),('suspend','SUSPENDED',False),
                                 ('resume','ACTIVE',True),('resume','ACTIVE',True),('delete','DELETED',False)]:
        assert manager_module.apply(manager,action,request)['status']==state
        assert (request['public_key'] in runtime)==present
        if state=='SUSPENDED':assert manager_module.apply(manager,'inspect',request)['status']=='PRESENT'
        assert runtime[key(1)]=='10.77.0.2/32' and runtime[key(2)]=='10.77.0.10/32'
    assert request['hostname'] not in json.loads(manager.registry.read_text())
    assert manager_module.apply(manager,'delete',request)['status']=='DELETED'
    assert manager_module.apply(manager,'inspect',request)['status']=='MISSING'
    assert manager.allocate(*manager.inventory()[1:3],manager.records()) == '10.77.0.11/32'


def test_conflicting_identity_and_mutation_failure_do_not_change_other_peers(setup):
    manager,request,runtime,calls,fail,_=setup
    manager_module.apply(manager,'approve',request)
    before=manager.config.read_bytes()
    with pytest.raises(ValueError,match='identity differs'):
        manager_module.apply(manager,'approve',{**request,'public_key':key(5)})
    fail[0]=True
    with pytest.raises(server_module.ProvisionError):
        manager_module.apply(manager,'suspend',request)
    assert manager.config.read_bytes()==before
    assert runtime[key(1)]=='10.77.0.2/32'
    assert json.loads(manager.registry.read_text())[request['hostname']].get('central_status','ACTIVE')=='ACTIVE'


def test_desktop_and_infrabox_peers_share_pool_without_fake_serials(setup):
    import uuid
    manager,request,runtime,_,_,_=setup
    desktop={'version':2,'client_id':str(uuid.uuid4()),'hostname':'client-test',
             'public_key':key(8),'request_id':str(uuid.uuid4())}
    result=manager_module.apply(manager,'approve',desktop)
    assert result['registration']['address']=='10.77.0.11/32' and 'device_id' not in result['registration']
    box=manager_module.apply(manager,'approve',request)
    assert box['registration']['address']=='10.77.0.12/32'
    assert manager_module.apply(manager,'suspend',desktop)['status']=='SUSPENDED'
    assert request['public_key'] in runtime
    assert manager_module.apply(manager,'resume',desktop)['registration']['address']=='10.77.0.11/32'
    assert manager_module.apply(manager,'delete',desktop)['status']=='DELETED'
    assert desktop['public_key'] not in runtime and request['public_key'] in runtime
    assert runtime[key(1)]=='10.77.0.2/32' and runtime[key(2)]=='10.77.0.10/32'


def test_unmanaged_selection_deletes_only_exact_key_and_addresses(setup):
    manager,request,runtime,_,_,_=setup
    manager_module.apply(manager,'approve',request)
    selected={'version':3,'public_key':key(1),'allowed_ips':['10.77.0.2/32']}
    before=manager.config.read_bytes()
    with pytest.raises(ValueError,match='addresses changed'):
        manager_module.apply(manager,'delete-unmanaged',{**selected,'allowed_ips':['10.77.0.9/32']})
    assert manager.config.read_bytes()==before and key(1) in runtime
    assert manager_module.apply(manager,'delete-unmanaged',selected)['status']=='DELETED'
    assert key(1) not in runtime and key(2) in runtime and request['public_key'] in runtime
    assert manager_module.apply(manager,'delete-unmanaged',selected)['status']=='DELETED'
    with pytest.raises(ValueError,match='central lifecycle'):
        manager_module.apply(manager,'delete-unmanaged',{'version':3,'public_key':request['public_key'],'allowed_ips':['10.77.0.11/32']})


def test_unmanaged_delete_rolls_back_and_never_selects_replacement_by_ip(setup):
    manager,request,runtime,_,fail,_=setup
    selected={'version':3,'public_key':key(1),'allowed_ips':['10.77.0.2/32']}
    before=manager.config.read_bytes();fail[0]=True
    with pytest.raises(server_module.ProvisionError):manager_module.apply(manager,'delete-unmanaged',selected)
    assert manager.config.read_bytes()==before and runtime[key(1)]=='10.77.0.2/32'
    manager_module.apply(manager,'delete-unmanaged',selected)
    # A new public key may reuse the retired IP. Delayed deletion of the old key
    # must not touch the replacement peer.
    new={**request,'public_key':key(7),'hostname':'new-client','device_id':'1000000000000007'}
    manager.start=__import__('ipaddress').IPv4Address('10.77.0.2')
    manager.add(new,requested='10.77.0.2')
    assert manager_module.apply(manager,'delete-unmanaged',selected)['status']=='DELETED'
    assert runtime[key(7)]=='10.77.0.2/32'
