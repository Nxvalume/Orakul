"""Owner-approved domain access does not weaken other browser restrictions."""
import pytest

from engine import allowed_domains, is_allowed_domain, validate_url


def test_approved_kwork_keeps_existing_domains(monkeypatch):
    monkeypatch.setenv("BROWSER_ALLOWED_DOMAINS", "example.com,web.telegram.org")
    domains = allowed_domains()
    assert "kwork.ru" in domains
    assert "example.com" in domains
    assert "web.telegram.org" in domains
    assert is_allowed_domain("www.kwork.ru", domains)
    assert not is_allowed_domain("example.net", domains)


def test_approved_domain_still_requires_https():
    with pytest.raises(ValueError):
        validate_url("http://kwork.ru", check_dns=False)
    with pytest.raises(ValueError):
        validate_url("https://kwork.ru:8080", check_dns=False)
    with pytest.raises(ValueError):
        validate_url("https://user:pass@kwork.ru", check_dns=False)


@pytest.mark.asyncio
async def test_mcp_domain_tool_persists_and_normalizes(monkeypatch):
    import server
    from unittest.mock import Mock

    saved = Mock()
    monkeypatch.setattr(server.store, "save_domain", saved)
    monkeypatch.setattr(server, "add_allowed_domain", lambda domain: ["example.com", domain])
    result = await server.browser_allow_domain("  KWORK.RU. ")
    saved.assert_called_once_with("kwork.ru")
    assert "kwork.ru" in result["domains"]
    assert result["durable"] == bool(server.store.durable)
