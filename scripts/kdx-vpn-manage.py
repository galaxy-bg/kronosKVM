#!/usr/bin/env python3
"""Forced SSH command: manage exact enrolled peers, never arbitrary shell input."""
import importlib.util
import ipaddress
import json
import os
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location('vpn_server', Path(__file__).with_name('kdx-wg-server.py'))
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


def delete_unmanaged(manager, request):
    # A selection is identified by key AND the displayed address set, never IP alone.
    if not isinstance(request,dict) or set(request)!={"version","public_key","allowed_ips"} or type(request["version"]) is not int or request["version"]!=3:
        raise ValueError("Invalid peer selection")
    pub=server.public_key(request["public_key"])
    ips=request["allowed_ips"]
    if not isinstance(ips,list) or not 1<=len(ips)<=16:
        raise ValueError("Invalid peer addresses")
    expected=[]
    for value in ips:
        network=ipaddress.IPv4Network(value,strict=True)
        if network.prefixlen!=32 or not network.subnet_of(manager.network) or str(network)!=value:
            raise ValueError("Select exact addresses in this VPN network")
        expected.append(network)
    if len(set(expected))!=len(expected):raise ValueError("Duplicate peer addresses")
    if pub==server.wg("show",manager.interface,"public-key"):
        raise ValueError("Cannot delete server identity")
    with manager.locked():
        before,file_peers,live,records=manager.inventory()
        if any(record.get("public_key")==pub for record in records.values()):
            raise ValueError("Registered peer must use central lifecycle")
        for source in (file_peers,live):
            if pub in source and set(source[pub])!=set(expected):
                raise ValueError("Selected peer addresses changed; refresh inventory")
        if pub not in file_peers and pub not in live:
            return {"status":"DELETED"}
        after=''.join(block for block in server.blocks(before)
                      if server.fields(block).get("publickey")!=[pub])
        manager.transaction(before,after,records,records,pub,None,live)
        return {"status":"DELETED"}


def apply(manager, action, request):
    if action == "delete-unmanaged":
        return delete_unmanaged(manager, request)
    server.validate_request(request)
    if action not in {'approve', 'suspend', 'resume', 'archive', 'delete', 'inspect'}:
        raise ValueError('Unsupported operation')
    peer_name, pub = request['hostname'], request['public_key']
    # The legacy add transaction handles allocation and rollback. Retry after a
    # successful remote change is reconciled against exact public request fields.
    with manager.locked():
        _, _, _, records = manager.inventory()
        existing = records.get(peer_name)
        if existing and any(existing.get(k) != v for k, v in request.items()):
            raise ValueError('Peer identity differs; operator recovery required')
        if action in {'delete', 'archive', 'inspect'}:
            before, file_peers, live, records = manager.inventory()
            if not existing:
                if pub in file_peers or pub in live or any(r.get('public_key') == pub for r in records.values()):
                    raise ValueError('Unmanaged or conflicting peer; operator review required')
                return {'status': 'MISSING' if action == 'inspect' else 'DELETED', 'registration': None}
            expected = [ipaddress.ip_network(existing['address'])]
            if any(pub in source and source[pub] != expected for source in (file_peers, live)):
                raise ValueError('Peer routes changed outside management')
            if action == 'inspect':
                if pub in file_peers and pub in live:
                    return {'status':'PRESENT'}
                if pub not in file_peers and pub not in live:
                    return {'status':'DELETED' if existing.get('central_status') == 'ARCHIVED' else 'PRESENT' if existing.get('central_status') == 'SUSPENDED' else 'MISSING'}
                raise ValueError('Persistent and runtime peer state differs; retry or reconcile')
            after = ''.join(b for b in server.blocks(before)
                            if server.fields(b).get('publickey') != [pub])
            updated = {name:r for name,r in records.items() if name != peer_name}
            manager.transaction(before,after,records,updated,pub,None,live)
            return {'status':'DELETED','registration':None}
        if not existing and action in {'suspend', 'resume'}:
            raise ValueError('No existing managed peer')
    if not existing:
        if action == 'archive':
            return {'status': 'ARCHIVED', 'registration': None}
        manager.add(request)
    with manager.locked():
        before, file_peers, live, records = manager.inventory()
        record = records.get(peer_name)
        if not record or any(record.get(k) != v for k, v in request.items()):
            raise ValueError('Peer identity changed')
        old_state = record.get('central_status', 'ACTIVE')
        if old_state == 'ARCHIVED' and action != 'archive':
            raise ValueError('Archived peer requires operator recovery')
        expected = [ipaddress.ip_network(record['address'])]
        if any(pub in source and source[pub] != expected for source in (file_peers, live)):
            raise ValueError('Peer routes changed outside management')
        desired = {'approve':'ACTIVE', 'resume':'ACTIVE', 'suspend':'SUSPENDED', 'archive':'ARCHIVED'}[action]
        if old_state == desired:
            present = pub in file_peers and pub in live
            absent = pub not in file_peers and pub not in live
            if (desired == 'ACTIVE' and not present) or (desired != 'ACTIVE' and not absent):
                raise ValueError('Saved peer state differs from runtime; operator recovery required')
            # Existing active legacy peer adoption is deliberately a no-op.
        else:
            after = ''.join(b for b in server.blocks(before)
                            if server.fields(b).get('publickey') != [pub])
            address = None
            if desired == 'ACTIVE':
                for source in (file_peers, live):
                    if any(n.overlaps(expected[0]) for key, nets in source.items() if key != pub
                           for n in nets if n.version == 4):
                        raise ValueError('Reserved address conflicts with another peer')
                address = record['address']
                after = after.rstrip() + (f'\n\n[Peer]\n# KDX InfraBox {peer_name}\n'
                                         f'PublicKey = {pub}\nAllowedIPs = {address}\n')
            updated = {**records, peer_name: {**record, 'central_status': desired}}
            manager.transaction(before, after, records, updated, pub, address, live)
        registration = {k: record[k] for k in (*request.keys(), 'address', 'endpoint',
                                               'server_public_key', 'allowed_ips', 'keepalive')}
        return {'status': desired, 'registration': registration}


def main():
    os.umask(0o077)
    try:
        if os.geteuid() != 0:
            raise ValueError('Restricted local privilege required')
        raw = sys.stdin.buffer.read(4097)
        value = json.loads(raw)
        if len(raw) > 4096 or set(value) != {'action', 'request'}:
            raise ValueError('Invalid operation')
        settings = json.loads(Path('/etc/wireguard/kdx-registration.json').read_text())
        manager = server.Server(settings.get('config','/etc/wireguard/wg0.conf'),
            settings.get('registry','/etc/wireguard/kdx-peers.json'), settings.get('interface','wg0'),
            settings.get('network','10.77.0.0/24'), settings.get('pool_start','10.77.0.11'),
            settings.get('pool_end','10.77.0.254'), settings['endpoint'])
        print(json.dumps(apply(manager, value['action'], value['request'])))
        return 0
    except Exception:
        print('VPN operation failed; no credentials or private keys were printed', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
