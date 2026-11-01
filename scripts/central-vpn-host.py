#!/usr/bin/env python3
"""Opt-in host bridge: public request -> device proof -> signed server settings."""
import fcntl
import importlib.util
import json
import os
import subprocess
import time
from pathlib import Path


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


host = module('central_vpn_host_controller', Path(__file__).with_name('remote-assist-host.py'))
AGENT = Path('/opt/kdx-registration-client/client.py')
AGENT_CONFIG = Path('/etc/kdx-registration-client/config.json')


def synchronize(config, central, public, agent, call):
    value = call(public)
    if value.get('status') not in {'PENDING', 'ACTIVE', 'SUSPENDED', 'ARCHIVED', 'DELETED'}:
        raise ValueError('VPN server response unavailable')
    if value['status'] in {'ACTIVE','DELETED'}:
        st = AGENT_CONFIG.stat()
        if st.st_uid != 0 or st.st_mode & 0o022:
            raise ValueError('Server trust configuration must be root-owned and not writable by service users')
        pin = json.loads(AGENT_CONFIG.read_text())['server_public_key']
        if value['status'] == 'DELETED':
            agent.verify_vpn_deletion(value['document'],pin,public)
            config = host.transactional_process(config,{'action':'delete-local-vpn'})
            host.atomic(host.PRIVATE / 'central.json',{'enabled':False,'delete_pending':False,'connect_pending':False})
            return config,{'status':'DELETED','updated_at':int(time.time())}
        if central.get('delete_pending'):
            raise ValueError('Deletion not yet confirmed; profile must not be restored')
        registration = agent.verify_vpn_document(value['document'], pin, public)
        registration = host.registration_response(registration)
        profile = config.get('profile')
        matches = profile and all(profile.get(k) == registration[v] for k,v in (
            ('public_key','server_public_key'), ('address','address'), ('endpoint','endpoint'),
            ('allowed_ips','allowed_ips'), ('keepalive','keepalive')))
        if matches:
            derived = subprocess.run(['wg','pubkey'], input=profile['private_key']+'\n',
                capture_output=True,text=True,timeout=5)
            matches = derived.returncode == 0 and derived.stdout.strip() == public['public_key']
        if not matches:
            if config.get('enabled'):
                raise ValueError('Existing active profile differs; disconnect and review before replacement')
            config = host.transactional_process(config, {'action':'register', 'registration':registration})
        if central.get('connect_pending'):
            if not config.get('enabled'):
                config = host.transactional_process(config, {'action':'enable'})
            central['connect_pending'] = False
            host.atomic(host.PRIVATE / 'central.json', central)
    return config, {'status':value['status'], 'updated_at':int(time.time())}


def main():
    if os.geteuid() != 0:
        return 1
    marker = host.PRIVATE / 'central.json'
    if not marker.exists():
        return 0
    central = json.loads(marker.read_text())
    if not central.get('enabled'):
        return 0
    agent = module('central_vpn_agent', AGENT)
    with (host.STATE / 'remote-assist.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        if (host.STATE / 'remote-assist-request.json').exists():
            return 0
        config = host.read_config()
        try:
            public = central["delete_request"] if central.get("delete_pending") else host.ensure_identity(config)
            def call(request):
                result = subprocess.run(['/usr/sbin/runuser','-u','kdx-registration','--',
                    '/usr/bin/python3',str(AGENT),'vpn'], input=json.dumps({'operation':'delete' if central.get('delete_pending') else 'sync','request':request}),
                    capture_output=True,text=True,timeout=40)
                if result.returncode or len(result.stdout)>8192:
                    raise ValueError('VPN request unavailable')
                return json.loads(result.stdout)
            config, status = synchronize(config, central, public, agent, call)
        except Exception:
            status = {'status':'DELETE_PENDING' if central.get('delete_pending') else 'UNAVAILABLE','error':'VPN_REQUEST_UNCONFIRMED','updated_at':int(time.time())}
        host.atomic(host.STATE / 'central-vpn-status.json',status,public=True)
        host.snapshot(config)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
