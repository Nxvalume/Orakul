"""Encrypted MiniFish profiles and persisted job queue.

MINIFISH_DATABASE_URL supports a dedicated PostgreSQL database for real durability.
Local SQLite is a development/degraded fallback: free Render filesystem is ephemeral.
No credential, cookie or task payload is logged or sent to the browser tool response.
"""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import os
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken

NAME_RE = re.compile(r'^[A-Za-z0-9_-]{1,40}$')
MAX_STATE_SIZE = 750_000
MAX_JOB_SIZE = 35_000


class Store:
    def __init__(self, *, database_url: str | None = None,
                 sqlite_path: str | None = None, secret: str | None = None):
        secret = secret if secret is not None else os.getenv('MINIFISH_SECRET', '')
        if len(secret) < 32:
            raise RuntimeError('MINIFISH_SECRET must be at least 32 characters')
        key = base64.urlsafe_b64encode(hashlib.sha256(
            b'MiniFish encrypted profiles and jobs v1:' + secret.encode()).digest())
        self.cipher = Fernet(key)
        self.url = database_url if database_url is not None else os.getenv('MINIFISH_DATABASE_URL', '')
        self.is_postgres = bool(self.url)
        self.durable = self.is_postgres or os.getenv('MINIFISH_PERSISTENT_DISK') == '1'
        self.sqlite_path = sqlite_path or os.getenv('MINIFISH_SQLITE_PATH', '/tmp/minifish-state.sqlite3')
        self._lock = threading.RLock()
        self._setup()

    @contextmanager
    def connect(self):
        if self.is_postgres:
            import psycopg
            with psycopg.connect(self.url, connect_timeout=10) as con:
                yield con
        else:
            Path(self.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.sqlite_path, timeout=10) as con:
                con.execute('PRAGMA busy_timeout=10000')
                yield con

    def sql(self, statement: str) -> str:
        return statement.replace('?', '%s') if self.is_postgres else statement

    def execute(self, statement: str, params: tuple = (), *, fetch: bool = False):
        with self._lock, self.connect() as con:
            cur = con.execute(self.sql(statement), params)
            return cur.fetchall() if fetch else cur.rowcount

    def _setup(self):
        blob = 'BYTEA' if self.is_postgres else 'BLOB'
        self.execute(f'''CREATE TABLE IF NOT EXISTS mf_profiles (
            name TEXT PRIMARY KEY, site TEXT NOT NULL,
            encrypted_state {blob} NOT NULL, updated DOUBLE PRECISION NOT NULL)''')
        self.execute(f'''CREATE TABLE IF NOT EXISTS mf_jobs (
            id TEXT PRIMARY KEY, status TEXT NOT NULL, profile TEXT,
            site TEXT NOT NULL, encrypted_plan {blob} NOT NULL,
            run_at DOUBLE PRECISION NOT NULL, created DOUBLE PRECISION NOT NULL,
            updated DOUBLE PRECISION NOT NULL, progress INTEGER NOT NULL DEFAULT 0,
            total INTEGER NOT NULL, summary TEXT NOT NULL DEFAULT '')''')
        self.execute(f'''CREATE TABLE IF NOT EXISTS mf_job_results (
            id TEXT PRIMARY KEY, encrypted_result {blob} NOT NULL,
            updated DOUBLE PRECISION NOT NULL)''')
        self.execute('''CREATE TABLE IF NOT EXISTS mf_allowed_domains (
            domain TEXT PRIMARY KEY, added DOUBLE PRECISION NOT NULL)''')
        # Interrupted runs are not automatically retried; clicks might not be idempotent.
        self.execute("UPDATE mf_jobs SET status='interrupted', summary='Сервер перезапущен; повторный запуск только вручную' WHERE status='running'")

    @staticmethod
    def profile_name(name):
        if not isinstance(name, str) or not NAME_RE.fullmatch(name):
            raise ValueError('Имя профиля: 1–40 латинских букв, цифр, _ или -')
        return name

    def _encrypt(self, obj, max_size):
        raw = json.dumps(obj, ensure_ascii=False, separators=(',', ':')).encode()
        if len(raw) > max_size:
            raise ValueError('Сохранённые данные слишком большие')
        return self.cipher.encrypt(raw)

    def _decrypt(self, data):
        try:
            return json.loads(self.cipher.decrypt(bytes(data)))
        except (InvalidToken, ValueError, TypeError) as exc:
            raise ValueError('Не удалось расшифровать данные. Проверьте MINIFISH_SECRET.') from exc

    def save_domain(self, domain: str) -> None:
        if not isinstance(domain,str) or not re.fullmatch(
                r'[a-z0-9-]+(?:\.[a-z0-9-]+)+',domain) or len(domain)>253:
            raise ValueError('Некорректное имя домена')
        try:
            ipaddress.ip_address(domain)
        except ValueError:
            pass
        else:
            raise ValueError('Числовой IP нельзя сохранять как домен')
        self.execute('''INSERT INTO mf_allowed_domains (domain,added) VALUES (?,?)
                        ON CONFLICT(domain) DO NOTHING''',(domain,time.time()))

    def list_domains(self) -> list[str]:
        return [r[0] for r in self.execute(
            'SELECT domain FROM mf_allowed_domains ORDER BY added',fetch=True)]

    def save_profile(self, name: str, site: str, state: dict):
        self.profile_name(name)
        encrypted = self._encrypt(state, MAX_STATE_SIZE)
        now = time.time()
        self.execute('''INSERT INTO mf_profiles (name,site,encrypted_state,updated)
            VALUES (?,?,?,?) ON CONFLICT (name) DO UPDATE SET
            site=excluded.site, encrypted_state=excluded.encrypted_state,updated=excluded.updated''',
            (name, site, encrypted, now))
        return {'name': name, 'site': site, 'updated': now, 'durable': self.durable}

    def get_profile(self, name: str):
        self.profile_name(name)
        rows = self.execute('SELECT site,encrypted_state FROM mf_profiles WHERE name=?',
                            (name,), fetch=True)
        if not rows:
            raise ValueError('Профиль не найден')
        return {'site': rows[0][0], 'state': self._decrypt(rows[0][1])}

    def list_profiles(self):
        rows = self.execute('SELECT name,site,updated FROM mf_profiles ORDER BY updated DESC', fetch=True)
        return [{'name': n, 'site': site, 'updated': date} for n, site, date in rows]

    def delete_profile(self, name: str):
        self.profile_name(name)
        return {'deleted': self.execute('DELETE FROM mf_profiles WHERE name=?', (name,)) > 0}

    def enqueue(self, *, profile: str | None, site: str, steps: list,
                run_at: float):
        if profile:
            self.profile_name(profile)
            self.get_profile(profile)
        if len(self.list_jobs()) >= 50:
            raise ValueError('Лимит истории очереди — 50 задач')
        job_id = str(uuid4())
        encrypted = self._encrypt(steps, MAX_JOB_SIZE)
        now = time.time()
        self.execute('''INSERT INTO mf_jobs
            (id,status,profile,site,encrypted_plan,run_at,created,updated,progress,total)
            VALUES (?,'queued',?,?,?,?,?,?,0,?)''',
            (job_id, profile, site, encrypted, run_at, now, now, len(steps)))
        return {'id': job_id, 'status': 'queued', 'run_at': run_at,
                'steps': len(steps), 'durable': self.durable}

    def list_jobs(self):
        rows = self.execute('''SELECT id,status,profile,site,run_at,created,updated,progress,total,summary
                               FROM mf_jobs ORDER BY created DESC LIMIT 50''', fetch=True)
        keys = ('id','status','profile','site','run_at','created','updated','progress','total','summary')
        return [dict(zip(keys, r)) for r in rows]

    def get_job(self, job_id: str):
        rows = self.execute('''SELECT id,status,profile,site,run_at,created,updated,progress,total,summary
                               FROM mf_jobs WHERE id=?''',(job_id,), fetch=True)
        if not rows:
            raise ValueError('Задача не найдена')
        return dict(zip(('id','status','profile','site','run_at','created','updated','progress','total','summary'),rows[0]))

    def due_ids(self):
        return [r[0] for r in self.execute(
            "SELECT id FROM mf_jobs WHERE status='queued' AND run_at<=? ORDER BY run_at LIMIT 5",
            (time.time(),), fetch=True)]

    def claim(self, job_id: str):
        if not self.execute("UPDATE mf_jobs SET status='running',updated=? WHERE id=? AND status='queued'",
                            (time.time(),job_id)):
            return None
        rows = self.execute('SELECT profile,site,encrypted_plan FROM mf_jobs WHERE id=?',
                            (job_id,),fetch=True)
        profile, site, payload = rows[0]
        return {'profile': profile,'site': site,'steps': self._decrypt(payload)}

    def set_job(self, job_id: str, status: str, *, progress: int | None = None, summary: str = ''):
        if status not in ('queued','running','done','failed','interrupted','cancelled'):
            raise ValueError('Некорректный статус')
        if progress is None:
            self.execute('UPDATE mf_jobs SET status=?,updated=?,summary=? WHERE id=?',
                         (status,time.time(),summary[:200],job_id))
        else:
            self.execute('UPDATE mf_jobs SET status=?,updated=?,progress=?,summary=? WHERE id=?',
                         (status,time.time(),int(progress),summary[:200],job_id))

    def save_job_result(self, job_id: str, result: dict):
        self.get_job(job_id)
        blob = self._encrypt(result, 12_000)
        self.execute('''INSERT INTO mf_job_results (id,encrypted_result,updated)
            VALUES (?,?,?) ON CONFLICT (id) DO UPDATE SET
            encrypted_result=excluded.encrypted_result,updated=excluded.updated''',
            (job_id, blob, time.time()))

    def get_job_result(self, job_id: str):
        info = self.get_job(job_id)
        rows = self.execute('SELECT encrypted_result FROM mf_job_results WHERE id=?',
                            (job_id,), fetch=True)
        return {'job': info, 'result': self._decrypt(rows[0][0]) if rows else None}

    def cancel(self, job_id: str):
        self.get_job(job_id)
        n = self.execute("UPDATE mf_jobs SET status='cancelled',updated=? WHERE id=? AND status='queued'",
                         (time.time(),job_id))
        if not n:
            raise ValueError('Можно отменить только задачу в очереди')
        return {'id': job_id, 'status': 'cancelled'}
