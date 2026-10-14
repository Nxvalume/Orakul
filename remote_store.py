"""Supabase free Edge Function-backed encrypted MiniFish state store.

All session cookies and task plans are encrypted before sending. The Edge Function
authenticates an independent server token and accepts only bounded database operations.
"""
from __future__ import annotations
import base64
import os
import re
import httpx
from state_store import Store

TABLES = ('mf_profiles','mf_jobs','mf_job_results','mf_allowed_domains')

class RemoteStore(Store):
    def __init__(self):
        self.gateway_url = os.getenv('MINIFISH_STORE_API_URL','').strip()
        self.gateway_token = os.getenv('MINIFISH_STORE_API_TOKEN','').strip()
        if (not self.gateway_url.startswith('https://')
                or len(self.gateway_token) < 64):
            raise RuntimeError('HTTPS storage gateway credentials missing')
        super().__init__(database_url='')
        self.durable = True

    def _setup(self):
        # Tables and their private schema are created using Supabase migrations,
        # not dynamically via untrusted HTTP requests.
        self.execute("UPDATE mf_jobs SET status='interrupted', summary='Сервер перезапущен; повторный запуск только вручную' WHERE status='running'")

    def sql(self, statement: str) -> str:
        for table in TABLES:
            statement = re.sub(r'\b' + table + r'\b', 'minifish.' + table, statement)
        index = 0
        def substitute(match):
            nonlocal index
            index += 1
            return chr(36) + str(index)
        return re.sub(r'\?', substitute, statement)

    def execute(self, statement: str, params: tuple = (), *, fetch: bool = False):
        def encode(value):
            if isinstance(value, bytes):
                return {'binary': base64.b64encode(value).decode('ascii')}
            return value

        try:
            response = httpx.post(self.gateway_url,
                headers={'x-minifish-token': self.gateway_token},
                json={'sql': self.sql(statement),
                      'params': [encode(v) for v in params], 'fetch': bool(fetch)},
                timeout=15, follow_redirects=False)
            response.raise_for_status()
            result = response.json()
            if not result.get('ok'):
                raise RuntimeError('Gateway rejected operation')
            if fetch:
                def decode(value):
                    if isinstance(value,dict) and set(value) == {'binary'}:
                        return base64.b64decode(value['binary'], validate=True)
                    return value
                return [tuple(decode(v) for v in row) for row in result['rows']]
            return int(result['rowcount'])
        except Exception as exc:
            # No URLs/tokens/request bodies in exceptions.
            raise RuntimeError('Storage gateway unavailable (' + type(exc).__name__ + ')') from None
