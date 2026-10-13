"""Owner-approved OAuth 2.1 PKCE for a private ChatGPT MCP connection.

This deployment intentionally only accepts ChatGPT redirect URIs. No general
public user registration, arbitrary redirect clients, or anonymous MCP access.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import time
from urllib.parse import parse_qs, urlsplit, urlencode

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse

from web_auth import SECRET, allowed_attempt, verify_password, authorized

BASE = os.getenv('MINIFISH_PUBLIC_URL', 'https://nxval-minifish-2026.onrender.com').rstrip('/')
RESOURCE = BASE
SCOPES = 'browser:read browser:act'
CHALLENGE = f'Bearer resource_metadata="{BASE}/.well-known/oauth-protected-resource", scope="browser:read browser:act"'
# Authorization codes are one use, short lived, and never stored in logs.
_codes: dict[str, dict] = {}


def encode_bytes(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip('=')


def decode_bytes(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))


def sign(payload: dict) -> str:
    raw = encode_bytes(json.dumps(payload, separators=(',', ':'), sort_keys=True).encode())
    mac = encode_bytes(hmac.new(SECRET.encode(), raw.encode(), hashlib.sha256).digest())
    return f'mf1.{raw}.{mac}'


def verify_signed(token: str, kind: str) -> dict | None:
    try:
        version, raw, mac = token.split('.')
        if version != 'mf1' or len(token) > 8000:
            return None
        expected = hmac.new(SECRET.encode(), raw.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(decode_bytes(mac), expected):
            return None
        data = json.loads(decode_bytes(raw))
        if not isinstance(data, dict) or data.get('kind') != kind:
            return None
        now = time.time()
        if not (float(data.get('iat', 0)) <= now + 30 < float(data.get('exp', 0)) + 30):
            return None
        return data
    except (ValueError, TypeError, KeyError, OverflowError, json.JSONDecodeError):
        return None


def authorized_access(value: str) -> bool:
    data = verify_signed(value, 'access')
    return bool(data and data.get('aud') == RESOURCE and {'browser:read', 'browser:act'} <= set(data.get('scope', '').split()))


def client_redirect_allowed(uri: str) -> bool:
    try:
        p = urlsplit(uri)
        return (p.scheme == 'https' and p.netloc == 'chatgpt.com' and
                not p.query and not p.fragment and (
                    p.path == '/connector_platform_oauth_redirect' or
                    bool(re.fullmatch(r'/connector/oauth/[A-Za-z0-9_-]{8,128}', p.path))
                ))
    except ValueError:
        return False


def client_id_allowed(client_id: str, redirect: str) -> bool:
    if not client_redirect_allowed(redirect):
        return False
    if client_id in ('https://chatgpt.com/oauth/client.json',):
        return True
    if re.fullmatch(r'https://chatgpt.com/oauth/[A-Za-z0-9_-]{8,128}/client.json', client_id):
        return True
    # DCR clients are stateless and signed with server's secret.
    data = verify_signed(client_id, 'client')
    return bool(data and redirect in data.get('redirect_uris', []))


def bad(msg: str, code: int = 400):
    return JSONResponse({'error': msg}, status_code=code, headers={'Cache-Control': 'no-store'})


async def protected_resource(req: Request):
    return JSONResponse({'resource': RESOURCE, 'authorization_servers': [BASE],
                         'scopes_supported': SCOPES.split()})


async def oauth_metadata(req: Request):
    return JSONResponse({
        'issuer': BASE,
        'authorization_endpoint': BASE + '/oauth/authorize',
        'token_endpoint': BASE + '/oauth/token',
        'registration_endpoint': BASE + '/oauth/register',
        'response_types_supported': ['code'],
        'grant_types_supported': ['authorization_code', 'refresh_token'],
        'token_endpoint_auth_methods_supported': ['none'],
        'code_challenge_methods_supported': ['S256'],
        'scopes_supported': SCOPES.split(),
        'authorization_response_iss_parameter_supported': True,
    })


async def register(req: Request):
    if len(await req.body()) > 8000:
        return bad('invalid_client_metadata')
    try:
        data = await req.json()
        redirect_uris = data.get('redirect_uris')
        if (not isinstance(redirect_uris, list) or not 1 <= len(redirect_uris) <= 4 or
                not all(isinstance(x, str) and client_redirect_allowed(x) for x in redirect_uris) or
                data.get('token_endpoint_auth_method', 'none') != 'none'):
            return bad('invalid_redirect_uri')
        now = int(time.time())
        client_id = sign({'kind': 'client', 'redirect_uris': redirect_uris,
                          'iat': now, 'exp': now + 365 * 86400})
        return JSONResponse({'client_id': client_id, 'client_id_issued_at': now,
                             'token_endpoint_auth_method': 'none',
                             'redirect_uris': redirect_uris}, status_code=201,
                            headers={'Cache-Control': 'no-store'})
    except (ValueError, TypeError, AttributeError):
        return bad('invalid_client_metadata')


def validated_request(p: dict) -> dict | None:
    try:
        client = p.get('client_id', '')
        redirect = p.get('redirect_uri', '')
        state = p.get('state', '')
        challenge = p.get('code_challenge', '')
        resource = p.get('resource', RESOURCE)
        scopes = p.get('scope', SCOPES).split()
        if (p.get('response_type') != 'code' or p.get('code_challenge_method') != 'S256' or
            not re.fullmatch(r'[A-Za-z0-9_-]{43,128}', challenge) or not 8 <= len(state) <= 1024 or
            not client_id_allowed(client, redirect) or resource not in (RESOURCE, BASE + '/mcp') or
            not scopes or set(scopes) - set(SCOPES.split())):
            return None
        return {'client_id': client, 'redirect_uri': redirect, 'state': state,
                'code_challenge': challenge, 'resource': RESOURCE, 'scope': ' '.join(scopes)}
    except (TypeError, ValueError, AttributeError):
        return None


def make_ticket(params: dict) -> str:
    now = int(time.time())
    return sign({'kind': 'ticket', **params, 'iat': now, 'exp': now + 600})


async def authorize_get(req: Request):
    params = validated_request(dict(req.query_params))
    if not params:
        return bad('invalid_request')
    ticket = make_ticket(params)
    logged = authorized(req.headers.get('cookie', ''), '')
    pw = '' if logged else '<label for="pwd">Пароль владельца MiniFish</label><input id="pwd" name="password" type="password" required autocomplete="current-password" maxlength="1000">'
    body = ('''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'''
            '''<title>Подключить MiniFish к ChatGPT</title><style>body{background:#101820;color:#fafafa;font:16px system-ui;max-width:460px;margin:9vh auto;padding:24px;}'''
            '''main{background:#1e2935;border-radius:18px;padding:24px;}input,button{display:block;width:100%;box-sizing:border-box;padding:14px;margin-top:14px;border-radius:8px}button{background:#6bbfa6;color:#101820;border:0;font-weight:bold}</style></head>'''
            '<body><main><h2>Подключить MiniFish</h2><p>ChatGPT запрашивает управление браузером MiniFish. Доступ получит только подключённый ChatGPT-плагин.</p>'
            '<p>Разрешения: чтение страниц, переходы, клики и заполнение обычных полей. Финансовые и опасные действия требуют дополнительного подтверждения.</p>'
            '<form action="/oauth/authorize" method="post"><input type="hidden" name="ticket" value="' + html.escape(ticket, quote=True) + '">' +
            pw + '<button type="submit">Разрешить подключение</button></form></main></body></html>')
    return HTMLResponse(body, headers={'Cache-Control': 'no-store', 'Referrer-Policy':'no-referrer'})


async def authorize_post(req: Request):
    raw = await req.body()
    if len(raw) > 10000:
        return bad('invalid_request')
    try:
        form = parse_qs(raw.decode('utf-8'), keep_blank_values=True, max_num_fields=4)
        ticket = form.get('ticket', [''])[0]
        payload = verify_signed(ticket, 'ticket')
        if not payload:
            return bad('invalid_request')
        params = validated_request({'client_id': payload['client_id'], 'redirect_uri': payload['redirect_uri'],
                                    'state': payload['state'], 'response_type':'code',
                                    'code_challenge': payload['code_challenge'], 'code_challenge_method':'S256',
                                    'resource': payload['resource'], 'scope':payload['scope']})
        if not params:
            return bad('invalid_request')
        already_logged = authorized(req.headers.get('cookie', ''), '')
        if not already_logged:
            ip = req.client.host if req.client else 'unknown'
            if not allowed_attempt(ip):
                return bad('too_many_requests', 429)
            pwd = form.get('password', [''])[0]
            if not pwd or not verify_password(pwd, ip):
                return HTMLResponse('<h3>Неверный пароль MiniFish. Вернитесь назад и повторите попытку.</h3>', status_code=401)
        now = int(time.time())
        for key in list(_codes):
            if _codes[key]['exp'] < now:
                _codes.pop(key, None)
        if len(_codes) >= 64:
            return bad('authorization_temporarily_unavailable', 429)
        code = secrets.token_urlsafe(36)
        _codes[hashlib.sha256(code.encode()).hexdigest()] = {**params, 'exp': now + 300}
        query = urlencode({'code': code, 'state': params['state'], 'iss': BASE})
        return RedirectResponse(params['redirect_uri'] + '?' + query, status_code=303,
                                headers={'Cache-Control':'no-store', 'Referrer-Policy':'no-referrer'})
    except (KeyError, IndexError, TypeError, ValueError, UnicodeDecodeError):
        return bad('invalid_request')


def issue_tokens(info: dict, grant_refresh: bool = True) -> dict:
    now = int(time.time())
    base = {'client_id': info['client_id'], 'aud': RESOURCE, 'scope': info['scope'], 'iat': now}
    result = {'access_token': sign({**base, 'kind':'access', 'exp': now + 3600}),
              'token_type': 'Bearer', 'expires_in': 3600, 'scope': info['scope']}
    if grant_refresh:
        result['refresh_token'] = sign({**base, 'kind':'refresh', 'exp': now + 30*86400})
    return result


async def token(req: Request):
    raw = await req.body()
    if len(raw) > 12000:
        return bad('invalid_request')
    try:
        form = {k:v[0] for k,v in parse_qs(raw.decode(), max_num_fields=12).items()}
        grant = form.get('grant_type')
        client = form.get('client_id', '')
        if grant == 'authorization_code':
            code = form.get('code', '')
            info = _codes.pop(hashlib.sha256(code.encode()).hexdigest(), None)
            if not info or time.time() > info['exp'] or info['client_id'] != client or info['redirect_uri'] != form.get('redirect_uri'):
                return bad('invalid_grant')
            verifier = form.get('code_verifier', '')
            if not re.fullmatch(r'[A-Za-z0-9._~-]{43,128}', verifier):
                return bad('invalid_grant')
            calculated = encode_bytes(hashlib.sha256(verifier.encode()).digest())
            if not hmac.compare_digest(calculated, info['code_challenge']):
                return bad('invalid_grant')
            if form.get('resource', RESOURCE) not in (RESOURCE, BASE+'/mcp'):
                return bad('invalid_target')
            return JSONResponse(issue_tokens(info), headers={'Cache-Control':'no-store'})
        if grant == 'refresh_token':
            data = verify_signed(form.get('refresh_token',''), 'refresh')
            if not data or data.get('client_id') != client or data.get('aud') != RESOURCE:
                return bad('invalid_grant')
            return JSONResponse(issue_tokens(data), headers={'Cache-Control':'no-store'})
        return bad('unsupported_grant_type')
    except (ValueError, TypeError, UnicodeDecodeError):
        return bad('invalid_request')
