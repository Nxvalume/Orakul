"""MCP Telegram status must not expose credentials or inspect private login."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest


@pytest.mark.asyncio
async def test_status_private_owner_mode_does_not_inspect_page(monkeypatch):
    import server
    session = SimpleNamespace(private_mode=True)
    monkeypatch.setattr(server.engine, 'telegram_session_id', lambda: 'test-session')
    monkeypatch.setattr(server.engine, '_sessions', {'test-session':session})
    login = AsyncMock()
    monkeypatch.setattr(server.engine, 'telegram_logged_in', login)
    result = await server.browser_telegram_status.fn()
    assert result['phase'] == 'private_login'
    assert result['saved'] is None
    assert result['storage'] == 'not_checked'
    login.assert_not_awaited()


@pytest.mark.asyncio
async def test_status_authenticated_verifies_encrypted_profile(monkeypatch):
    import server
    session = SimpleNamespace(private_mode=False)
    monkeypatch.setattr(server.engine, 'telegram_session_id', lambda: 'test-session')
    monkeypatch.setattr(server.engine, '_sessions', {'test-session':session})
    monkeypatch.setattr(server.engine, 'telegram_logged_in', AsyncMock(return_value=True))
    monkeypatch.setattr(server.engine, 'telegram_authenticated_state',
                        AsyncMock(return_value={'cookies': [], 'origins': []}))
    saved = []
    def get_profile(name):
        if not saved: raise ValueError('not found')
        return {'site':'web.telegram.org'}
    monkeypatch.setattr(server.store, 'get_profile', get_profile)
    monkeypatch.setattr(server.store, 'durable', True, raising=False)
    monkeypatch.setattr(server.store, 'degraded', False, raising=False)
    checkpoint = AsyncMock(side_effect=lambda name,state: saved.append(name))
    monkeypatch.setattr(server, '_checkpoint_browser_profile',checkpoint)
    result = await server.browser_telegram_status.fn()
    assert result['phase'] == 'authenticated'
    assert result['saved'] is True
    assert result['storage'] == 'ok'
    checkpoint.assert_awaited_once_with('telegram',{'cookies': [], 'origins': []})


@pytest.mark.asyncio
async def test_status_no_session_leaves_storage_untouched(monkeypatch):
    import server
    monkeypatch.setattr(server.engine, 'telegram_session_id', lambda: None)
    result = await server.browser_telegram_status.fn()
    assert result == {'phase':'not_open','logged_in':False,
                      'saved':False,'storage':'not_checked','session_id':None}
