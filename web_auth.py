"""Password login for the private MiniFish phone UI and bearer auth for MCP."""
from __future__ import annotations
import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict
from http.cookies import SimpleCookie

# Never use real default credentials when running publicly.
PASSWORD = os.getenv('MINIFISH_PASSWORD', '')
SECRET = os.getenv('MINIFISH_SECRET', '')
MCP_TOKEN = os.getenv('MINIFISH_MCP_TOKEN', '')

if not PASSWORD or not SECRET or len(SECRET) < 32:
    raise RuntimeError('MINIFISH_PASSWORD and MINIFISH_SECRET (32+ chars) are required')

failures: dict[str, list[float]] = defaultdict(list)
MAX_ATTEMPTS = 8
WINDOW = 900
SESSION_TTL = 7 * 24 * 3600

def allowed_attempt(ip: str) -> bool:
    now=time.time()
    failures[ip] = [t for t in failures[ip] if now-t < WINDOW]
    return len(failures[ip]) < MAX_ATTEMPTS

def verify_password(password: str, ip: str) -> bool:
    if not allowed_attempt(ip):
        return False
    ok = hmac.compare_digest(hashlib.sha256(password.encode()).digest(), hashlib.sha256(PASSWORD.encode()).digest())
    if not ok:
        failures[ip].append(time.time())
    else:
        failures.pop(ip, None)
    return ok

def make_cookie() -> str:
    timestamp = str(int(time.time()))
    msg = f'v1:{timestamp}'
    mac = hmac.new(SECRET.encode(),msg.encode(),hashlib.sha256).hexdigest()
    return f'{msg}:{mac}'

def check_cookie(value: str) -> bool:
    try:
        version,ts,signature=value.split(':')
        if version != 'v1' or not ts.isdecimal() or not 0 <= time.time()-int(ts) <= SESSION_TTL: return False
        msg=f'{version}:{ts}'
        expected=hmac.new(SECRET.encode(),msg.encode(),hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected,signature)
    except (ValueError,AttributeError,TypeError):return False

def authorized(cookie_header: str, authorization: str) -> bool:
    # Bearer optional for external MCP-compatible clients; no OAuth discovery yet.
    if MCP_TOKEN and authorization.startswith('Bearer '):
        return secrets.compare_digest(authorization[7:], MCP_TOKEN)
    try:
        cookies=SimpleCookie();cookies.load(cookie_header)
        return 'mf_session' in cookies and check_cookie(cookies['mf_session'].value)
    except Exception:return False
