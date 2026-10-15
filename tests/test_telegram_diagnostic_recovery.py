"""The /healthz server probe must not block Telegram's single browser slot."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("saved_profile", [False, True])
async def test_telegram_open_retires_only_unprofiled_health_probe(monkeypatch, saved_profile):
    import server
    monkeypatch.setattr(server, 'validate_url', lambda url: url)
    page = SimpleNamespace(
        url='https://nxval-minifish-2026.onrender.com/healthz',
        is_closed=lambda: False,
    )
    probe = SimpleNamespace(page=page, private_mode=False, profile_name=None)
    monkeypatch.setattr(server.engine, '_sessions', {'probe': probe})
    monkeypatch.setattr(server.engine, 'telegram_session_id', lambda: None)
    close = AsyncMock(return_value={'closed': True})
    opened = AsyncMock(return_value={'session_id':'new-telegram', 'url':'https://web.telegram.org/k/'})
    monkeypatch.setattr(server.engine, 'close', close)
    monkeypatch.setattr(server.engine, 'open', opened)

    def saved(name):
        if not saved_profile:
            raise ValueError('profile missing')
        return {'site':'web.telegram.org', 'state':{'cookies':[], 'origins':[]}}
    monkeypatch.setattr(server.store, 'get_profile', saved)
    result = await server._open_telegram('https://web.telegram.org/k/')
    close.assert_awaited_once_with('probe')
    assert result['session_id'] == 'new-telegram'
    if saved_profile:
        assert opened.await_args.kwargs['profile_name'] == 'telegram'
    else:
        opened.assert_awaited_once_with('https://web.telegram.org/k/')


@pytest.mark.asyncio
@pytest.mark.parametrize("site,protected,profile", [
    ('https://example.com/', False, None),
    ('https://nxval-minifish-2026.onrender.com/healthz', True, None),
    ('https://nxval-minifish-2026.onrender.com/healthz', False, 'my_profile'),
    ('https://nxval-minifish-2026.onrender.com/live', False, None),
])
async def test_telegram_open_never_closes_non_diagnostic_session(monkeypatch, site, protected, profile):
    import server
    monkeypatch.setattr(server, 'validate_url', lambda url: url)
    session = SimpleNamespace(
        page=SimpleNamespace(url=site, is_closed=lambda:False),
        private_mode=protected, profile_name=profile)
    monkeypatch.setattr(server.engine, '_sessions', {'other': session})
    monkeypatch.setattr(server.engine, 'telegram_session_id', lambda: None)
    monkeypatch.setattr(server.store, 'get_profile', lambda name: (_ for _ in ()).throw(ValueError('missing')))
    close = AsyncMock()
    monkeypatch.setattr(server.engine, 'close', close)
    monkeypatch.setattr(server.engine, 'open', AsyncMock(return_value={'session_id':'new'}))
    await server._open_telegram('https://web.telegram.org/k/')
    close.assert_not_awaited()


def test_telegram_deeplink_ignores_existing_health_check_in_live_view():
    from live_view import PAGE
    assert "let telegramSession=list.find(x=>x.site==='web.telegram.org')" in PAGE
    assert "if(launchTelegramIfEmpty){launchTelegramIfEmpty=false;if(!telegramSession)" in PAGE
    assert "setTimeout(()=>$('openTelegram').click(),80)" in PAGE
    assert "telegramSession||list[0]?.session_id" in PAGE
    assert "Служебная проверка сервера" in PAGE
