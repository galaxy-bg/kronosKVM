#!/usr/bin/env python3
"""Inspect phone WAN without confusing Ethernet internet with USB internet."""
import argparse
import json
import subprocess
from pathlib import Path

DRIVERS = {"rndis_host", "cdc_ether", "cdc_ncm", "ipheth"}
STORAGE_PORTS = {"1-1.1", "2-1"}


def phone_interfaces(net_root=Path('/sys/class/net')):
    found = []
    for net in sorted(net_root.iterdir()):
        device = (net / 'device').resolve()
        driver = (net / 'device/driver').resolve().name
        if driver not in DRIVERS:
            continue
        port = next((p.name for p in device.parents if p.name in STORAGE_PORTS), None)
        found.append({'interface': net.name, 'driver': driver, 'storage_port': bool(port),
                      'usb_port': port, 'device_path': str(device)})
    return found


def command(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=20, check=False)
    return {'ok': result.returncode == 0, 'output': result.stdout.strip(),
            'error': result.stderr.strip()}


def check(probe=False):
    interfaces = phone_interfaces()
    for item in interfaces:
        name = item['interface']
        item['network'] = command(['nmcli', '-f', 'GENERAL.STATE,GENERAL.CONNECTION,IP4',
                                   'device', 'show', name])
        item['routes'] = command(['ip', '-4', 'route', 'show', 'dev', name])
        if probe and item['storage_port']:
            # No proxy and explicit device binding: eth0 must not satisfy this probe.
            # Literal endpoint tests USB internet independently of system DNS.
            item['internet_ipv4'] = command([
                'curl', '--noproxy', '*', '--interface', name, '-4', '-fsS',
                '--connect-timeout', '5', '--max-time', '12',
                'https://1.1.1.1/cdn-cgi/trace', '-o', '/dev/null', '-w', '%{http_code}',
            ])
    return {'status': 'detected' if interfaces else 'waiting_for_phone',
            'interfaces': interfaces}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', action='store_true', help='Test HTTPS through USB only')
    print(json.dumps(check(parser.parse_args().probe), indent=2))
