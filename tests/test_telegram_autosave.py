"""Telegram auto-checkpoint must save auth before private browser is released."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import asyncio
import pytest


@pytest.mark.asyncio
async def test_telegram_autosave_persists_private_login_and_releases_owner(monkeypatch):
    import server
    sid = 'test-telegram-owner'
    session = SimpleNamespace(private_mode=True)
    monkeypatch.setattr(server.engine, '_sessions', {sid: session})
    monkeypatch.setattr(server.engine, 'telegram_session_id', lambda: sid)
    state = {'cookies': [{'name': 'synthetic'}], 'origins': []}
    monkeypatch.setattr(server.engine, 'telegram_authenticated_state', AsyncMock(return_value=state))
    save = AsyncMock()
    release = AsyncMock(return_value=True)
    rename = Mock()
    monkeypatch.setattr(server, '_checkpoint_browser_profile', save)
    monkeypatch.setattr(server.engine, 'release_verified_telegram_login', release)
    monkeypatch.setattr(server.engine, 'set_profile_name', rename)
    monkeypatch.setattr(server.store, 'durable', True, raising=False)
    monkeypatch.setattr(server.store, 'degraded', False, raising=False)
    ticks = 0
    async def one_iteration(seconds):
        nonlocal ticks
        ticks += 1
        if ticks > 1:
            raise asyncio.CancelledError()
    monkeypatch.setattr(server.asyncio, 'sleep', one_iteration)
    with pytest.raises(asyncio.CancelledError):
        await server._telegram_profile_watch()
    save.assert_awaited_once_with('telegram', state)
    rename.assert_called_once_with(sid, 'telegram')
    release.assert_awaited_once_with(sid)


@pytest.mark.asyncio
async def test_telegram_autosave_does_not_persist_qr_login_page(monkeypatch):
    import server
    sid = 'test-unauthed'
    monkeypatch.setattr(server.engine, 'telegram_session_id', lambda: sid)
    monkeypatch.setattr(server.engine, '_sessions', {sid: SimpleNamespace(private_mode=True)})
    monkeypatch.setattr(server.engine, 'telegram_authenticated_state', AsyncMock(return_value=None))
    save = AsyncMock()
    monkeypatch.setattr(server, '_checkpoint_browser_profile', save)
    ticks = 0
    async def one_iteration(seconds):
        nonlocal ticks
        ticks += 1
        if ticks > 1:
            raise asyncio.CancelledError()
    monkeypatch.setattr(server.asyncio, 'sleep', one_iteration)
    with pytest.raises(asyncio.CancelledError):
        await server._telegram_profile_watch()
    save.assert_not_awaited()
