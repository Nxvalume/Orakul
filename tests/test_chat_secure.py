"""Private MCP Apps widget authenticates directly to MiniFish, not through chat tools."""
from uuid import uuid4
import pytest
from chat_secure import trusted_chat_origin, _seal, _valid, _cors
from chat_ui import CHAT_TOOL_META, CHAT_UI_URI, CHAT_UI_CSP


def test_widget_accepts_only_trusted_https_sandbox_origins():
    assert trusted_chat_origin('https://chatgpt.com')
    assert trusted_chat_origin('https://example.oaiusercontent.com')
    assert not trusted_chat_origin('https://attacker.example')
    assert not trusted_chat_origin('https://oaiusercontent.com.attacker.example')
    assert not trusted_chat_origin('http://chatgpt.com')
    assert not trusted_chat_origin('https://chatgpt.com:444')
    assert not trusted_chat_origin('null')


def test_private_owner_token_is_bound_to_session_and_origin(monkeypatch):
    monkeypatch.setenv('MINIFISH_SECRET', 'M'*64)
    sid=str(uuid4())
    other=str(uuid4())
    origin='https://sandbox.oaiusercontent.com'
    token=_seal(sid, origin)
    assert _valid(token,sid,origin)
    assert not _valid(token,other,origin)
    assert not _valid(token,sid,'https://chatgpt.com')
    assert not _valid(token+'0',sid,origin)
    assert not _valid('',sid,origin)


def test_ui_declares_only_existing_mini_fish_https_host():
    uri=CHAT_TOOL_META['ui']['resourceUri']
    assert uri==CHAT_UI_URI
    assert CHAT_UI_CSP['connectDomains']==['https://nxval-minifish-2026.onrender.com']
    assert _cors('https://chatgpt.com')['Access-Control-Allow-Origin']=='https://chatgpt.com'
