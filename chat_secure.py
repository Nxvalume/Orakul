"""Owner-only secret input channel from an embedded MCP Apps browser window.

Secrets go directly over HTTPS to the MiniFish server. They NEVER enter
MCP tool arguments, model-visible results, cookies, URL query or app logs.
The channel uses a short-lived HMAC owner capability bound to one browser
session and the iframe's HTTPS Origin. It is active only in private mode.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from urllib.parse import urlsplit

from starlette.responses import JSONResponse, Response
from web_auth import allowed_attempt, verify_password

_LIMIT = 12 * 60
_UUID = re.compile(r'^[0-9a-f-]{36}$')
_HOST = {'chatgpt.com', 'chat.openai.com'}


def trusted_chat_origin(origin: str) -> bool:
    try:
        p = urlsplit(origin)
        host = (p.hostname or '').lower()
        return (
            p.scheme == 'https' and not p.username and not p.password
            and p.port in (None, 443)
            and (host in _HOST or host.endswith('.chatgpt.com')
                 or host.endswith('.oaiusercontent.com'))
        )
    except (TypeError, ValueError):
        return False


def _secret() -> bytes:
    value = os.getenv('MINIFISH_SECRET', '')
    if len(value) < 32:
        raise RuntimeError('MiniFish server key is missing')
    return value.encode()


def _seal(sid: str, origin: str) -> str:
    payload = json.dumps({
        'v': 1, 'sid': sid, 'origin': origin,
        'exp': int(time.time() + _LIMIT),
        'nonce': secrets.token_hex(12),
    }, separators=(',', ':')).encode()
    body = base64.urlsafe_b64encode(payload).decode().rstrip('=')
    sig = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    return body + '.' + sig


def _valid(token: str, sid: str, origin: str) -> bool:
    if not isinstance(token, str) or not 60 <= len(token) <= 900 or not _UUID.fullmatch(sid):
        return False
    try:
        raw, signature = token.rsplit('.', 1)
        expected = hmac.new(_secret(), raw.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return False
        payload = json.loads(base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4)))
        return (payload.get('v') == 1 and payload.get('sid') == sid
                and payload.get('origin') == origin
                and isinstance(payload.get('exp'), int)
                and time.time() <= payload['exp'] <= time.time() + _LIMIT + 5)
    except (ValueError, TypeError, UnicodeError, KeyError):
        return False


def _cors(origin: str) -> dict:
    return {
        'Access-Control-Allow-Origin': origin,
        'Vary': 'Origin',
        'Access-Control-Allow-Headers': 'Content-Type, X-MiniFish-Owner',
        'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
        'Access-Control-Max-Age': '600',
        'Cache-Control': 'no-store',
    }


def create_owner_routes(engine):
    async def owner_secure(req):
        origin = req.headers.get('origin', '')
        if not trusted_chat_origin(origin):
            return JSONResponse({'error': 'Недопустимый источник'}, status_code=403)
        headers = _cors(origin)
        if req.method == 'OPTIONS':
            return Response(status_code=204, headers=headers)
        if req.headers.get('content-length', '0').isdecimal() and int(req.headers.get('content-length', '0')) > 4096:
            return JSONResponse({'error': 'Слишком большой запрос'}, status_code=413, headers=headers)
        operation = req.path_params['operation']
        try:
            if operation == 'frame':
                sid = req.query_params.get('session_id', '')
                token = req.headers.get('x-minifish-owner', '')
                if not _valid(token, sid, origin):
                    return JSONResponse({'error': 'Требуется приватный вход'}, status_code=401, headers=headers)
                session = engine.get(sid, owner=True)
                if not session.private_mode:
                    return JSONResponse({'error': 'Личный режим завершён'}, status_code=403, headers=headers)
                png = await engine.live_jpeg(sid)
                return Response(png, media_type='image/jpeg', headers=headers)

            if req.method != 'POST':
                return JSONResponse({'error': 'Метод не разрешён'}, status_code=405, headers=headers)
            data = await req.json()
            if not isinstance(data, dict):
                return JSONResponse({'error': 'Неверный запрос'}, status_code=400, headers=headers)
            sid = data.get('session_id', '')
            if not isinstance(sid, str) or not _UUID.fullmatch(sid):
                return JSONResponse({'error': 'Неверная сессия'}, status_code=400, headers=headers)

            if operation == 'unlock':
                password = data.get('owner_password')
                ip = req.client.host if req.client else 'unknown'
                if (not isinstance(password, str) or len(password) > 500
                        or not allowed_attempt(ip) or not verify_password(password, ip)):
                    return JSONResponse({'error': 'Неверный пароль MiniFish или лимит попыток'}, status_code=401, headers=headers)
                result = await engine.owner_set_private(sid, True)
                return JSONResponse({'token': _seal(sid, origin),
                                     'expires_seconds': _LIMIT,
                                     'private_mode': result['private_mode']}, headers=headers)

            token = req.headers.get('x-minifish-owner', '')
            if not _valid(token, sid, origin):
                return JSONResponse({'error': 'Защищённый доступ истёк'}, status_code=401, headers=headers)
            session = engine.get(sid, owner=True)
            if not session.private_mode:
                return JSONResponse({'error': 'Личный режим не активен'}, status_code=403, headers=headers)

            if operation == 'fields':
                result = await engine.owner_fields(sid)
                result['viewport'] = session.page.viewport_size or {'width': 960, 'height': 675}
                return JSONResponse(result, headers=headers)
            if operation == 'control':
                action = data.get('action', '')
                if action not in {'click', 'fill_field', 'key', 'scroll', 'telegram_open', 'navigate'}:
                    return JSONResponse({'error': 'Неизвестное действие'}, status_code=400, headers=headers)
                if action == 'telegram_open':
                    # Owner-requested navigation only; never expose this private page via MCP.
                    # The URL is fixed to Telegram Web, not supplied by the caller.
                    result = await engine.owner_control(
                        sid, 'navigate', url='https://web.telegram.org/k/')
                else:
                    result = await engine.owner_control(
                        sid, action, x=data.get('x'), y=data.get('y'),
                        field_index=data.get('field_index'), text=data.get('text'),
                        key=data.get('key'), pixels=data.get('pixels'),
                        url=data.get('url'))
                return JSONResponse(result, headers=headers)
            if operation == 'finish':
                result = await engine.owner_set_private(sid, False)
                return JSONResponse({
                    'private_mode': result['private_mode'],
                    'profile_saved': result['profile_saved'],
                    'save_error': result['save_error'],
                }, headers=headers)
            return JSONResponse({'error': 'Неизвестное действие'}, status_code=404, headers=headers)
        except (ValueError, RuntimeError, PermissionError) as err:
            # Human-readable but NEVER include page HTML, passwords or codes.
            return JSONResponse({'error': str(err)[:180]}, status_code=400, headers=headers)
        except Exception as err:
            return JSONResponse({'error': 'Ошибка защищённого интерфейса ('+
                                  type(err).__name__+')'}, status_code=502, headers=headers)
    return owner_secure
