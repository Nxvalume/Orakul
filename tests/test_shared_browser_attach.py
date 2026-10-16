"""MCP and owner panel attach to one existing Telegram Chromium session.

A persisted checkpoint is for recovery after restart, never a reason to
replace a live login or invalidate the owner's browser view.
"""
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("logged_in,profile", [
    (False, None),
    (True, "telegram"),
])
async def test_telegram_reuses_live_owner_context_even_with_stored_profile(monkeypatch, logged_in, profile):
    import server

    url = "https://web.telegram.org/k/"
    page = SimpleNamespace(
        url=url,
        title=AsyncMock(return_value="Telegram"),
        is_closed=lambda: False,
    )
    existing = SimpleNamespace(page=page, profile_name=profile,
                               private_mode=False, touched=time.monotonic())
    monkeypatch.setattr(server.engine, "_sessions", {"shared-id": existing})
    monkeypatch.setattr(server.engine, "telegram_session_id", lambda: "shared-id")

    open_new = AsyncMock(side_effect=AssertionError("A live session must not be replaced"))
    close = AsyncMock(side_effect=AssertionError("A live session must not be closed"))
    monkeypatch.setattr(server.engine, "open", open_new)
    monkeypatch.setattr(server.engine, "close", close)
    monkeypatch.setattr(server.store, "get_profile",
                        lambda name: (_ for _ in ()).throw(
                            AssertionError("Saved state must not replace the live context")))

    result = await server._open_telegram(url)

    assert result == {
        "session_id": "shared-id", "url": url, "title": "Telegram",
        "profile": profile, "reused": True,
    }
    open_new.assert_not_awaited()
    close.assert_not_awaited()


@pytest.mark.asyncio
async def test_telegram_owner_private_login_cannot_be_attached_by_mcp(monkeypatch):
    import server

    url = "https://web.telegram.org/k/"
    private = SimpleNamespace(
        page=SimpleNamespace(url=url, is_closed=lambda: False),
        profile_name=None, private_mode=True, touched=time.monotonic(),
    )
    monkeypatch.setattr(server.engine, "_sessions", {"private-id": private})
    monkeypatch.setattr(server.engine, "telegram_session_id", lambda: "private-id")
    open_new = AsyncMock()
    close = AsyncMock()
    monkeypatch.setattr(server.engine, "open", open_new)
    monkeypatch.setattr(server.engine, "close", close)
    with pytest.raises(PermissionError, match="Личный режим владельца"):
        await server._open_telegram(url)
    open_new.assert_not_awaited()
    close.assert_not_awaited()


@pytest.mark.asyncio
async def test_telegram_restores_saved_state_only_after_live_context_disappears(monkeypatch):
    import server

    url = "https://web.telegram.org/k/"
    state = {"cookies": [], "origins": []}
    monkeypatch.setattr(server.engine, "_sessions", {})
    monkeypatch.setattr(server.engine, "telegram_session_id", lambda: None)
    monkeypatch.setattr(server.store, "get_profile",
                        lambda name: {"site": "web.telegram.org", "state": state})
    opener = AsyncMock(return_value={"session_id": "restored"})
    monkeypatch.setattr(server.engine, "open", opener)

    assert await server._open_telegram(url) == {"session_id": "restored"}
    opener.assert_awaited_once_with(url, storage_state=state, profile_name="telegram")
