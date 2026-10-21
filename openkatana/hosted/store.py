"""Bounded SQLite queue and hashed credentials. No tool code runs here."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import secrets
import sqlite3
import time
import uuid


def fingerprint(value):
    return hashlib.sha256(value.encode()).hexdigest()


class Store:
    def __init__(self, settings):
        self.settings = settings
        self.root = settings.data
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = self.root / 'control.sqlite3'
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, label TEXT NOT NULL, project TEXT);
                CREATE TABLE IF NOT EXISTS tokens (digest TEXT PRIMARY KEY, user TEXT NOT NULL,
                    kind TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, user TEXT NOT NULL,
                    request_id TEXT NOT NULL, signature TEXT NOT NULL, tool TEXT NOT NULL,
                    arguments TEXT NOT NULL, state TEXT NOT NULL, created REAL NOT NULL,
                    updated REAL NOT NULL, result TEXT, error TEXT,
                    UNIQUE(user, request_id));
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def ensure_user(self, user, label):
        if not re.fullmatch(r'[a-f0-9]{32}', user):
            raise ValueError('Invalid account identifier')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM users WHERE id=?', (user,)).fetchone():
                if db.execute('SELECT count(*) FROM users').fetchone()[0] >= self.settings.max_users:
                    raise ValueError('This pilot is at its account capacity')
                db.execute('INSERT INTO users VALUES(?,?,NULL)', (user, str(label)[:100]))
        return user

    def add_user(self, label):
        user = self.ensure_user(uuid.uuid4().hex, label)
        return {'user': user, 'access_key': self.issue(user, 'login', 7 * 86400)}

    def issue(self, user, kind, lifetime):
        token = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute('INSERT INTO tokens VALUES(?,?,?,?)', (fingerprint(token), user, kind, time.time() + lifetime))
        return token

    def authenticate(self, token, kinds):
        if not isinstance(token, str) or len(token) > 8192:
            return None
        with self.connect() as db:
            row = db.execute('SELECT * FROM tokens WHERE digest=? AND expires>?', (fingerprint(token), time.time())).fetchone()
        return row['user'] if row and row['kind'] in kinds else None

    def revoke(self, token):
        with self.connect() as db:
            db.execute('DELETE FROM tokens WHERE digest=?', (fingerprint(token),))

    def revoke_api_keys(self, user):
        with self.connect() as db:
            db.execute("DELETE FROM tokens WHERE user=? AND kind='api'", (user,))

    def workspace(self, user):
        if not re.fullmatch(r'[a-f0-9]{32}', user):
            raise ValueError('Invalid account identifier')
        return self.root / 'workspaces' / user

    def selected(self, user, project=None):
        with self.connect() as db:
            if project is not None:
                if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', project):
                    raise ValueError('Invalid project ID')
                if not (self.workspace(user) / project / 'project.json').is_file():
                    raise ValueError('Project not found')
                db.execute('UPDATE users SET project=? WHERE id=?', (project, user))
            row = db.execute('SELECT project FROM users WHERE id=?', (user,)).fetchone()
        return row['project'] if row else None

    def submit(self, user, tool, arguments, request_id):
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
            raise ValueError('Supply a request_id of 1..128 characters')
        raw = json.dumps(arguments, sort_keys=True, separators=(',', ':'), allow_nan=False)
        if len(raw.encode()) > 4 * 1024**2:
            raise ValueError('Tool arguments exceed 4 MiB')
        signature = fingerprint(tool + '\n' + raw)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM jobs WHERE user=? AND request_id=?', (user, request_id)).fetchone()
            if old:
                if old['signature'] != signature:
                    raise ValueError('This request_id belongs to different arguments')
                return self.public(old)
            if db.execute("SELECT count(*) FROM jobs WHERE user=? AND state IN ('queued','running')", (user,)).fetchone()[0] >= self.settings.max_pending:
                raise ValueError('Workspace queue is full')
            now = time.time(); key = uuid.uuid4().hex
            db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                       (key, user, request_id, signature, tool, raw, 'queued', now, now, None, None))
            return self.public(db.execute('SELECT * FROM jobs WHERE id=?', (key,)).fetchone())

    @staticmethod
    def public(row):
        out = {k: row[k] for k in ('id', 'request_id', 'tool', 'state', 'created', 'updated', 'error')}
        if row['result'] is not None:
            out['result'] = json.loads(row['result'])
        return out

    def job(self, user, key):
        with self.connect() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=? AND user=?', (key, user)).fetchone()
        if not row:
            raise ValueError('Job not found')
        return self.public(row)

    def jobs(self, user):
        with self.connect() as db:
            return [self.public(r) for r in db.execute('SELECT * FROM jobs WHERE user=? ORDER BY created DESC LIMIT 100', (user,))]

    def busy(self, user):
        with self.connect() as db:
            return bool(db.execute("SELECT 1 FROM jobs WHERE user=? AND state='running'", (user,)).fetchone())

    def cancel(self, user, key):
        with self.connect() as db:
            db.execute("UPDATE jobs SET state='cancelled',updated=? WHERE id=? AND user=? AND state IN ('queued','running')", (time.time(), key, user))
        return self.job(user, key)

    def claim(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM jobs WHERE state='queued' AND user NOT IN (SELECT user FROM jobs WHERE state='running') ORDER BY created LIMIT 1").fetchone()
            if row:
                db.execute("UPDATE jobs SET state='running',updated=? WHERE id=?", (time.time(), row['id']))
                return dict(row)

    def finish(self, key, result=None, error=None):
        with self.connect() as db:
            db.execute("UPDATE jobs SET state=?,result=?,error=?,updated=? WHERE id=? AND state='running'",
                       ('failed' if error else 'succeeded', json.dumps(result, allow_nan=False) if result is not None else None,
                        str(error)[:2000] if error else None, time.time(), key))

    def recover(self):
        with self.connect() as db:
            db.execute("UPDATE jobs SET state='interrupted',error='Worker restarted; inspect receipts before resubmitting',updated=? WHERE state='running'", (time.time(),))
