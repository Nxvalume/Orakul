"""Exercise the inline private-control channel through the real HTTP router."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from starlette.applications import Starlette
from starlette.routing import Route

from chat_secure import create_owner_routes


@pytest.mark.asyncio
async def test_inline_private_mode_request_flow(monkeypatch):
    monkeypatch.setenv('MINIFISH_SECRET', 'test-fixture-signing-secret-1234567890123456789')
    monkeypatch.setattr('chat_secure.allowed_attempt', lambda ip: True)
    monkeypatch.setattr('chat_secure.verify_password', lambda value, ip: value == 'test-owner-only')
    sid = '2b524552-1881-4433-a1af-0a3f49acd831'
    session = SimpleNamespace(private_mode=False,
                              page=SimpleNamespace(viewport_size={'width':960,'height':675}))

    async def private(session_id, enabled):
        assert session_id == sid
        session.private_mode = enabled
        return {'private_mode':enabled, 'profile_saved':not enabled,'save_error':None}

    engine = SimpleNamespace(
        get=lambda session_id, owner=False: session,
        owner_set_private=private,
        owner_fields=AsyncMock(return_value={'site':'example.com','fields':[{
            'kind':'text','index':0,'label':'Example field'}]}),
        owner_control=AsyncMock(return_value={'ok':True}),
        live_jpeg=AsyncMock(return_value=b'\xff\xd8\xff\xd9'),
    )
    app = Starlette(routes=[Route('/chat/secure/{operation}',
                  create_owner_routes(engine),methods=['GET','POST','OPTIONS'])])
    origin = 'https://chatgpt.com'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url='https://minifish.example') as client:
        wrong = await client.post('/chat/secure/unlock',
            headers={'Origin':'https://untrusted.example'},
            json={'session_id':sid,'owner_password':'test-owner-only'})
        assert wrong.status_code == 403
        response = await client.post('/chat/secure/unlock',
            headers={'Origin':origin},
            json={'session_id':sid,'owner_password':'test-owner-only'})
        assert response.status_code == 200
        assert 'test-owner-only' not in response.text
        token = response.json()['token']
        headers = {'Origin':origin,'X-MiniFish-Owner':token}
        fields = await client.post('/chat/secure/fields',headers=headers,
                                   json={'session_id':sid})
        assert fields.status_code == 200
        assert fields.json()['viewport']['width'] == 960
        result = await client.post('/chat/secure/control',headers=headers,
            json={'session_id':sid,'action':'fill_field','field_index':0,
                  'text':'example-input'})
        assert result.status_code == 200
        assert 'example-input' not in result.text
        frame = await client.get('/chat/secure/frame?session_id='+sid,headers=headers)
        assert frame.status_code == 200
        assert frame.headers['content-type'].startswith('image/jpeg')
        close = await client.post('/chat/secure/finish',headers=headers,
            json={'session_id':sid})
        assert close.status_code == 200
        assert close.json()['profile_saved'] is True
        assert not session.private_mode
        replay = await client.post('/chat/secure/fields',headers=headers,
            json={'session_id':sid})
        assert replay.status_code == 403
