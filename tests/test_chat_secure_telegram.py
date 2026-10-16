"""Private Telegram navigation is owner-authorized, fixed-host, and not a model tool."""
from types import SimpleNamespace

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from chat_secure import _seal, create_owner_routes


SID = "6f7b9cb4-2da1-4373-b5ef-06a9b9b2f201"


class FakeEngine:
    def __init__(self):
        self.private_mode = True
        self.calls = []

    def get(self, sid, *, owner=False):
        assert sid == SID and owner
        return SimpleNamespace(private_mode=self.private_mode)

    async def owner_control(self, sid, action, **kwargs):
        self.calls.append((sid, action, kwargs))
        return {"ok": True, "site": "web.telegram.org"}


def client_with_owner(monkeypatch):
    monkeypatch.setenv("MINIFISH_SECRET", "Z" * 64)
    engine = FakeEngine()
    app = Starlette(routes=[
        Route("/chat/secure/{operation}", create_owner_routes(engine),
              methods=["GET", "POST", "OPTIONS"])
    ])
    return TestClient(app), engine


def test_only_valid_owner_can_navigate_existing_private_session_to_telegram(monkeypatch):
    client, engine = client_with_owner(monkeypatch)
    headers = {
        "origin": "https://chatgpt.com",
        "x-minifish-owner": _seal(SID, "https://chatgpt.com"),
    }
    with client:
        res = client.post("/chat/secure/control", headers=headers, json={
            "session_id": SID, "action": "telegram_open",
            "url": "https://attacker.invalid/", "text": "not-a-secret"
        })
    assert res.status_code == 200, res.text
    assert res.json() == {"ok": True, "site": "web.telegram.org"}
    assert engine.calls == [(SID, "navigate", {"url": "https://web.telegram.org/k/"})]


def test_private_telegram_navigate_rejects_missing_owner_and_other_origin(monkeypatch):
    client, engine = client_with_owner(monkeypatch)
    with client:
        assert client.post("/chat/secure/control",
                           headers={"origin": "https://chatgpt.com"},
                           json={"session_id": SID, "action": "telegram_open"}).status_code == 401
        token = _seal(SID, "https://chatgpt.com")
        assert client.post("/chat/secure/control",
                           headers={"origin": "https://evil.invalid",
                                    "x-minifish-owner": token},
                           json={"session_id": SID, "action": "telegram_open"}).status_code == 403
    assert engine.calls == []


def test_telegram_navigate_requires_private_mode(monkeypatch):
    client, engine = client_with_owner(monkeypatch)
    engine.private_mode = False
    with client:
        result = client.post("/chat/secure/control", headers={
            "origin": "https://chatgpt.com",
            "x-minifish-owner": _seal(SID, "https://chatgpt.com"),
        }, json={"session_id": SID, "action": "telegram_open"})
    assert result.status_code == 403
    assert engine.calls == []
