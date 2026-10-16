"""Mobile-friendly result page for text entered in the MiniFish omnibox.

The upstream is a fixed public HTTPS RSS feed, never a user-selected URL.
No credentials or browser-state information are sent to the search provider.
"""
from __future__ import annotations

import asyncio
from html import escape, unescape
import re
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from starlette.requests import Request as HTTPRequest
from starlette.responses import HTMLResponse

MAX_QUERY_LENGTH = 200
MAX_FEED_BYTES = 256 * 1024
MAX_RESULTS = 12
_SEARCH_LIMIT = asyncio.Semaphore(3)


def _feed_url(query: str) -> str:
    return ("https://www.bing.com/search?format=rss&q="
            + quote(query, safe="") + "&setlang=ru")


def _get_feed(query: str) -> bytes:
    # The host cannot be controlled by the visitor. Keep bounded network use.
    request = Request(_feed_url(query), headers={
        "User-Agent": "Mozilla/5.0 (compatible; MiniFishPersonalSearch/1.0)",
        "Accept": "application/rss+xml,application/xml,text/xml;q=0.9",
    })
    with urlopen(request, timeout=8) as response:
        raw = response.read(MAX_FEED_BYTES + 1)
    if len(raw) > MAX_FEED_BYTES:
        raise ValueError("Search response too large")
    return raw


def _plain(source: str, length: int = 250) -> str:
    text = re.sub(r"<[^>]*>", " ", unescape(source or ""))
    return re.sub(r"\s+", " ", text).strip()[:length]


def _results(raw: bytes) -> list[dict]:
    if len(raw) > MAX_FEED_BYTES:
        raise ValueError("Search feed too large")
    head = raw[:4096].upper()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in head:
        raise ValueError("Unsafe XML feed")
    root = ElementTree.fromstring(raw)
    results = []
    for item in root.findall("./channel/item")[:MAX_RESULTS * 2]:
        title = _plain(item.findtext("title") or "", 160)
        description = _plain(item.findtext("description") or "")
        href = (item.findtext("link") or "").strip()
        if not title or len(href) > 2048:
            continue
        parsed = urlsplit(href)
        # Browser navigation rejects HTTP and private networks. Do not render
        # non-HTTPS links as clickable, even when they came from the feed.
        if (parsed.scheme != "https" or not parsed.hostname or
                parsed.username or parsed.password or
                (parsed.port is not None and parsed.port != 443)):
            continue
        results.append({"title": title, "description": description,
                        "href": href, "host": parsed.hostname})
        if len(results) == MAX_RESULTS:
            break
    return results


def _document(query: str, results: list[dict], note: str = "") -> str:
    q = escape(query, quote=True)
    rows = []
    for result in results:
        title = escape(result["title"], quote=True)
        desc = escape(result["description"], quote=True)
        host = escape(result["host"], quote=True)
        link = escape(result["href"], quote=True)
        rows.append(f'<article><small>{host}</small><a href="{link}">{title}</a>'
                    f'<p>{desc}</p></article>')
    message = (f'<p class="note">{escape(note)}</p>' if note else "")
    if query and not results and not note:
        message = '<p class="note">По этому запросу пока нет результатов.</p>'
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Поиск: {q} · MiniFish</title>
<style>
:root{{color-scheme:dark}}
*{{box-sizing:border-box}}
body{{font:20px/1.45 system-ui,sans-serif;background:#0f1926;color:#edf4ff;margin:0;padding:24px;}}
main{{max-width:850px;margin:0 auto}}
h1{{font-size:27px;margin:0 0 16px}}
form{{display:flex;gap:10px;margin-bottom:25px}}
input{{font:inherit;min-width:0;flex:1;padding:15px 16px;border:1px solid #536c84;
background:#1b2b3c;color:#fff;border-radius:12px}}
button{{font:inherit;background:#2776b7;color:white;border:0;border-radius:12px;padding:12px 17px}}
article{{padding:15px 0 20px;border-bottom:1px solid #32465b}}
article small{{display:block;color:#a3c2d8;font-size:16px}}
article a{{display:block;color:#91c8ff;font-size:23px;font-weight:600;text-decoration:none;margin-top:3px}}
article p{{font-size:18px;color:#d1dbe7;margin:6px 0 0}}
.note{{color:#d4dfeb}}
footer{{font-size:14px;color:#a3b5c9;margin-top:24px}}
</style></head><body><main>
<h1>Поиск в MiniFish</h1>
<form method="get" action="/search">
<input type="search" name="q" inputmode="search" enterkeyhint="search"
placeholder="Что найти?" value="{q}" maxlength="{MAX_QUERY_LENGTH}" required>
<button type="submit">Найти</button></form>
{message}{''.join(rows)}
<footer>Результаты поиска: Bing RSS. Перейди по ссылке, чтобы открыть сайт в этой вкладке.</footer>
</main></body></html>"""


async def search_page(request: HTTPRequest) -> HTMLResponse:
    query = (request.query_params.get("q") or "").strip()
    if len(query) > MAX_QUERY_LENGTH:
        return HTMLResponse(_document("", [], "Слишком длинный запрос (максимум 200 символов)."),
                            status_code=400)
    if not query:
        return HTMLResponse(_document("", [], "Введите слово или фразу для поиска."))
    try:
        async with _SEARCH_LIMIT:
            raw = await asyncio.wait_for(asyncio.to_thread(_get_feed, query), timeout=10)
        results = _results(raw)
        note = "" if results else "Поисковик не вернул подходящих HTTPS-ссылок."
    except Exception:
        # Do not echo upstream errors, URLs, personal search terms in logs.
        results, note = [], "Поиск временно недоступен. Попробуйте ещё раз."
    return HTMLResponse(_document(query, results, note),
                        headers={"X-Robots-Tag": "noindex, nofollow"})
