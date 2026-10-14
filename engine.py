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

# In-browser cursor is a visual-only overlay. It never intercepts input,
# reads text/credentials, or communicates with any external endpoint.
CURSOR_INIT = r"""(() => {
  if (window.__minifishCursorReady) return;
  window.__minifishCursorReady = true;
  function install() {
    if (document.getElementById('__minifish_cursor')) return;
    const el = document.createElement('div');
    el.id = '__minifish_cursor';
    el.setAttribute('aria-hidden', 'true');
    el.style.cssText = 'position:fixed;left:0;top:0;width:26px;height:34px;pointer-events:none;z-index:2147483647;opacity:0;transform:translate3d(-100px,-100px,0);filter:drop-shadow(0 2px 3px rgba(0,0,0,.75));transition:opacity .18s ease;';
    el.innerHTML = '<svg width="26" height="34" viewBox="0 0 26 34" xmlns="http://www.w3.org/2000/svg"><path d="M3 2v26l6.9-7.2 4.7 10.2 5.2-2.5-4.8-10.2 9.7-.2z" fill="#f9fafb" stroke="#10212b" stroke-width="2" stroke-linejoin="round"/></svg>';
    (document.body || document.documentElement).appendChild(el);
    document.addEventListener('mousemove', ev => {
      el.style.transform = 'translate3d(' + ev.clientX + 'px,' + ev.clientY + 'px,0)';
      el.style.opacity = '1';
    }, {capture:true, passive:true});
    document.addEventListener('mousedown', () => {
      el.style.filter = 'drop-shadow(0 0 9px rgba(93,214,186,.95))';
      setTimeout(() => el.style.filter = 'drop-shadow(0 2px 3px rgba(0,0,0,.75))', 170);
    }, {capture:true, passive:true});
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, {once:true});
  else install();
})()"""



def allowed_domains() -> list[str]:
    domains = [x.strip().lower().rstrip('.') for x in os.getenv('BROWSER_ALLOWED_DOMAINS', 'example.com').split(',')]
    # Kwork is explicitly approved by the owner; existing env and stored domains remain intact.
    owner_approved = {'kwork.ru'}
    with _domains_lock:
        return sorted(set(x for x in domains if x and x != '*') | owner_approved | _extra_domains)


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
        if not unrestricted_public_https() and len(_extra_domains) >= 30 and domain not in _extra_domains:
            raise ValueError('Достигнут лимит разрешённых доменов')
        _extra_domains.add(domain)
    return allowed_domains()


def unrestricted_public_https() -> bool:
    """Owner-configured permission for any public HTTPS website, never private networks."""
    return os.getenv('MINIFISH_ALLOW_ANY_PUBLIC_HTTPS', '0') == '1'


def is_allowed_domain(host: str, domains: list[str] | None = None) -> bool:
    host = host.lower().rstrip('.')
    # Explicit domain scopes still work (e.g. for owner approval validation).
    if domains is None and unrestricted_public_https():
        return True
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
    if port not in (None, 443):
        raise ValueError('Поддерживается только стандартный порт HTTPS (443)')
    if not is_allowed_domain(host, domains):
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
    profile_name: str | None = None
    cursor: tuple[float, float] = (640.0, 450.0)


class BrowserEngine:
    def __init__(self):
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._sessions: dict[str, Session] = {}
        self._lock = asyncio.Lock()
        self.profile_save_callback = None

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

    async def open(self, url: str, *, storage_state: dict | None = None,
                   profile_name: str | None = None) -> dict:
        validate_url(url)
        async with self._lock:
            await self._cleanup_expired()
            # Reuse a temporary browser already on the same website. This
            # preserves an in-progress Telegram login and prevents the mobile
            # "Open Telegram" button from exhausting session slots.
            if storage_state is None and profile_name is None:
                target_host = urlsplit(url).hostname
                for sid, existing in reversed(list(self._sessions.items())):
                    if (not existing.page.is_closed()
                            and urlsplit(existing.page.url).hostname == target_host
                            and existing.profile_name is None):
                        existing.touched = time.monotonic()
                        return {'session_id': sid, 'url': existing.page.url,
                                'title': await existing.page.title(),
                                'profile': None, 'reused': True}
            if len(self._sessions) >= MAX_SESSIONS:
                raise RuntimeError('Лимит браузерных сессий. Выберите открытую вкладку в /live.')
            await self._launch()
            assert self._browser is not None
            context = await self._browser.new_context(accept_downloads=False, service_workers='block',
                    viewport={'width': 1280, 'height': 900},
                    **({'storage_state': storage_state} if storage_state is not None else {}))
            await context.route('**/*', self._route)
            await context.add_init_script(CURSOR_INIT)
            page = await context.new_page()
            sid = str(uuid4())
            self._sessions[sid] = Session(context=context, page=page, profile_name=profile_name)
        try:
            await page.goto(url, timeout=TIMEOUT_MS, wait_until='domcontentloaded')
            return {'session_id': sid, 'url': page.url, 'title': await page.title(),
                    'profile': profile_name}
        except Exception:
            await self.close(sid)
            raise

    async def _cleanup_expired(self) -> None:
        stale = [k for k, s in self._sessions.items() if time.monotonic() - s.touched > TTL_SECONDS]
        for sid in stale:
            s = self._sessions.pop(sid)
            await self._close_session_context(s)

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
        try:
            async with asyncio.timeout(11):
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

        except TimeoutError:
            raise RuntimeError('Telegram долго отвечает или экран занят трансляцией') from None

    async def _move_cursor(self, session: Session, x: float, y: float) -> None:
        """Genuine eased Playwright mouse movement, visible in the live stream."""
        x, y = float(x), float(y)
        start_x, start_y = session.cursor
        for step in range(1, 15):
            t = step / 14
            ease = t * t * (3 - 2 * t)
            await session.page.mouse.move(
                start_x + (x - start_x) * ease,
                start_y + (y - start_y) * ease)
            await asyncio.sleep(0.018)
        session.cursor = (x, y)

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
            await el.scroll_into_view_if_needed(timeout=TIMEOUT_MS)
            bounds = await el.bounding_box(timeout=TIMEOUT_MS)
            if bounds:
                await self._move_cursor(s, bounds['x'] + bounds['width'] / 2,
                                        bounds['y'] + bounds['height'] / 2)
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
            bounds = await el.bounding_box(timeout=TIMEOUT_MS)
            if bounds:
                await self._move_cursor(s, bounds['x'] + bounds['width'] / 2,
                                        bounds['y'] + bounds['height'] / 2)
            await el.fill(value, timeout=TIMEOUT_MS)
            # Deliberately do not echo sensitive field values.
            s.last_action = 'Заполнение поля'
            return {'filled': selector, 'length': len(value)}

    async def select(self, sid: str, selector: str, value: str) -> dict:
        s = self.get(sid)
        async with s.lock:
            el = s.page.locator(selector).first
            bounds = await el.bounding_box(timeout=TIMEOUT_MS)
            if bounds:
                await self._move_cursor(s, bounds['x'] + bounds['width'] / 2,
                                        bounds['y'] + bounds['height'] / 2)
            await el.select_option(value, timeout=TIMEOUT_MS)
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

    def telegram_session_id(self) -> str | None:
        """Existing live Telegram session, regardless of its saved profile."""
        now = time.monotonic()
        for sid, session in reversed(list(self._sessions.items())):
            if (now-session.touched < TTL_SECONDS and not session.page.is_closed()
                    and urlsplit(session.page.url).hostname == 'web.telegram.org'):
                return sid
        return None

    async def telegram_logged_in(self, sid: str) -> bool:
        """Only persist Telegram after the chat UI has replaced its login page."""
        session = self._sessions.get(sid)
        if (session is None or session.page.is_closed()
                or time.monotonic()-session.touched >= TTL_SECONDS):
            return False
        async with session.lock:
            if urlsplit(session.page.url).hostname != 'web.telegram.org':
                return False
            # Telegram Web K: the left chat sidebar is visible after login.
            # An auth form or a loading screen is never treated as logged in.
            try:
                chat_list = await session.page.locator('#column-left').is_visible()
                auth_form = await session.page.locator('#auth-pages').is_visible()
                return bool(chat_list and not auth_form)
            except Exception:
                return False

    async def telegram_authenticated_state(self, sid: str) -> dict | None:
        """Secret browser state for server-side encryption only; no idle-TTL renewal."""
        session = self._sessions.get(sid)
        if (session is None or session.page.is_closed()
                or time.monotonic()-session.touched >= TTL_SECONDS
                or urlsplit(session.page.url).hostname != 'web.telegram.org'):
            return None
        async with session.lock:
            if not (await session.page.locator('#column-left').is_visible()):
                return None
            if await session.page.locator('#auth-pages').is_visible():
                return None
            return await session.context.storage_state(indexed_db=True)

    async def live_jpeg(self, sid: str) -> bytes:
        """Read-only low-bandwidth frame that does not keep a session alive."""
        s = self._sessions.get(sid)
        if not s or time.monotonic()-s.touched >= TTL_SECONDS or s.page.is_closed():
            raise ValueError('Сессия недоступна')
        # Live viewers must never monopolize the session lock and delay MCP
        # actions. A skipped frame is preferable to hanging an agent call.
        if s.lock.locked():
            raise TimeoutError('Страница занята')
        try:
            async with asyncio.timeout(4):
                async with s.lock:
                    return await s.page.screenshot(type='jpeg', quality=55, full_page=False, timeout=3000)
        except (asyncio.TimeoutError, TimeoutError):
            raise TimeoutError('Кадр временно недоступен') from None

    async def export_state(self, sid: str) -> dict:
        """Get browser cookies/localStorage to save encrypted; never expose via MCP result."""
        s = self.get(sid)
        async with s.lock:
            return await s.context.storage_state(indexed_db=True)

    def set_profile_name(self, sid: str, name: str) -> None:
        session = self._sessions.get(sid)
        if session is None or session.page.is_closed():
            raise ValueError('Браузерная сессия не найдена')
        # Background autosave should not keep an abandoned session alive.
        session.profile_name = name

    async def screenshot(self, sid: str) -> bytes:
        s = self.get(sid)
        async with s.lock:
            return await s.page.screenshot(type='png', full_page=False, timeout=TIMEOUT_MS)

    async def owner_fields(self, sid: str) -> dict:
        """Owner-only: list visible browser form fields, never their values."""
        s = self.get(sid)
        async with s.lock:
            fields = await s.page.locator('input:visible, textarea:visible, [contenteditable="true"]:visible').evaluate_all(
                """els => els.slice(0, 24).map((el, i) => ({
                    index: i,
                    kind: (el.getAttribute('type') || (el.isContentEditable ? 'text' : 'text')).toLowerCase(),
                    label: String(el.getAttribute('aria-label') ||
                        el.getAttribute('placeholder') ||
                        el.getAttribute('name') ||
                        el.getAttribute('id') ||
                        el.closest('label')?.innerText ||
                        'Поле ' + (i + 1)).slice(0, 90)
                }))""")
            return {'fields': fields, 'site': urlsplit(s.page.url).hostname or ''}

    async def owner_control(self, sid: str, action: str, *, x=None, y=None, text=None, key=None, field_index=None) -> dict:
        """Owner-only manual handoff. Do not expose as an MCP tool.

        Owner may type into the browser directly (including login forms) without
        passing account credentials to ChatGPT. Never log or return typed data.
        """
        s = self.get(sid)
        if action not in ('click', 'type', 'key', 'fill_field'):
            raise ValueError('Неизвестное действие управления')
        async with s.lock:
            if action == 'click':
                if (isinstance(x, bool) or isinstance(y, bool)
                        or not isinstance(x, (int, float)) or not isinstance(y, (int, float))):
                    raise ValueError('Некорректные координаты')
                viewport = s.page.viewport_size or {'width': 1280, 'height': 900}
                if not (0 <= x < viewport['width'] and 0 <= y < viewport['height']):
                    raise ValueError('Нажатие вне экрана')
                await self._move_cursor(s, float(x), float(y))
                await s.page.mouse.click(float(x), float(y))
                s.last_action = 'Владелец нажал на экране'
            elif action == 'type':
                if not isinstance(text, str) or not 0 < len(text) <= 1000:
                    raise ValueError('Текст должен содержать от 1 до 1000 символов')
                await s.page.keyboard.insert_text(text)
                s.last_action = 'Владелец ввёл текст'
            elif action == 'fill_field':
                if (isinstance(field_index, bool) or not isinstance(field_index, int)
                        or field_index < 0 or field_index > 23):
                    raise ValueError('Выберите поле на странице')
                if not isinstance(text, str) or not 0 < len(text) <= 1000:
                    raise ValueError('Введите текст в поле MiniFish')
                fields = s.page.locator('input:visible, textarea:visible, [contenteditable="true"]:visible')
                if field_index >= await fields.count():
                    raise ValueError('Поле больше не доступно. Обновите список полей')
                target = fields.nth(field_index)
                kind = (await target.get_attribute('type') or '').lower()
                if kind in {'hidden','file','checkbox','radio','submit','button'}:
                    raise ValueError('В это поле нельзя вводить текст')
                await target.fill(text, timeout=TIMEOUT_MS)
                s.last_action = 'Владелец заполнил поле'
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

    async def _close_session_context(self, session: Session) -> dict:
        updated = False
        failed = False
        try:
            if session.profile_name and self.profile_save_callback is not None:
                # Never overwrite a saved Telegram login with a logged-out
                # browser context or an in-progress reauthentication screen.
                can_checkpoint = True
                if session.profile_name == 'telegram':
                    try:
                        can_checkpoint = (
                            urlsplit(session.page.url).hostname == 'web.telegram.org'
                            and await session.page.locator('#column-left').is_visible()
                            and not await session.page.locator('#auth-pages').is_visible()
                        )
                    except Exception:
                        can_checkpoint = False
                if can_checkpoint:
                    state = await session.context.storage_state(indexed_db=True)
                    await self.profile_save_callback(session.profile_name, state)
                    updated = True
        except Exception:
            # Do not leak cookies or credentials into errors or logs.
            failed = True
        finally:
            await session.context.close()
        return {'closed': True, 'profile_updated': updated, 'profile_save_failed': failed}

    async def close(self, sid: str) -> dict:
        async with self._lock:
            s = self._sessions.pop(sid, None)
        if s is None:
            return {'closed': False}
        return await self._close_session_context(s)

    async def shutdown(self) -> None:
        for sid in list(self._sessions):
            await self.close(sid)
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._pw is not None:
            await self._pw.stop()
            self._pw = None
