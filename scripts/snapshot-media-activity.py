#!/usr/bin/env python3
"""Sample gadget reads, including page-cache hits, without touching the USB device."""
import json
import os
import time
from pathlib import Path

STATE = Path('/var/lib/kronoskvm/state')
LUN = Path('/sys/kernel/config/usb_gadget/kronoskvm/functions/mass_storage.usb0/lun.0')


def snapshot(previous, proc=Path('/proc'), lun=LUN, udc=Path('/sys/class/udc'),
             status=STATE / 'virtual-media-status', now=None):
    now = time.time() if now is None else now
    result = dict(updated_at=now, state='unknown', read_bytes_per_second=None,
                  last_read_at=None, observed_bytes=0)
    try:
        filename = Path((lun / 'file').read_text().strip()).name
        if not filename:
            return dict(result, state='ejected')
        result['filename'] = filename
        connected = any(p.read_text().strip() == 'configured' for p in udc.glob('*/state'))
        result['connected'] = connected
        workers = []
        for process in proc.glob('[0-9]*'):
            try:
                if (process / 'comm').read_text().strip() == 'file-storage':
                    workers.append(process)
            except OSError:
                continue
        # Multiple gadgets cannot be attributed safely to this LUN.
        if len(workers) != 1:
            return dict(result, state='unknown' if connected else 'disconnected')
        worker = workers[0]
        counters = dict(line.split(':', 1) for line in (worker / 'io').read_text().splitlines())
        count = int(counters['rchar'])
        identity = f'{worker.name}:{status.stat().st_mtime_ns}:{filename}'
        result.update(identity=identity, counter=count)
        elapsed = now - previous.get('updated_at', now)
        if (previous.get('identity') == identity and 0 < elapsed <= 20
                and count >= previous.get('counter', count)):
            delta = count - previous['counter']
            result.update(observed_bytes=previous.get('observed_bytes', 0) + delta,
                          read_bytes_per_second=delta / elapsed,
                          last_read_at=now if delta else previous.get('last_read_at'),
                          state='reading' if delta else 'idle')
        if not connected:
            result['state'] = 'disconnected'
    except (OSError, ValueError, KeyError):
        pass
    return result


if __name__ == '__main__':
    target = STATE / 'media-activity.json'
    try:
        previous = json.loads(target.read_text())
    except (OSError, ValueError):
        previous = {}
    value = snapshot(previous)
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(value))
    os.chown(temporary, 10001, 20)
    temporary.chmod(0o640)
    temporary.replace(target)
