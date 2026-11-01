"""Fixed, key-only SSH transport to the VPN server's constrained command."""
import json
import subprocess


class Controller:
    def __init__(self, cfg):
        self.cfg = cfg

    def apply(self, action, request):
        if not self.cfg.vpn_management_enabled:
            raise ValueError('VPN management is not configured')
        result = subprocess.run([
            '/usr/bin/ssh', '-F', '/dev/null', '-T',
            '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-o', 'IdentityAgent=none',
            '-o', 'StrictHostKeyChecking=yes', '-o', 'PasswordAuthentication=no',
            '-o', 'ConnectTimeout=5', '-o', 'ConnectionAttempts=1',
            '-o', 'UserKnownHostsFile=' + self.cfg.vpn_known_hosts,
            '-i', self.cfg.vpn_ssh_key, 'kdx-vpn-manager@172.12.2.74', 'manage',
        ], input=json.dumps({'action': action, 'request': request}),
            capture_output=True, text=True, timeout=20)
        if result.returncode or len(result.stdout) > 8192:
            raise ValueError('VPN operation unconfirmed; retry the same action to reconcile')
        value = json.loads(result.stdout)
        if not isinstance(value, dict) or value.get('status') not in {'ACTIVE', 'SUSPENDED', 'ARCHIVED', 'DELETED', 'PRESENT', 'MISSING'}:
            raise ValueError('Invalid VPN operation response')
        return value
