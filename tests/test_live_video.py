"""Authenticated live video WebSocket transport tests (no real cookies)."""
import asyncio
import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.websockets import WebSocketDisconnect

from live_video import same_origin, screencast_socket, _viewing
from engine import BrowserEngine, Session


def fake_socket(origin='https://nxval-minifish-2026.onrender.com'):
    return SimpleNamespace(
        headers={'origin': origin, 'host': 'nxval-minifish-2026.onrender.com'},
        query_params={'session_id':'b2c0ce16-c4e0-4e2d-87e5-230b2ca5b123'},
        accept=AsyncMock(), close=AsyncMock(), send_bytes=AsyncMock(),
        send_json=AsyncMock())


def test_video_socket_requires_same_origin():
    assert same_origin(fake_socket())
    assert not same_origin(fake_socket('https://attacker.example'))
    assert not same_origin(fake_socket(''))


@pytest.mark.asyncio
async def test_live_video_rejects_missing_owner():
    ws=fake_socket()
    await screencast_socket(SimpleNamespace(), lambda request: False)(ws)
    ws.close.assert_awaited_once_with(code=1008)
    ws.accept.assert_not_awaited()


@pytest.mark.asyncio
async def test_stream_delivers_binary_frame_and_closes_cdp():
    ws=fake_socket()
    payload=b'jpeg-test-data'
    class FakeCDP:
        def __init__(self):
            self.listeners={}
            self.messages=[]
            self.detach=AsyncMock()
        def on(self,event,func):
            self.listeners[event]=func
        async def send(self,command,params=None):
            self.messages.append(command)
            if command=='Page.startScreencast':
                self.listeners['Page.screencastFrame']({
                    'data':base64.b64encode(payload).decode(),
                    'sessionId':1})
    cdp=FakeCDP()
    page=SimpleNamespace(url='https://example.com/',is_closed=lambda:False)
    context=SimpleNamespace(new_cdp_session=AsyncMock(return_value=cdp))
    engine=BrowserEngine()
    engine._sessions[ws.query_params['session_id']]=Session(context=context,page=page)
    ws.send_bytes.side_effect=WebSocketDisconnect(1000)
    await screencast_socket(engine,lambda request:True)(ws)
    ws.accept.assert_awaited_once()
    ws.send_bytes.assert_awaited_once_with(payload)
    assert 'Page.startScreencast' in cdp.messages
    assert 'Page.stopScreencast' in cdp.messages
    cdp.detach.assert_awaited_once()
    assert ws.query_params['session_id'] not in _viewing
