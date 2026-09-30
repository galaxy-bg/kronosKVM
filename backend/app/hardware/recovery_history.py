"""Persistent, bounded DHCP observations shared by host sampler and API."""
import json
import sqlite3
from contextlib import closing

LIMIT = 5000


def connect(path):
    db = sqlite3.connect(str(path), timeout=10)
    db.execute('CREATE TABLE IF NOT EXISTS current (identity TEXT PRIMARY KEY, value TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS events '
               '(id INTEGER PRIMARY KEY, observed REAL, value TEXT)')
    return db


def observe(path, leases, observed):
    with closing(connect(path)) as db, db:
        previous = dict(db.execute('SELECT identity, value FROM current'))
        current = {}
        for lease in leases:
            identity = lease['mac'] + '/' + lease['ip']
            value = json.dumps(lease, sort_keys=True)
            current[identity] = value
            if previous.get(identity) != value:
                db.execute('INSERT INTO events(observed, value) VALUES (?, ?)', (observed, value))
        db.execute('DELETE FROM current')
        db.executemany('INSERT INTO current VALUES (?, ?)', current.items())
        db.execute('DELETE FROM events WHERE id NOT IN '
                   '(SELECT id FROM events ORDER BY id DESC LIMIT ?)', (LIMIT,))


def history(path, clear=False):
    with closing(connect(path)) as db, db:
        if clear:
            # Preserve observations so unchanged leases do not immediately reappear.
            db.execute('DELETE FROM events')
            return []
        return [dict(json.loads(value), observed_at=observed)
                for observed, value in db.execute(
                    'SELECT observed, value FROM events ORDER BY id DESC')]
