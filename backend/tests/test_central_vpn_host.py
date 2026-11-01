import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

spec=importlib.util.spec_from_file_location('central_bridge',Path('scripts/central-vpn-host.py'))
bridge=importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class Trust:
    def stat(self):return SimpleNamespace(st_uid=0,st_mode=0o644)
    def read_text(self):return json.dumps({'server_public_key':'PIN'})


@pytest.fixture
def setup(monkeypatch):
    public={'public_key':'DEVICE-PUBLIC'}
    registration={'server_public_key':'SERVER-PUBLIC','address':'10.77.0.11/32',
                  'endpoint':'vpn.example.com:51820','allowed_ips':'10.77.0.0/24','keepalive':25}
    profile={'public_key':'SERVER-PUBLIC','address':'10.77.0.11/32','private_key':'TEST-PRIVATE',
             'endpoint':'vpn.example.com:51820','allowed_ips':'10.77.0.0/24','keepalive':25}
    monkeypatch.setattr(bridge,'AGENT_CONFIG',Trust())
    monkeypatch.setattr(bridge.host,'registration_response',lambda value:value)
    monkeypatch.setattr(bridge.host,'atomic',Mock())
    changes=[]
    def mutate(config,request):
        changes.append(request['action'])
        return {**config,'enabled':True}
    monkeypatch.setattr(bridge.host,'transactional_process',mutate)
    monkeypatch.setattr(bridge.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stdout='DEVICE-PUBLIC\n'))
    agent=SimpleNamespace(verify_vpn_document=Mock(return_value=registration))
    call=lambda request:{'status':'ACTIVE','document':{'signed':'response'}}
    return public,profile,agent,call,changes


def test_existing_profile_and_boot_policy_are_preserved_without_reconnect(setup):
    public,profile,agent,call,changes=setup
    config={'profile':profile,'enabled':False,'autostart':False}
    value,status=bridge.synchronize(config,{'enabled':True,'connect_pending':False},public,agent,call)
    assert value==config and changes==[] and status['status']=='ACTIVE'
    agent.verify_vpn_document.assert_called_once()


def test_explicit_initial_connect_is_consumed_once(setup):
    public,profile,agent,call,changes=setup
    central={'enabled':True,'connect_pending':True}
    config={'profile':profile,'enabled':False,'autostart':False}
    config,_=bridge.synchronize(config,central,public,agent,call)
    assert changes==['enable'] and config['autostart'] is False and not central['connect_pending']
    bridge.synchronize(config,central,public,agent,call)
    assert changes==['enable']


def test_signed_settings_cannot_replace_a_different_active_profile(setup):
    public,profile,agent,call,changes=setup
    config={'profile':{**profile,'address':'10.99.0.2/32'},'enabled':True,'autostart':False}
    with pytest.raises(ValueError,match='differs'):
        bridge.synchronize(config,{'enabled':True,'connect_pending':True},public,agent,call)
    assert changes==[]


def test_signed_remote_deletion_cleans_profile_and_disables_polling(setup):
    public,profile,agent,call,changes=setup
    agent.verify_vpn_deletion=Mock()
    config,status=bridge.synchronize({'profile':profile,'enabled':True}, {'enabled':True},
        public,agent,lambda request:{'status':'DELETED','document':{'signed':'delete'}})
    assert status['status']=='DELETED' and changes==['delete-local-vpn']
    agent.verify_vpn_deletion.assert_called_once()
    assert bridge.host.atomic.call_args.args[1]['enabled'] is False


def test_invalid_delete_document_and_pending_outbox_cannot_restore_or_delete(setup):
    public,profile,agent,call,changes=setup
    agent.verify_vpn_deletion=Mock(side_effect=ValueError('Invalid signature'))
    with pytest.raises(ValueError):
        bridge.synchronize({'profile':profile,'enabled':True},{'enabled':True},public,agent,
            lambda request:{'status':'DELETED','document':{}})
    with pytest.raises(ValueError,match='Deletion not yet confirmed'):
        bridge.synchronize({'profile':None,'enabled':False},{'enabled':True,'delete_pending':True},public,agent,call)
    assert changes==[]
