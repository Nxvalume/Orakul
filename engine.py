"""Safe, bounded Playwright browsing engine for MiniFish MCP."""
from __future__ import annotations

import asyncio
import json
import ipaddress
import os
import secrets
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
MAX_SESSIONS = 1
TTL_SECONDS = 600
TELEGRAM_LOGIN_TTL_SECONDS = 1800  # owner authentication window; reaped afterwards


def session_idle_limit(session) -> int:
    """Keep an in-progress owner login open long enough for Telegram 2FA."""
    if (session.private_mode and
            urlsplit(session.page.url).hostname == 'web.telegram.org'):
        return TELEGRAM_LOGIN_TTL_SECONDS
    return TTL_SECONDS
TIMEOUT_MS = 15000


def memory_pressure(threshold: float = 0.80) -> bool:
    """Best-effort memory guard for 512-MiB Render instances; fail open elsewhere."""
    try:
        with open('/sys/fs/cgroup/memory.max', encoding='ascii') as f:
            maximum = f.read(32).strip()
        if not maximum.isdigit():
            return False
        capacity = int(maximum)
        if not 0 < capacity <= 1024 * 1024 * 1024:
            return False
        with open('/sys/fs/cgroup/memory.current', encoding='ascii') as f:
            used = int(f.read(32).strip())
        return used >= capacity * threshold
    except (OSError, ValueError):
        return False

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
    pattern = r'\b(pay|purchase|checkout|buy now|delete|remove account|transfer|submit payment|send|publish|post now|approve|confirm|authorize|accept|оплатить|купить|удалить|перевести деньги|списать|отправить|опубликовать|подтвердить|подтверждаю|разрешить|согласиться)\b'
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
    private_mode: bool = False
    pending_click: dict | None = None
    approved_click: dict | None = None


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
            self._browser = await self._pw.chromium.launch(headless=True, args=[
                '--disable-dev-shm-usage', '--disable-extensions',
                '--disable-background-networking', '--disable-default-apps',
                '--no-first-run', '--disable-component-update',
                '--disable-gpu', '--renderer-process-limit=2',
                '--disable-breakpad'])

    async def _route(self, route):
        # Under memory pressure, degrade only optional assets rather than
        # allow a kernel OOM kill to erase the owner's active Chromium state.
        if memory_pressure() and route.request.resource_type in {'image', 'media', 'font'}:
            await route.abort('blockedbyclient')
            return
        # Check every subresource and redirect, not only top-level navigations.
        # DNS can block for seconds. Never stall the single event loop while a
        # live video stream, owner input and MCP commands are also active.
        try:
            await asyncio.wait_for(asyncio.to_thread(validate_url, route.request.url), timeout=5)
        except (ValueError, TypeError, asyncio.TimeoutError):
            await route.abort('blockedbyclient')
            return
        # A Telegram locale JSON is a subresource, not an interactive page.
        # Android touch/cached tabs may navigate directly to it and display
        # thousands of untranslated strings. Redirect ONLY document navigation
        # here; regular locale fetch/XHR must continue unchanged. Retain this
        # in the one existing browser context (never create another session).
        request = route.request
        target = urlsplit(request.url)
        if (getattr(request, 'is_navigation_request', lambda: False)()
                and target.hostname == 'web.telegram.org'
                and re.fullmatch(r'/js/locales/[a-z0-9_-]+[.]json', target.path, re.I)):
            await route.fulfill(
                status=302,
                headers={'Location': 'https://web.telegram.org/k/',
                         'Cache-Control': 'no-store'},
                body='')
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
                            and not existing.private_mode
                            and urlsplit(existing.page.url).hostname == target_host
                            and existing.profile_name is None):
                        existing.touched = time.monotonic()
                        return {'session_id': sid, 'url': existing.page.url,
                                'title': await existing.page.title(),
                                'profile': None, 'reused': True}
            if len(self._sessions) >= MAX_SESSIONS:
                raise RuntimeError('Render Free поддерживает один браузер одновременно. Закройте предыдущую сессию в панели MiniFish перед открытием другого сайта.')
            await self._launch()
            assert self._browser is not None
            # Block service workers on EVERY website: their cache interception
            # bypasses frame routing and raises memory pressure above Render's
            # 512 MiB limit. Telegram login already runs without service workers.
            is_telegram = urlsplit(url).hostname == 'web.telegram.org'
            restored = dict(storage_state) if storage_state is not None else None
            session_values = (restored.pop('_minifish_session_storage', None)
                              if isinstance(restored, dict) else None)
            context = await self._browser.new_context(
                    accept_downloads=False,
                    service_workers='block',
                    viewport={'width': 800, 'height': 560},
                    device_scale_factor=1,
                    **({'storage_state': restored} if restored is not None else {}))
            await context.route('**/*', self._route)
            await context.add_init_script(CURSOR_INIT)
            if is_telegram and isinstance(session_values, dict):
                # The payload is only ever injected into its exact original
                # trusted HTTPS origin. It never enters MCP / URLs / logs.
                restored_telegram = session_values.get('https://web.telegram.org')
                if isinstance(restored_telegram, dict):
                    await context.add_init_script(
                        "(() => { if(location.origin !== 'https://web.telegram.org') return;"
                        "const saved = " + json.dumps(restored_telegram, ensure_ascii=True) + ";"
                        "for(const [k,v] of Object.entries(saved)){"
                        "if(typeof k==='string' && typeof v==='string')"
                        "sessionStorage.setItem(k,v); } })();")
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
        stale = [k for k, s in self._sessions.items() if time.monotonic() - s.touched > session_idle_limit(s)]
        for sid in stale:
            s = self._sessions.pop(sid)
            await self._close_session_context(s)

    async def reclaim_chromium_memory(self) -> dict:
        """Proactively request JS heap GC under Render memory pressure.

        This does not navigate, close tabs, inspect Telegram contents, or expose
        credentials. Avoid creating a CDP session while a user action is running.
        """
        if not memory_pressure():
            return {'attempted': False}
        reclaimed = 0
        for session in list(self._sessions.values()):
            if session.page.is_closed() or session.lock.locked():
                continue
            try:
                async with asyncio.timeout(6):
                    async with session.lock:
                        cdp = await session.context.new_cdp_session(session.page)
                        try:
                            await cdp.send('HeapProfiler.collectGarbage')
                            reclaimed += 1
                        finally:
                            await cdp.detach()
            except (Exception, asyncio.CancelledError) as exc:
                if isinstance(exc, asyncio.CancelledError):
                    raise
                # No user text, profile state, or browser URL in diagnostics.
                continue
        return {'attempted': True, 'pages': reclaimed}

    async def reap_idle(self) -> dict:
        """Reap expired contexts even without new browser_open calls.

        A free 512-MiB instance cannot retain Chromium forever after a mobile
        browser disconnects. Active sessions with owner controls are renewed.
        """
        async with self._lock:
            await self._cleanup_expired()
            if not self._sessions and self._browser is not None:
                await self._browser.close()
                self._browser = None
                if self._pw is not None:
                    await self._pw.stop()
                    self._pw = None
            return {'active_sessions': len(self._sessions)}

    def get(self, sid: str, *, owner: bool = False) -> Session:
        s = self._sessions.get(sid)
        if s is None:
            raise ValueError('Браузерная сессия не найдена. Вызовите browser_open.')
        if time.monotonic() - s.touched > session_idle_limit(s):
            raise ValueError('Браузерная сессия истекла. Вызовите browser_close, затем browser_open.')
        if s.private_mode and not owner:
            raise PermissionError('Личный режим владельца: доступ MCP временно заблокирован')
        s.touched = time.monotonic()
        return s

    # Render Free hosts a single Chromium context. Tabs share its cookies,
    # IndexedDB and authorization without consuming additional browser slots.
    MAX_TABS = 6

    def _tab_pages(self, session: Session) -> list:
        # Legacy owner-control test fixtures provide a Page without a complete
        # BrowserContext. Production Playwright contexts always expose pages.
        pages = getattr(session.context, 'pages', None)
        if pages is None:
            pages = [session.page]
        return [page for page in pages if not page.is_closed()]

    async def tab_list(self, sid: str, *, owner: bool = False) -> dict:
        """Return bounded tab metadata; private pages only through owner HTTPS."""
        session = self.get(sid, owner=owner)
        async with session.lock:
            pages = self._tab_pages(session)
            if not pages:
                raise ValueError('Не осталось открытых вкладок')
            if session.page not in pages:
                session.page = pages[-1]
            items = []
            for idx, page in enumerate(pages):
                site = urlsplit(page.url).hostname or ''
                try:
                    title = str(await asyncio.wait_for(page.title(), timeout=2))[:72]
                except Exception:
                    title = site or 'Новая вкладка'
                items.append({'index': idx, 'title': title or site or 'Новая вкладка',
                              'site': site, 'active': page is session.page})
            return {'tabs': items, 'active': pages.index(session.page),
                    'max_tabs': self.MAX_TABS}

    async def tab_action(self, sid: str, action: str, index: int = -1, url: str = '',
                         *, owner: bool = False) -> dict:
        """Create, switch or close real Playwright Page objects within one context.

        Model tools cannot touch any tabs while owner private mode is enabled.
        The owner channel passes owner=True only after HMAC+password validation.
        """
        if action not in ('new', 'switch', 'close', 'forward', 'reload'):
            raise ValueError('Недопустимое действие с вкладкой')
        if isinstance(index, bool) or type(index) is not int:
            raise ValueError('Неверный номер вкладки')
        if action == 'new' and url:
            await asyncio.to_thread(validate_url, url)
        session = self.get(sid, owner=owner)
        async with session.lock:
            pages = self._tab_pages(session)
            if not pages:
                raise ValueError('Браузерные вкладки закрыты')
            if session.page not in pages:
                session.page = pages[-1]
            if action in ('switch', 'close') and not 0 <= index < len(pages):
                raise ValueError('Вкладка не найдена; обновите список')
            if action == 'new':
                if len(pages) >= self.MAX_TABS:
                    raise ValueError('Достигнут предел 6 вкладок для Render Free')
                page = await session.context.new_page()
                try:
                    if url:
                        await page.goto(url, timeout=TIMEOUT_MS,
                                        wait_until='domcontentloaded')
                    else:
                        await page.set_content('<!doctype html><title>Новая вкладка</title><main><h1>Новая вкладка</h1><p>Введите HTTPS-адрес в строке MiniFish.</p></main>')
                    session.page = page
                except Exception:
                    await page.close()
                    raise
            elif action == 'switch':
                session.page = pages[index]
                await session.page.bring_to_front()
            elif action == 'close':
                to_close = pages[index]
                if (session.private_mode and
                        urlsplit(to_close.url).hostname == 'web.telegram.org'):
                    # The owner must finish checkpointing an authenticated
                    # Telegram profile before the login tab can disappear.
                    raise PermissionError('Сначала завершите защищённый вход Telegram и сохраните профиль')
                was_active = to_close is session.page
                if len(pages) == 1:
                    # Keep the same context/owner capability and a usable
                    # blank page, even after closing the last tab.
                    replacement = await session.context.new_page()
                    await replacement.set_content('<!doctype html><title>Новая вкладка</title><main><h1>Новая вкладка</h1><p>Введите HTTPS-адрес в строке MiniFish.</p></main>')
                    session.page = replacement
                elif was_active:
                    session.page = pages[min(index + 1, len(pages) - 1)
                                         if index + 1 < len(pages) else index - 1]
                await to_close.close()
            elif action == 'forward':
                await session.page.go_forward(timeout=TIMEOUT_MS,
                                              wait_until='domcontentloaded')
            elif action == 'reload':
                if session.page.url != 'about:blank':
                    await session.page.reload(timeout=TIMEOUT_MS,
                                              wait_until='domcontentloaded')
            session.pending_click = None
            session.approved_click = None
            session.last_action = {
                'new': 'Открыта новая вкладка',
                'switch': 'Выбрана вкладка',
                'close': 'Закрыта вкладка',
                'forward': 'Вперёд по истории',
                'reload': 'Обновлена страница',
            }[action]
            current = self._tab_pages(session)
            return {'ok': True, 'action': action, 'active': current.index(session.page),
                    'count': len(current), 'site': urlsplit(session.page.url).hostname or ''}

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
                            if (!n.parentElement) { p.unshift(tag); break; }
                            const siblings=Array.from(n.parentElement.children).filter(x => x.tagName === n.tagName);
                            const num=siblings.indexOf(n) + 1;
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
            sensitive = typ == 'submit' or sensitive_action(label)
            if sensitive:
                now = time.monotonic()
                approved = s.approved_click
                if not (confirm_sensitive and approved and approved.get('selector') == selector
                        and approved.get('url') == s.page.url and approved.get('expires', 0) > now):
                    pending = s.pending_click
                    if not pending or pending.get('selector') != selector or pending.get('url') != s.page.url or pending.get('expires', 0) <= now:
                        s.pending_click = {'id': secrets.token_urlsafe(16), 'selector': selector,
                                           'label': (label.strip()[:120] or 'Нажатие'), 'url': s.page.url,
                                           'expires': now + 180}
                    raise PermissionError('Требуется подтверждение владельца в MiniFish /live. Затем повтори вызов с confirm_sensitive=true.')
                # A prior owner approval is consumed once before interacting with the page.
                s.approved_click = None
                s.pending_click = None
            await el.scroll_into_view_if_needed(timeout=TIMEOUT_MS)
            bounds = await el.bounding_box(timeout=TIMEOUT_MS)
            if bounds:
                await self._move_cursor(s, bounds['x'] + bounds['width'] / 2,
                                        bounds['y'] + bounds['height'] / 2)
            prior_pages = self._tab_pages(s)
            await el.click(timeout=TIMEOUT_MS)
            popups = [p for p in self._tab_pages(s) if all(p is not previous for previous in prior_pages)]
            if popups:
                s.page = popups[-1]
            s.last_action = 'Нажатие: ' + (label.strip()[:80] or selector[:80])
            return {'clicked': selector, 'url': s.page.url, 'label': label}

    async def tap(self, sid: str, x: float, y: float) -> dict:
        """Click a visible interactive element at screenshot coordinates.

        Uses the *same* approval-aware selector click path as browser_click.
        This does not grant model/widget access to owner private login mode.
        """
        s = self.get(sid)
        viewport = s.page.viewport_size or {'width': 960, 'height': 675}
        if (isinstance(x, bool) or isinstance(y, bool)
                or not isinstance(x, (int, float)) or not isinstance(y, (int, float))
                or not 0 <= x < viewport['width'] or not 0 <= y < viewport['height']):
            raise ValueError('Координаты за пределами экрана браузера')
        async with s.lock:
            selector = await s.page.evaluate("""([x,y]) => {
                const el = document.elementFromPoint(x, y);
                const target = el?.closest('button,a,input,textarea,select,[role="button"]');
                if (!target) return null;
                const rect = target.getBoundingClientRect();
                if (!rect.width || !rect.height) return null;
                let node=target, parts=[];
                while (node && node.nodeType===1 && parts.length<12) {
                    if (node.id) {parts.unshift('#'+CSS.escape(node.id));break;}
                    const tag=node.tagName.toLowerCase();
                    if (!node.parentElement) {parts.unshift(tag);break;}
                    const siblings=Array.from(node.parentElement.children)
                        .filter(n=>n.tagName===node.tagName);
                    parts.unshift(tag+':nth-of-type('+(siblings.indexOf(node)+1)+')');
                    node=node.parentElement;
                }
                return parts.join(' > ');
            }""", [x, y])
        if not isinstance(selector, str) or not selector or len(selector) > 300:
            raise ValueError('Нажми на кнопку или поле страницы')
        return await self.click(sid, selector, confirm_sensitive=False)

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
            if now - s.touched >= session_idle_limit(s) or s.page.is_closed():
                continue
            site = urlsplit(s.page.url).hostname or 'Загрузка страницы'
            result.append({'session_id': sid, 'site': site, 'action': s.last_action,
                           'viewport': s.page.viewport_size or {'width': 1280, 'height': 900},
                           'private_mode': s.private_mode,
                           'pending_click': (s.pending_click if s.pending_click and s.pending_click['expires'] > now else None)})
        return result

    def _telegram_pages(self, session: Session) -> list:
        """Locate Telegram regardless of which tab currently has focus."""
        return [page for page in self._tab_pages(session)
                if urlsplit(page.url).hostname == 'web.telegram.org']

    def telegram_session_id(self) -> str | None:
        """Existing live Telegram tab, including background tabs in one context."""
        now = time.monotonic()
        for sid, session in reversed(list(self._sessions.items())):
            if (now-session.touched < session_idle_limit(session) and
                    self._telegram_pages(session)):
                return sid
        return None

    async def telegram_logged_in(self, sid: str) -> bool:
        """Check login state without switching the user's active tab."""
        session = self._sessions.get(sid)
        if (session is None or session.private_mode or
                time.monotonic()-session.touched >= session_idle_limit(session)):
            return False
        async with session.lock:
            for page in self._telegram_pages(session):
                try:
                    if (await page.locator('#column-left').is_visible() and
                            not await page.locator('#auth-pages').is_visible()):
                        return True
                except Exception:
                    continue
            return False

    async def _encrypted_profile_state(self, session: Session) -> dict:
        """Export complete supported browser state, including sessionStorage.

        The caller encrypts the returned data immediately; no tokens are sent
        through MCP results. Never capture a different website's sessionStorage.
        """
        # IndexedDB is required for Telegram. OPFS export duplicates large
        # buffers under memory pressure; do not snapshot it on the free tier.
        state = await session.context.storage_state(indexed_db=True)
        for page in self._telegram_pages(session):
            try:
                values = await page.evaluate("""() => {
                    const out={};
                    for(let i=0;i<sessionStorage.length;i++){
                        const key=sessionStorage.key(i);
                        if(key !== null)out[key]=sessionStorage.getItem(key);
                    }
                    return out;
                }""")
                if values:
                    state['_minifish_session_storage'] = {
                        'https://web.telegram.org': values}
                break
            except Exception:
                continue
        return state

    async def telegram_authenticated_state(self, sid: str) -> dict | None:
        """Export signed-in Telegram state only for encrypted server-side saving."""
        session = self._sessions.get(sid)
        if (session is None or
                time.monotonic()-session.touched >= session_idle_limit(session)):
            return None
        async with session.lock:
            for page in self._telegram_pages(session):
                try:
                    if (await page.locator('#column-left').is_visible() and
                            not await page.locator('#auth-pages').is_visible()):
                        return await self._encrypted_profile_state(session)
                except Exception:
                    continue
            return None

    async def release_verified_telegram_login(self, sid: str) -> bool:
        """Release a private, verified saved Telegram session without tab switch."""
        session = self._sessions.get(sid)
        if session is None:
            return False
        async with session.lock:
            if not session.private_mode:
                return False
            for page in self._telegram_pages(session):
                try:
                    signed_in = (await page.locator('#column-left').is_visible() and
                                 not await page.locator('#auth-pages').is_visible())
                except Exception:
                    signed_in = False
                if signed_in:
                    session.profile_name = 'telegram'
                    session.private_mode = False
                    session.pending_click = None
                    session.approved_click = None
                    session.last_action = 'Telegram: вход сохранён, управление возвращено ассистенту'
                    return True
            return False

    async def live_jpeg(self, sid: str) -> bytes:
        """Read-only low-bandwidth frame that does not keep a session alive."""
        s = self._sessions.get(sid)
        if not s or time.monotonic()-s.touched >= session_idle_limit(s) or s.page.is_closed():
            raise ValueError('Сессия недоступна')
        # Owner-only live video stays available during private mode; MCP screenshot
        # and snapshots go through get(), which blocks them.
        # Live viewers must never monopolize the session lock and delay MCP
        # actions. A skipped frame is preferable to hanging an agent call.
        if s.lock.locked():
            raise TimeoutError('Страница занята')
        if memory_pressure():
            raise TimeoutError('Кадр временно недоступен: ограничение памяти')
        try:
            async with asyncio.timeout(4):
                async with s.lock:
                    return await s.page.screenshot(type='jpeg', quality=55, full_page=False, timeout=3000)
        except (asyncio.TimeoutError, TimeoutError):
            raise TimeoutError('Кадр временно недоступен') from None

    async def export_state(self, sid: str, *, owner: bool = False) -> dict:
        """Get browser storage for encryption; owner-only private-mode export."""
        s = self.get(sid, owner=owner)
        async with s.lock:
            return await self._encrypted_profile_state(s)

    def set_profile_name(self, sid: str, name: str) -> None:
        session = self._sessions.get(sid)
        if session is None or session.page.is_closed():
            raise ValueError('Браузерная сессия не найдена')
        # Background autosave should not keep an abandoned session alive.
        session.profile_name = name

    async def screenshot_jpeg(self, sid: str) -> bytes:
        """Compact CSS-pixel JPEG for Android: lower wire and worker memory than PNG."""
        s = self.get(sid)
        if memory_pressure(0.94):
            raise TimeoutError('Недостаточно памяти для кадра')
        async with s.lock:
            return await s.page.screenshot(type='jpeg', quality=42,
                                           scale='css', full_page=False,
                                           timeout=TIMEOUT_MS)

    async def screenshot(self, sid: str) -> bytes:
        s = self.get(sid)
        if memory_pressure():
            raise TimeoutError('Кадр временно недоступен: ограничение памяти')
        async with s.lock:
            return await s.page.screenshot(type='png', full_page=False, timeout=TIMEOUT_MS)

    async def owner_set_private(self, sid: str, enabled: bool) -> dict:
        """Owner release immediately checkpoints Telegram before MCP can resume.

        The owner must explicitly end private mode; no chat-agent access to
        private browser state is created by the checkpoint operation.
        """
        s = self.get(sid, owner=True)
        profile_saved = False
        save_error = None
        async with s.lock:
            if not enabled and s.private_mode:
                # A signed-in Telegram tab can be in the background. Never
                # accidentally release it without checkpointing its context.
                telegram_pages = [page for page in self._tab_pages(s)
                                  if urlsplit(page.url).hostname == 'web.telegram.org']
                for telegram_page in telegram_pages:
                    try:
                        signed_in = (
                            await telegram_page.locator('#column-left').is_visible()
                            and not await telegram_page.locator('#auth-pages').is_visible())
                        if signed_in:
                            if self.profile_save_callback is None:
                                raise RuntimeError('Постоянное хранилище недоступно')
                            state = await self._encrypted_profile_state(s)
                            await self.profile_save_callback('telegram', state)
                            s.profile_name = 'telegram'
                            profile_saved = True
                            break
                    except Exception as exc:
                        # No secret state, page URL or account identifier in errors.
                        save_error = 'Не удалось сохранить вход (' + type(exc).__name__ + ')'
                        break
            # A failed checkpoint must never silently hand authenticated
            # Telegram control back to MCP. Keep the same Chromium context
            # and allow the owner to retry without a second login.
            if save_error:
                s.last_action = 'Telegram: вход пока не сохранён; личный режим включён'
                return {'private_mode': True,
                        'profile_saved': False, 'save_error': save_error}
            s.private_mode = bool(enabled)
            s.pending_click = None
            s.approved_click = None
            s.last_action = ('Личный режим владельца' if enabled else 'Управление ассистента разрешено')
            return {'private_mode': s.private_mode,
                    'profile_saved': profile_saved, 'save_error': save_error}

    async def owner_approve_click(self, sid: str, request_id: str) -> dict:
        s = self.get(sid, owner=True)
        async with s.lock:
            pending = s.pending_click
            if (not pending or not secrets.compare_digest(str(pending.get('id')), str(request_id))
                    or pending['url'] != s.page.url or pending['expires'] <= time.monotonic()
                    or s.private_mode):
                raise ValueError('Подтверждение устарело или личный режим ещё включён')
            s.approved_click = {'selector': pending['selector'], 'url': pending['url'],
                                'expires': time.monotonic() + 90}
            s.pending_click = None
            return {'approved': True}

    async def owner_reject_click(self, sid: str) -> dict:
        s = self.get(sid, owner=True)
        async with s.lock:
            s.pending_click = None
            s.approved_click = None
            return {'rejected': True}

    async def owner_elements(self, sid: str) -> dict:
        """Visible action labels for mobile owner controls, with no field values or cookies."""
        s = self.get(sid, owner=True)
        async with s.lock:
            actions = await s.page.locator(
                'button:visible, a:visible, [role="button"]:visible, '
                'input[type="submit"]:visible, input[type="button"]:visible'
            ).evaluate_all("""els => els.slice(0, 50).map((el, index) => ({
                index, label: String(el.innerText || el.getAttribute('aria-label') ||
                    el.getAttribute('title') || el.getAttribute('value') ||
                    el.getAttribute('placeholder') || el.tagName.toLowerCase()).trim().slice(0, 90),
                kind: el.tagName.toLowerCase()
            }))""")
            return {'actions': actions, 'site': urlsplit(s.page.url).hostname or ''}

    async def owner_fields(self, sid: str) -> dict:
        """Owner-only: list visible browser form fields, never their values."""
        s = self.get(sid, owner=True)
        async with s.lock:
            fields = await s.page.locator('input:visible, textarea:visible, [contenteditable="true"]:visible').evaluate_all(
                """els => els.slice(0, 24).map((el, i) => {
                    // A stable per-element identity survives insertion/reordering
                    // of Telegram's country chooser. Do not expose field values.
                    if (!el.dataset.minifishOwnerField)
                        el.dataset.minifishOwnerField = (
                            Math.random().toString(36).slice(2) +
                            Math.random().toString(36).slice(2)
                        );
                    const inputLabel = el.closest('.input-field')?.querySelector(
                        '.input-field-label, label')?.textContent;
                    return {
                        ref: el.dataset.minifishOwnerField,
                        index: i,
                        kind: (el.getAttribute('type') || (el.isContentEditable ? 'text' : 'text')).toLowerCase(),
                        label: String(el.getAttribute('aria-label') ||
                            el.getAttribute('placeholder') ||
                            inputLabel ||
                            el.getAttribute('name') ||
                            el.getAttribute('id') ||
                            el.closest('label')?.innerText ||
                            'Поле ' + (i + 1)).slice(0, 90)
                    };
                })""")
            return {'fields': fields, 'site': urlsplit(s.page.url).hostname or ''}

    async def owner_control(self, sid: str, action: str, *, x=None, y=None, text=None, key=None, field_index=None, field_ref=None, element_index=None, pixels=None, axis='vertical', url=None) -> dict:
        """Owner-only manual handoff. Do not expose as an MCP tool.

        Owner may type into the browser directly (including login forms) without
        passing account credentials to ChatGPT. Never log or return typed data.
        """
        s = self.get(sid, owner=True)
        if action not in ('click', 'click_element', 'navigate', 'back', 'reload',
                          'scroll', 'type', 'type_focused', 'clear_focused', 'key', 'fill_field', 'telegram_next'):
            raise ValueError('Неизвестное действие управления')
        if action == 'navigate':
            await asyncio.to_thread(validate_url, url)
        async with s.lock:
            prior_pages = self._tab_pages(s)
            if (urlsplit(s.page.url).hostname == 'web.telegram.org'
                    and (action in ('click', 'click_element', 'telegram_next')
                         or (action == 'key' and key == 'Enter'))):
                # Never retry Telegram authentication after a flood notice.
                # Detect the notice locally; do not send the page or credentials
                # to ChatGPT or application logs.
                try:
                    flooded = await s.page.locator('body').evaluate(
                        """body => body.innerText.includes('PHONE_PASSWORD_FLOOD')""")
                except Exception:
                    flooded = False
                if flooded:
                    raise ValueError('Telegram ограничил попытки входа (PHONE_PASSWORD_FLOOD). Повторные попытки через MiniFish остановлены. Дождитесь разрешения Telegram.')
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
            elif action == 'click_element':
                if (type(element_index) is not int or not 0 <= element_index < 50):
                    raise ValueError('Выберите кнопку на странице')
                actions = s.page.locator(
                    'button:visible, a:visible, [role="button"]:visible, '
                    'input[type="submit"]:visible, input[type="button"]:visible'
                )
                if element_index >= await actions.count():
                    raise ValueError('Элемент изменился, обновите список кнопок')
                element = actions.nth(element_index)
                await element.click(timeout=5000)
                s.last_action = 'Владелец нажал кнопку сайта'
            elif action == 'navigate':
                await s.page.goto(url, timeout=TIMEOUT_MS, wait_until='domcontentloaded')
                s.last_action = 'Владелец перешёл на сайт'
            elif action == 'back':
                await s.page.go_back(timeout=TIMEOUT_MS, wait_until='domcontentloaded')
                s.last_action = 'Владелец вернулся назад'
            elif action == 'reload':
                await s.page.reload(timeout=TIMEOUT_MS, wait_until='domcontentloaded')
                s.last_action = 'Владелец обновил страницу'
            elif action == 'scroll':
                if (type(pixels) is not int or not -3000 <= pixels <= 3000):
                    raise ValueError('Некорректная прокрутка')
                if axis not in ('horizontal', 'vertical'):
                    raise ValueError('Неизвестное направление прокрутки')
                await s.page.mouse.wheel(pixels if axis == 'horizontal' else 0,
                                         pixels if axis == 'vertical' else 0)
                s.last_action = 'Владелец прокрутил страницу'
            elif action in ('type_focused', 'clear_focused'):
                # Never read field values or forward private text through MCP.
                # Phone entry is a replacement, whereas OTP multi-box widgets
                # require sequential keystrokes to advance between cells.
                if action == 'type_focused' and (
                        not isinstance(text, str) or not 0 < len(text) <= 1000):
                    raise ValueError('Введите текст от 1 до 1000 символов')
                field = await s.page.evaluate("""() => {
                    const el = document.activeElement;
                    if (!el || (el.isContentEditable && el.closest('[contenteditable="false"]')))
                        return {editable: false, phone: false};
                    if (el.isContentEditable)
                        return {editable: true, phone: false};
                    if (!el.matches('input, textarea') || el.disabled || el.readOnly)
                        return {editable: false, phone: false};
                    const excluded = ['hidden','file','button','submit','reset',
                        'checkbox','radio','range','color','date','datetime-local',
                        'month','week','time'];
                    if (el.tagName === 'INPUT' && excluded.includes((el.type||'text').toLowerCase()))
                        return {editable: false, phone: false};
                    const hints = [
                        el.getAttribute('type'), el.getAttribute('inputmode'),
                        el.getAttribute('autocomplete'), el.getAttribute('name'),
                        el.getAttribute('id'), el.getAttribute('placeholder'),
                        el.getAttribute('aria-label')
                    ].filter(Boolean).join(' ').toLowerCase();
                    const phone = el.tagName === 'INPUT' &&
                        ((el.type||'').toLowerCase() === 'tel' ||
                         /(?:^|[^a-z])(phone|telephone|mobile|tel)(?:$|[^a-z])|телефон|номер телефона/i.test(hints));
                    return {editable: true, phone};
                }""")
                if not field['editable']:
                    raise ValueError('Коснитесь поля прямо на изображении браузера, затем повторите ввод')
                if action == 'clear_focused' or field['phone']:
                    # Clear via keyboard events so controlled inputs observe the
                    # empty state; typing a new +country prefix lets the website
                    # update its country selector instead of appending old digits.
                    await s.page.keyboard.press('ControlOrMeta+A')
                    await s.page.keyboard.press('Backspace')
                if action == 'type_focused':
                    await s.page.keyboard.type(text, delay=25)
                    s.last_action = 'Владелец заменил номер' if field['phone'] else 'Владелец ввёл текст в выбранное поле'
                else:
                    s.last_action = 'Владелец очистил выбранное поле'
            elif action == 'type':
                if not isinstance(text, str) or not 0 < len(text) <= 1000:
                    raise ValueError('Текст должен содержать от 1 до 1000 символов')
                await s.page.keyboard.insert_text(text)
                s.last_action = 'Владелец ввёл текст'
            elif action == 'fill_field':
                # Fail closed for older Android widgets using unstable numeric
                # indices. Otherwise a dynamic country picker can shift the
                # phone input and silently put a phone number in Country.
                if not isinstance(field_ref, str) or not re.fullmatch(
                        r'[a-zA-Z0-9_-]{12,80}', field_ref):
                    raise ValueError('Обновите окно MiniFish и выберите поле заново')
                if not isinstance(text, str) or not 0 < len(text) <= 1000:
                    raise ValueError('Введите текст в поле MiniFish')
                target = s.page.locator(
                    'input[data-minifish-owner-field="' + field_ref + '"]:visible, '
                    'textarea[data-minifish-owner-field="' + field_ref + '"]:visible, '
                    '[contenteditable="true"][data-minifish-owner-field="' + field_ref + '"]:visible'
                )
                if await target.count() != 1:
                    raise ValueError('Выбранное поле изменилось. Обновите поля и выберите его снова')
                kind = (await target.get_attribute('type') or '').lower()
                if kind in {'hidden','file','checkbox','radio','submit','button'}:
                    raise ValueError('В это поле нельзя вводить текст')
                await target.fill(text, timeout=TIMEOUT_MS)
                # Do not report success when a reactive form has discarded the input.
                # Read only a boolean: passwords and codes must never enter responses.
                accepted = await target.evaluate(
                    "el => Boolean('value' in el ? el.value : el.textContent)")
                if not accepted:
                    raise ValueError('Поле не приняло ввод; обновите поля и попробуйте снова')
                s.last_action = 'Владелец заполнил поле'
            elif action == 'telegram_next':
                if urlsplit(s.page.url).hostname != 'web.telegram.org':
                    raise ValueError('Продолжить вход можно только в Telegram Web')
                next_button = s.page.get_by_role('button', name='NEXT', exact=True)
                if await next_button.count() != 1:
                    raise ValueError('Кнопка NEXT не найдена; обновите экран Telegram')
                await next_button.click(timeout=TIMEOUT_MS)
                s.last_action = 'Владелец подтвердил ввод в Telegram'
            else:
                allowed = {'Tab', 'Enter', 'Escape', 'Backspace', 'Delete',
                           'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight',
                           'ControlOrMeta+A'}
                if key not in allowed:
                    raise ValueError('Клавиша не разрешена')
                await s.page.keyboard.press(key)
                s.last_action = 'Владелец нажал клавишу'
            popups = [p for p in self._tab_pages(s) if all(p is not previous for previous in prior_pages)]
            if popups:
                s.page = popups[-1]
            return {'ok': True, 'site': urlsplit(s.page.url).hostname or ''}

    async def scroll(self, sid: str, pixels: int = 650, axis: str = 'vertical') -> dict:
        s = self.get(sid)
        if axis not in ('vertical', 'horizontal'):
            raise ValueError('Неизвестное направление прокрутки')
        pixels = max(-1500, min(1500, int(pixels)))
        async with s.lock:
            await s.page.mouse.wheel(pixels if axis == 'horizontal' else 0,
                                     pixels if axis == 'vertical' else 0)
            s.last_action = 'Прокрутка страницы'
            return {'scroll_pixels': pixels, 'axis': axis, 'url': s.page.url}

    async def _close_session_context(self, session: Session) -> dict:
        updated = False
        failed = False
        try:
            if self.profile_save_callback is not None:
                name = session.profile_name
                # Users may close the owner login tab before pressing
                # "Finish". Save a *new* authenticated Telegram session even
                # if no profile name has been assigned by the background task.
                telegram_page = urlsplit(session.page.url).hostname == 'web.telegram.org'
                if telegram_page:
                    try:
                        signed_in = (
                            await session.page.locator('#column-left').is_visible()
                            and not await session.page.locator('#auth-pages').is_visible()
                        )
                    except Exception:
                        signed_in = False
                    if signed_in:
                        name = 'telegram'
                    elif name == 'telegram':
                        name = None  # never replace a saved login with QR state
                if name:
                    state = await self._encrypted_profile_state(session)
                    await self.profile_save_callback(name, state)
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
