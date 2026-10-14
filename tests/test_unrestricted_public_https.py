"""Public HTTPS unrestricted mode regression tests (no external network required)."""
import socket
from unittest.mock import patch

import pytest

from engine import add_allowed_domain, is_allowed_domain, validate_url, _extra_domains


PUBLIC_DNS = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('1.1.1.1', 443))]
PRIVATE_DNS = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.0.0.7', 443))]


def test_unrestricted_public_domain(monkeypatch):
    monkeypatch.setenv('MINIFISH_ALLOW_ANY_PUBLIC_HTTPS', '1')
    monkeypatch.setenv('BROWSER_ALLOWED_DOMAINS', 'example.com')
    with patch('engine.socket.getaddrinfo', return_value=PUBLIC_DNS):
        assert validate_url('https://previously-unlisted.example/path?ok=1').startswith('https://')
    assert is_allowed_domain('previously-unlisted.example')


def test_legacy_domain_allowlist_still_available(monkeypatch):
    monkeypatch.delenv('MINIFISH_ALLOW_ANY_PUBLIC_HTTPS', raising=False)
    monkeypatch.setenv('BROWSER_ALLOWED_DOMAINS', 'example.com')
    assert not is_allowed_domain('previously-unlisted.example')
    with pytest.raises(ValueError, match='не разрешён'):
        validate_url('https://previously-unlisted.example')


@pytest.mark.parametrize('url', [
    'http://example.com/', 'https://127.0.0.1/',
    'https://10.0.0.1/', 'https://example.com:8443/',
    'https://user:password@example.com/'
])
def test_unrestricted_mode_keeps_url_guards(monkeypatch, url):
    monkeypatch.setenv('MINIFISH_ALLOW_ANY_PUBLIC_HTTPS', '1')
    with patch('engine.socket.getaddrinfo', return_value=PUBLIC_DNS):
        with pytest.raises(ValueError):
            validate_url(url)


def test_dns_private_addresses_remain_blocked(monkeypatch):
    monkeypatch.setenv('MINIFISH_ALLOW_ANY_PUBLIC_HTTPS', '1')
    with patch('engine.socket.getaddrinfo', return_value=PRIVATE_DNS):
        with pytest.raises(ValueError, match='приватной'):
            validate_url('https://public-looking.example')


def test_no_30_domain_cap_in_public_mode(monkeypatch):
    monkeypatch.setenv('MINIFISH_ALLOW_ANY_PUBLIC_HTTPS', '1')
    previous = set(_extra_domains)
    try:
        _extra_domains.update({f'allowed-{n}.example' for n in range(40)})
        with patch('engine.socket.getaddrinfo', return_value=PUBLIC_DNS):
            assert 'allowed-new.example' in add_allowed_domain('allowed-new.example')
    finally:
        _extra_domains.clear()
        _extra_domains.update(previous)
