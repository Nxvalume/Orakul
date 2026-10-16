"""Search results are safely rendered from fixed-host RSS, never arbitrary URLs."""
from urllib.parse import parse_qs, urlsplit

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

import search_view


FEED = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
<item><title>Telegram — официальный сайт</title>
<link>https://telegram.org/</link>
<description>Скачать мессенджер &amp; открыть Telegram</description></item>
<item><title>Проверка</title>
<link>javascript:alert(1)</link>
<description>Выполняемый код должен быть исключён</description></item>
<item><title>Внутренняя сеть</title>
<link>http://169.254.169.254/latest/</link>
<description>Небезопасная ссылка</description></item>
<item><title>&lt;script&gt;alert(1)&lt;/script&gt; Руководство</title>
<link>https://example.com/guide</link>
<description>Подробное руководство</description></item>
</channel></rss>""".encode()


def test_rss_search_url_is_fixed_public_https_and_encodes_cyrillic():
    url = search_view._feed_url('телеграмм ? &')
    parsed = urlsplit(url)
    assert parsed.scheme == 'https'
    assert parsed.hostname == 'www.bing.com'
    assert parsed.path == '/search'
    assert parse_qs(parsed.query)['q'] == ['телеграмм ? &']
    assert parse_qs(parsed.query)['format'] == ['rss']


def test_search_results_filter_non_https_and_escape_markup():
    items = search_view._results(FEED)
    assert len(items) == 2
    assert items[0]['href'] == 'https://telegram.org/'
    page = search_view._document('телеграмм', items)
    assert 'href="https://telegram.org/"' in page
    assert 'Telegram — официальный сайт' in page
    assert 'javascript:alert' not in page
    assert '169.254.169.254' not in page
    assert '<script>' not in page
    assert 'Поиск в MiniFish' in page


def test_reject_xml_entities_and_oversized_feeds():
    import pytest
    with pytest.raises(ValueError):
        search_view._results(b'<!DOCTYPE foo [ <!ENTITY xx "attack"> ]><rss/>')
    with pytest.raises(ValueError):
        search_view._results(b'a' * (search_view.MAX_FEED_BYTES + 1))


def test_mobile_search_route_uses_escaped_results(monkeypatch):
    received = []
    def mocked_feed(query):
        received.append(query)
        return FEED
    monkeypatch.setattr(search_view, '_get_feed', mocked_feed)
    app = Starlette(routes=[Route('/search', search_view.search_page)])
    with TestClient(app) as client:
        response = client.get('/search', params={'q': 'телеграмм'})
        assert response.status_code == 200
        assert received == ['телеграмм']
        assert 'Telegram — официальный сайт' in response.text
        assert 'href="https://telegram.org/"' in response.text
        assert 'javascript:alert' not in response.text
        assert response.headers['x-robots-tag'] == 'noindex, nofollow'
        empty = client.get('/search')
        assert empty.status_code == 200
        assert 'Введите слово или фразу' in empty.text
        too_long = client.get('/search', params={'q': 'x' * 201})
        assert too_long.status_code == 400
    assert received == ['телеграмм']


def test_search_failure_returns_useful_page_without_leaking_backend_error(monkeypatch):
    def failed(_query):
        raise RuntimeError('SENSITIVE_INTERNAL_MESSAGE')
    monkeypatch.setattr(search_view, '_get_feed', failed)
    app = Starlette(routes=[Route('/search', search_view.search_page)])
    with TestClient(app) as client:
        response = client.get('/search?q=погода')
    assert response.status_code == 200
    assert 'Поиск временно недоступен' in response.text
    assert 'SENSITIVE_INTERNAL_MESSAGE' not in response.text
