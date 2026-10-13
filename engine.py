"""Safe, bounded Playwright browsing engine for MiniFish MCP."""
from __future__ import annotations

import asyncio
import ipaddress
import os
import re
import socket
import time
import threading
from dataclasses import dataclass, field
from urllib.parse import urlsplit
from uuid import uuid4

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

_extra_domains: set[str] = set()
_domains_lock = threading.Lock()
MAX_TEXT = 16000
MAX_SESSIONS = 2
TTL_SECONDS = 900
TIMEOUT_MS = 15000


def allowed_domains() -> list[str]:
    domains = [x.strip().lower().rstrip('.') for x in os.getenv('BROWSER_ALLOWED_DOMAINS', 'example.com').split(',')]
    
    with _domains_lock:
        return sorted(set(x for x in domains if x and x != '*') | _extra_domains)


def add_allowed_domain(domain: str) -> list[str]:
    """Explicitly add a public hostname to the running process (no wildcard)."""
    domain = domain.strip().lower().rstrip('.')
    if not re.fullmatch(r'[a-z0-9-]+(?:\.[a-z0-9-]+)+', domain) or len(domain) > 253:
        raise ValueError('Введите корректный домен, например example.com')
    if domain.startswith('xn--'):
        raise ValueError('Используйте стандартный домен')
    # Validate before making it available to the browser.
    validate_url(f'https://{domain}', [domain])
    with _domains_lock:
        if len(_extra_domains) >= 30 and domain not in _extra_domains:
            raise ValueError('Достигнут лимит разрешённых доменов')
        _extra_domains.add(domain)
    return allowed_domains()


def is_allowed_domain(host: str, domains: list[str] | None = None) -> bool:
    host = host.lower().rstrip('.')
    return any(host == d or host.endswith('.' + d) for d in (domains if domains is not None else allowed_domains()))


def validate_url(url: str, domains: list[str] | None = None, *, check_dns: bool = True) -> str:
    if not isinstance(url, str) or len(url) > 2048:
        raise ValueError('Недопустимая длина URL')
    parts = urlsplit(url)
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password:
        raise ValueError('Разрешены только публичные HTTPS-адреса без встроенных учётных данных')
    try:
        host = parts.hostname.encode('idna').decode('ascii').lower().rstrip('.')
        port = parts.port
    except (ValueError, UnicodeError) as exc:
        raise ValueError('Недопустимый адрес') from exc
    if port not in (None, 443) or not is_allowed_domain(host, domains):
        raise ValueError(f'Домен {host} не разрешён в BROWSER_ALLOWED_DOMAINS')
    try:
        parsed_ip = ipaddress.ip_address(host)
    except ValueError:
        parsed_ip = None
    if parsed_ip is not None and not parsed_ip.is_global:
        raise ValueError('Приватные и служебные адреса запрещены')
    if check_dns:
        try:
            addresses = socket.getaddrinfo(host, port or 443, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ValueError('Не удалось определить публичный адрес сайта') from exc
        if not addresses or any(not ipaddress.ip_address(info[4][0]).is_global for info in addresses):
            raise ValueError('Адрес ведёт к приватной или служебной сети')
    return url


def trim(value: str, limit: int = MAX_TEXT) -> str:
    return value[:limit] + ('\n...[обрезано]' if len(value) > limit else '')


def sensitive_action(label: str) -> bool:
    pattern = r'\b(pay|purchase|checkout|buy now|delete|remove account|transfer|submit payment|оплатить|купить|удалить|перевести деньги|списать)\b'
    return bool(re.search(pattern, label.lower()))


@dataclass
class Session:
    context: BrowserContext
    page: Page
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    touched: float = field(default_factory=time.monotonic)
    last_action: str = 'Открыта страница'


class BrowserEngine:
    def __init__(self):
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._sessions: dict[str, Session] = {}
        self._lock = asyncio.Lock()

    async def _launch(self) -> None:
        if self._browser is None:
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(headless=True, args=['--disable-dev-shm-usage'])

    async def _route(self, route):
        # Check every subresource and redirect, not only top-level navigations.
        try:
            validate_url(route.request.url)
        except (ValueError, TypeError):
            await route.abort('blockedbyclient')
            return
        await route.continue_()

    async def open(self, url: str) -> dict:
        validate_url(url)
        async with self._lock:
            await self._cleanup_expired()
            if len(self._sessions) >= MAX_SESSIONS:
                raise RuntimeError('Лимит одновременных браузерных сессий; закройте одну из них')
            await self._launch()
            assert self._browser is not None
            context = await self._browser.new_context(accept_downloads=False, service_workers='block', viewport={'width': 1280, 'height': 900})
            await context.route('**/*', self._route)
            page = await context.new_page()
            sid = str(uuid4())
            self._sessions[sid] = Session(context=context, page=page)
        try:
            await page.goto(url, timeout=TIMEOUT_MS, wait_until='domcontentloaded')
            return {'session_id': sid, 'url': page.url, 'title': await page.title()}
        except Exception:
            await self.close(sid)
            raise

    async def _cleanup_expired(self) -> None:
        stale = [k for k, s in self._sessions.items() if time.monotonic() - s.touched > TTL_SECONDS]
        for sid in stale:
            s = self._sessions.pop(sid)
            await s.context.close()

    def get(self, sid: str) -> Session:
        s = self._sessions.get(sid)
        if s is None:
            raise ValueError('Браузерная сессия не найдена. Вызовите browser_open.')
        if time.monotonic() - s.touched > TTL_SECONDS:
            raise ValueError('Браузерная сессия истекла. Вызовите browser_close, затем browser_open.')
        s.touched = time.monotonic()
        return s

    async def goto(self, sid: str, url: str) -> dict:
        validate_url(url)
        s = self.get(sid)
        async with s.lock:
            await s.page.goto(url, timeout=TIMEOUT_MS, wait_until='domcontentloaded')
            s.last_action = 'Переход на сайт'
            return {'url': s.page.url, 'title': await s.page.title()}

    async def back(self, sid: str) -> dict:
        s = self.get(sid)
        async with s.lock:
            await s.page.go_back(timeout=TIMEOUT_MS, wait_until='domcontentloaded')
            s.last_action = 'Возврат на предыдущую страницу'
            return {'url': s.page.url, 'title': await s.page.title()}

    async def snapshot(self, sid: str) -> dict:
        s = self.get(sid)
        async with s.lock:
            page = s.page
            text = await page.locator('body').inner_text(timeout=TIMEOUT_MS)
            # Semantically useful links, buttons and fields, bounded for model context.
            elements = await page.locator('a, button, input, textarea, select, [role="button"]').evaluate_all('''els => els.slice(0, 80).map((e, i) => ({
                selector: (() => { let p=[], n=e; while (n && n.nodeType === 1 && p.length < 12) {
                    if (n.id) { p.unshift('#' + CSS.escape(n.id)); break; }
                    const tag=n.tagName.toLowerCase();
                    const num=Array.from(n.parentElement?.children || []).filter(x => x.tagName === n.tagName).indexOf(n) + 1;
                    p.unshift(tag + ':nth-of-type(' + num + ')'); n=n.parentElement;
                } return p.join(' > '); })(),
                i, tag: e.tagName.toLowerCase(), text: (e.innerText || e.getAttribute('aria-label') || '').slice(0, 100),
                type: e.getAttribute('type'), name: e.getAttribute('name'), id: e.id || null,
                placeholder: e.getAttribute('placeholder'), href: e.getAttribute('href')
            }))''')
            return {'url': page.url, 'title': await page.title(), 'text': trim(text), 'elements': elements}

    async def click(self, sid: str, selector: str, confirm_sensitive: bool = False) -> dict:
        if not selector or len(selector) > 300:
            raise ValueError('Укажите корректный CSS-селектор')
        s = self.get(sid)
        async with s.lock:
            el = s.page.locator(selector).first
            label = trim(((await el.inner_text(timeout=TIMEOUT_MS)) or '') + ' ' + ((await el.get_attribute('aria-label')) or ''), 300)
            typ = (await el.get_attribute('type') or '').lower()
            if (typ == 'submit' or sensitive_action(label)) and not confirm_sensitive:
                raise PermissionError(f'Для подтверждаемого действия «{label.strip()}» нужно explicit confirm_sensitive=true после согласия пользователя')
            await el.click(timeout=TIMEOUT_MS)
            if len(s.context.pages) > 1:
                s.page = s.context.pages[-1]
            s.last_action = 'Нажатие: ' + (label.strip()[:80] or selector[:80])
            return {'clicked': selector, 'url': s.page.url, 'label': label}

    async def fill(self, sid: str, selector: str, value: str) -> dict:
        if not selector or len(selector) > 300 or len(value) > 4000:
            raise ValueError('Слишком длинный селектор или значение')
        s = self.get(sid)
        async with s.lock:
            el = s.page.locator(selector).first
            attrs = ' '.join([(await el.get_attribute(k) or '') for k in ['type', 'name', 'id', 'autocomplete']])
            if re.search(r'password|passwd|card|cc-number|cc-csc|cvv|cvc|otp|one-time-code|token|secret', attrs, re.I):
                raise PermissionError('Ввод паролей, кодов и платёжных данных не поддерживается')
            await el.fill(value, timeout=TIMEOUT_MS)
            # Deliberately do not echo sensitive field values.
            s.last_action = 'Заполнение поля'
            return {'filled': selector, 'length': len(value)}

    async def select(self, sid: str, selector: str, value: str) -> dict:
        s = self.get(sid)
        async with s.lock:
            await s.page.locator(selector).first.select_option(value, timeout=TIMEOUT_MS)
            s.last_action = 'Выбор значения'
            return {'selected': selector, 'value': value}

    def live_sessions(self) -> list[dict]:
        """Owner-visible session summary without revealing page path or query."""
        now = time.monotonic()
        result = []
        for sid, s in list(self._sessions.items()):
            if now - s.touched >= TTL_SECONDS or s.page.is_closed():
                continue
            site = urlsplit(s.page.url).hostname or 'Загрузка страницы'
            result.append({'session_id': sid, 'site': site, 'action': s.last_action})
        return result

    async def live_jpeg(self, sid: str) -> bytes:
        """Read-only low-bandwidth frame that does not keep a session alive."""
        s = self._sessions.get(sid)
        if not s or time.monotonic()-s.touched >= TTL_SECONDS or s.page.is_closed():
            raise ValueError('Сессия недоступна')
        async with s.lock:
            return await s.page.screenshot(type='jpeg', quality=55, full_page=False, timeout=TIMEOUT_MS)

    async def screenshot(self, sid: str) -> bytes:
        s = self.get(sid)
        async with s.lock:
            return await s.page.screenshot(type='png', full_page=False, timeout=TIMEOUT_MS)

    async def owner_control(self, sid: str, action: str, *, x=None, y=None, text=None, key=None) -> dict:
        """Owner-only manual handoff. Do not expose as an MCP tool.

        Owner may type into the browser directly (including login forms) without
        passing account credentials to ChatGPT. Never log or return typed data.
        """
        s = self.get(sid)
        if action not in ('click', 'type', 'key'):
            raise ValueError('Неизвестное действие управления')
        async with s.lock:
            if action == 'click':
                if (isinstance(x, bool) or isinstance(y, bool)
                        or not isinstance(x, (int, float)) or not isinstance(y, (int, float))):
                    raise ValueError('Некорректные координаты')
                viewport = s.page.viewport_size or {'width': 1280, 'height': 900}
                if not (0 <= x < viewport['width'] and 0 <= y < viewport['height']):
                    raise ValueError('Нажатие вне экрана')
                await s.page.mouse.click(float(x), float(y))
                s.last_action = 'Владелец нажал на экране'
            elif action == 'type':
                if not isinstance(text, str) or not 0 < len(text) <= 1000:
                    raise ValueError('Текст должен содержать от 1 до 1000 символов')
                await s.page.keyboard.insert_text(text)
                s.last_action = 'Владелец ввёл текст'
            else:
                allowed = {'Tab', 'Enter', 'Escape', 'Backspace', 'Delete',
                           'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight',
                           'ControlOrMeta+A'}
                if key not in allowed:
                    raise ValueError('Клавиша не разрешена')
                await s.page.keyboard.press(key)
                s.last_action = 'Владелец нажал клавишу'
            if len(s.context.pages) > 1:
                s.page = s.context.pages[-1]
            return {'ok': True, 'site': urlsplit(s.page.url).hostname or ''}

    async def scroll(self, sid: str, pixels: int = 650) -> dict:
        s = self.get(sid)
        pixels = max(-1500, min(1500, int(pixels)))
        async with s.lock:
            await s.page.mouse.wheel(0, pixels)
            s.last_action = 'Прокрутка страницы'
            return {'scroll_pixels': pixels, 'url': s.page.url}

    async def close(self, sid: str) -> dict:
        async with self._lock:
            s = self._sessions.pop(sid, None)
        if s is None:
            return {'closed': False}
        await s.context.close()
        return {'closed': True}

    async def shutdown(self) -> None:
        for sid in list(self._sessions):
            await self.close(sid)
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._pw is not None:
            await self._pw.stop()
            self._pw = None
