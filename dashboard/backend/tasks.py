"""Durable operation history. Never accepts payloads, credentials or result bodies."""
import re
import sqlite3
import threading
import uuid
from datetime import datetime,timezone
from pathlib import Path


def now():return datetime.now(timezone.utc).isoformat()


def operation(method,path):
    exact={
        ('POST','/api/customers'):('customers.create','Create customer',None),
        ('POST','/api/devices'):('devices.create','Create device',None),
        ('POST','/api/licenses'):('licenses.create','Create license',None),
        ('POST','/api/vpn/clients'):('vpn-clients.create','Create computer VPN client',None),
        ('POST','/api/vpn/peers/delete'):('vpn-peers.delete','Delete selected VPN peer',None),
        ('DELETE','/api/tasks/completed'):('tasks.clear','Clear completed task history',None),
    }
    if (method,path) in exact:return exact[(method,path)]
    if method=='PATCH':
        match=re.fullmatch(r'/api/(customers|devices)/([0-9a-fA-F-]{36})',path)
        if match:
            entity,ident=match.groups();uuid.UUID(ident)
            return(entity+'.update','Update '+('customer' if entity=='customers' else 'device'),ident)
    if method=='POST':
        match=re.fullmatch(r'/api/actions/(customers|devices|licenses|vpn|vpn-clients)/([0-9a-fA-F-]{36})/(approve|suspend|resume|revoke|renew|reassign|archive|restore|delete)',path)
        if match:
            entity,ident,action=match.groups();uuid.UUID(ident)
            nouns={'customers':'customer','devices':'device','licenses':'license','vpn':'device VPN access','vpn-clients':'computer VPN access'}
            return(entity+'.'+action,action.capitalize()+' '+nouns[entity],ident)
    return None


class TaskStore:
    def __init__(self,path):
        self.lock=threading.RLock()
        if path!=':memory:':
            folder=Path(path).parent;folder.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.db=sqlite3.connect(path,check_same_thread=False,timeout=5)
        self.db.row_factory=sqlite3.Row
        if path!=':memory:':Path(path).chmod(0o600)
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS tasks (
          id TEXT PRIMARY KEY,operation TEXT NOT NULL,title TEXT NOT NULL,actor TEXT NOT NULL,
          target TEXT,status TEXT NOT NULL,progress INTEGER,created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,completed_at TEXT,error TEXT,http_status INTEGER);
        CREATE INDEX IF NOT EXISTS task_created ON tasks(created_at DESC);
        CREATE TABLE IF NOT EXISTS task_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
          status TEXT NOT NULL,detail TEXT NOT NULL,created_at TEXT NOT NULL);
        ''')
        for row in self.db.execute("SELECT id FROM tasks WHERE status IN ('queued','running')").fetchall():
            self.finish(row['id'],'unknown',None,'Service restarted before the outcome was confirmed.')
        self.db.commit()

    def start(self,operation,title,actor,target=None):
        ident=str(uuid.uuid4());tick=now()
        with self.lock,self.db:
            self.db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                (ident,operation,title,actor,target,'queued',0,tick,tick,None,None,None))
            self.db.execute('INSERT INTO task_events(task_id,status,detail,created_at) VALUES(?,?,?,?)',
                (ident,'queued','Request accepted for processing.',tick))
            self.db.execute("DELETE FROM tasks WHERE id IN (SELECT id FROM tasks WHERE status NOT IN ('queued','running') ORDER BY created_at DESC LIMIT -1 OFFSET 1000)")
        self.running(ident)
        return ident

    def running(self,ident):
        tick=now()
        with self.lock,self.db:
            self.db.execute("UPDATE tasks SET status='running',progress=NULL,updated_at=? WHERE id=?",(tick,ident))
            self.db.execute('INSERT INTO task_events(task_id,status,detail,created_at) VALUES(?,?,?,?)',(ident,'running','Operation in progress.',tick))

    def finish(self,ident,status,code=None,error=None):
        tick=now();progress=100 if status=='successful' else None
        detail=error or 'Operation completed. Device follow-up actions may require synchronization.'
        with self.lock,self.db:
            self.db.execute('UPDATE tasks SET status=?,progress=?,updated_at=?,completed_at=?,error=?,http_status=? WHERE id=?',
                (status,progress,tick,tick,error,code,ident))
            self.db.execute('INSERT INTO task_events(task_id,status,detail,created_at) VALUES(?,?,?,?)',(ident,status,detail,tick))

    def list(self):
        with self.lock:
            rows=[dict(r) for r in self.db.execute('SELECT * FROM tasks ORDER BY created_at DESC LIMIT 200')]
            active=self.db.execute("SELECT COUNT(*) FROM tasks WHERE status IN ('queued','running')").fetchone()[0]
            return {'items':rows,'active':active,'limit':200}

    def detail(self,ident):
        with self.lock:
            row=self.db.execute('SELECT * FROM tasks WHERE id=?',(ident,)).fetchone()
            if not row:return None
            return {**dict(row),'events':[dict(e) for e in self.db.execute('SELECT status,detail,created_at FROM task_events WHERE task_id=? ORDER BY id',(ident,))]}

    def clear(self):
        with self.lock,self.db:
            result=self.db.execute("DELETE FROM tasks WHERE status NOT IN ('queued','running')")
            return result.rowcount

    def close(self):
        with self.lock:self.db.close()
