"""Cross-site browsing keeps one browser and both owner/public entrypoints safe."""
import re
import shutil
import subprocess
import socket

import pytest

from chat_ui import CHAT_HTML
from engine import validate_url


def test_shared_address_bar_uses_same_session_and_private_uses_owner_channel():
    assert 'id="navForm"' in CHAT_HTML
    assert 'id="secureNavForm"' in CHAT_HTML
    assert "$('navForm').hidden=!enabled;" in CHAT_HTML
    assert "act('browser_goto',{session_id:session,url})" in CHAT_HTML
    assert "secureAction('navigate',{url})" in CHAT_HTML
    assert "if(!secureToken)" in CHAT_HTML
    assert "resolveOmnibox($('secureUrl').value)" in CHAT_HTML
    assert "resolveOmnibox($('navUrl').value)" in CHAT_HTML
    assert 'id="navUrl" type="search" inputmode="search"' in CHAT_HTML
    assert 'id="secureUrl" type="search" inputmode="search"' in CHAT_HTML


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js unavailable")
def test_widget_address_validation_handles_scheme_credentials_and_custom_ports():
    match = re.search(r"(?ms)^ function cleanSiteUrl\(raw\)\{.*?^ \}", CHAT_HTML)
    assert match is not None
    script = match.group(0) + """
const accepted=[
 ['example.com','https://example.com/'],
 ['https://web.telegram.org/k/','https://web.telegram.org/k/'],
 ['  https://example.com/  ','https://example.com/']
];
for(const [input,expected] of accepted){
 if(cleanSiteUrl(input)!==expected)process.exit(1);
}
for(const input of ['http://example.com','https://user:pass@example.com',
                     'https://example.com:444','ftp://example.com','https://']){
 try{cleanSiteUrl(input);process.exit(2)}catch(e){}
}
"""
    # Use a flag instead of process.exit inside the try as that is not catchable;
    # process.exit ends Node immediately on invalid acceptance.
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_owner_approved_public_https_still_rejects_internal_hosts(monkeypatch):
    monkeypatch.setenv("MINIFISH_ALLOW_ANY_PUBLIC_HTTPS", "1")
    assert validate_url("https://example.com/", check_dns=False)
    for private in ("https://127.0.0.1/", "https://10.0.0.5/",
                    "https://192.168.1.1/", "https://169.254.169.254/",
                    "https://[::1]/"):
        with pytest.raises(ValueError):
            validate_url(private, check_dns=False)
    with pytest.raises(ValueError):
        validate_url("http://example.com", check_dns=False)
    with pytest.raises(ValueError):
        validate_url("https://user:pass@example.com", check_dns=False)


def test_domain_dns_resolution_must_be_public_even_if_public_https_enabled(monkeypatch):
    monkeypatch.setenv("MINIFISH_ALLOW_ANY_PUBLIC_HTTPS", "1")
    monkeypatch.setattr(socket, "getaddrinfo",
                        lambda *a, **k: [(socket.AF_INET,socket.SOCK_STREAM,0,"",("10.0.0.2",443))])
    with pytest.raises(ValueError):
        validate_url("https://example.com/")


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js unavailable")
def test_android_omnibox_resolves_russian_queries_and_bare_domains():
    import json
    helpers = re.search(
        r"(?ms)^ function cleanSiteUrl\(raw\)\{.*?^ \}\n"
        r"^ function resolveOmnibox\(raw\)\{.*?^ \}", CHAT_HTML)
    assert helpers is not None
    samples = [
        ('телеграмм', 'search'),
        ('как установить телеграмм', 'search'),
        ('Telegram', 'search'),
        ('site:telegram.org мессенджер', 'search'),
        ('foo bar.com', 'search'),
        ('telegram.org', 'site'),
        ('www.telegram.org/k/', 'site'),
        ('https://web.telegram.org/k/', 'site'),
        ('пример.рф', 'site'),
    ]
    js = helpers.group(0) + '''
const samples = ''' + json.dumps(samples, ensure_ascii=False) + ''';
for(const [typed,kind] of samples){
 const url=resolveOmnibox(typed);
 const parsed=new URL(url);
 if(kind==='search'){
  if(parsed.hostname!=='nxval-minifish-2026.onrender.com' ||
     parsed.pathname!=='/search' ||
     parsed.searchParams.get('q')!==typed)process.exit(1);
 }else if(parsed.hostname==='nxval-minifish-2026.onrender.com')process.exit(2);
}
for(const invalid of ['http://example.com','ftp://example.com',
  'https://user:pass@example.com','https://example.com:444','https://','']){
 let failed=false;
 try{resolveOmnibox(invalid)}catch(e){failed=true}
 if(!failed)process.exit(3);
}
'''
    result = subprocess.run(['node', '-e', js], capture_output=True,
                            text=True, timeout=10)
    assert result.returncode == 0, result.stderr
