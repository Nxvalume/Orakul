"""Security regressions for owner-only login, action approvals and profile key rotation."""
import asyncio
import time
from unittest.mock import Mock

import pytest

from engine import BrowserEngine, Session
from state_store import Store


@pytest.mark.asyncio
async def test_private_login_blocks_mcp_reads_but_allows_owner_actions():
    engine = BrowserEngine()
    page = Mock()
    page.url = 'https://web.telegram.org/k/'
    page.is_closed.return_value = False
    sid = 'test-private'
    engine._sessions[sid] = Session(context=None, page=page)
    result = await engine.owner_set_private(sid, True)
    assert result['private_mode'] is True
    with pytest.raises(PermissionError, match='Личный режим'):
        engine.get(sid)
    assert engine.get(sid, owner=True).private_mode
    result = await engine.owner_set_private(sid, False)
    assert not result['private_mode']
    assert engine.get(sid) is engine._sessions[sid]


@pytest.mark.asyncio
async def test_sensitive_approval_only_by_owner_and_single_use():
    engine = BrowserEngine()
    page = Mock()
    page.url = 'https://example.com/checkout'
    page.is_closed.return_value = False
    sid = 'test-approval'
    session = Session(context=None, page=page)
    engine._sessions[sid] = session
    session.pending_click = {
        'id':'test-nonce', 'selector':'button.confirm', 'url':page.url,
        'label':'Checkout', 'expires':time.monotonic()+60
    }
    with pytest.raises(ValueError):
        await engine.owner_approve_click(sid, 'wrong-nonce')
    approved = await engine.owner_approve_click(sid, 'test-nonce')
    assert approved['approved']
    assert session.approved_click['selector']=='button.confirm'
    assert session.pending_click is None
    assert (await engine.owner_reject_click(sid))['rejected']
    assert session.approved_click is None


def test_legacy_encrypted_profiles_survive_new_encryption_key(monkeypatch, tmp_path):
    monkeypatch.delenv('MINIFISH_PROFILE_ENCRYPTION_SECRET', raising=False)
    path = str(tmp_path / 'old-profiles.sqlite3')
    old = Store(secret='o'*64, sqlite_path=path)
    old.save_profile('telegram','web.telegram.org',{'cookies':[{'name':'stub', 'value':'test'}]})
    monkeypatch.setenv('MINIFISH_PROFILE_ENCRYPTION_SECRET','n'*64)
    upgraded = Store(secret='o'*64, sqlite_path=path)
    assert upgraded.get_profile('telegram')['state']['cookies'][0]['value']=='test'
    upgraded.save_profile('telegram','web.telegram.org',{'cookies':[]})
    assert upgraded.get_profile('telegram')['state']=={'cookies':[]}
    with pytest.raises(ValueError):
        old.get_profile('telegram')
