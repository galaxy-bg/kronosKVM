#!/usr/bin/env bash
set -Eeuo pipefail
[[ ${EUID} -eq 0 ]] || { echo 'Run as root' >&2; exit 1; }
install -d -m 0755 /etc/kronoskvm
python3 - <<'PY'
import os
import secrets
from pathlib import Path
path = Path('/etc/kronoskvm/lcd-api-token')
if not path.exists():
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
    with os.fdopen(descriptor, 'w') as stream:
        stream.write(secrets.token_hex(32) + '\n')
os.chown(path, 0, 20)
os.chmod(path, 0o640)
PY
