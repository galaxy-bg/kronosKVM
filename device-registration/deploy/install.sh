#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run as root'; exit 1; }
[[ ! -e /opt/kdx-registration-client && ! -e /etc/kdx-registration-client ]] || {
 echo 'Existing agent detected; review upgrades without replacing its identity/configuration.'; exit 1;
}
python3 -c 'from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey'
source_dir=$(cd "$(dirname "$0")/.." && pwd)
id kdx-registration >/dev/null 2>&1 || useradd --system --home-dir /var/lib/kdx-registration --shell /usr/sbin/nologin kdx-registration
install -d -m 0755 /opt/kdx-registration-client /etc/kdx-registration-client
install -m 0644 "$source_dir/client.py" /opt/kdx-registration-client/client.py
install -d -m 0700 -o kdx-registration -g kdx-registration /var/lib/kdx-registration
install -d -m 0755 -o kdx-registration -g kdx-registration /var/lib/kdx-registration-public
install -m 0644 "$source_dir/deploy/"kdx-registration-client.{service,timer} /etc/systemd/system/
systemctl daemon-reload
printf 'Agent installed. Provision a pinned config.json before enabling the timer.\n'
