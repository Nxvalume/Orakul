"""Real Chromium state round-trip without contacting Telegram or test domains.

The synthetic HTTPS origin is intercepted fully inside Playwright. Validates
cookies, localStorage and IndexedDB are restored in a completely new context.
"""
import pytest
from playwright.async_api import async_playwright

ORIGIN = "https://minifish-local-fixture.example"
HTML = "<!doctype html><html><body><input id='phone' placeholder='Phone'><button id='submit'>Next</button></body></html>"


@pytest.mark.asyncio
async def test_context_restarts_with_cookies_localstorage_and_indexeddb():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=['--disable-dev-shm-usage'])
        try:
            first = await browser.new_context(viewport={'width': 420, 'height': 760})
            await first.route(ORIGIN + '/**', lambda route: route.fulfill(
                status=200, content_type='text/html', body=HTML))
            page = await first.new_page()
            await page.goto(ORIGIN + '/login')
            await first.add_cookies([{'name': 'test_cookie', 'value': 'fixture-only',
                'url': ORIGIN}])
            await page.evaluate("""async () => {
                localStorage.setItem('fixture', 'saved');
                await new Promise((resolve, reject) => {
                    const request = indexedDB.open('minifish-test', 1);
                    request.onupgradeneeded = () => {
                        request.result.createObjectStore('session');
                    };
                    request.onerror = () => reject(request.error);
                    request.onsuccess = () => {
                        const tx = request.result.transaction('session', 'readwrite');
                        tx.objectStore('session').put('persisted', 'fixture');
                        tx.oncomplete = () => { request.result.close(); resolve(); };
                        tx.onerror = () => reject(tx.error);
                    };
                });
            }""")
            state = await first.storage_state(indexed_db=True)
            assert any(origin.get('indexedDB') for origin in state['origins'])
            await first.close()
            resumed = await browser.new_context(
                storage_state=state, viewport={'width': 420, 'height': 760})
            await resumed.route(ORIGIN + '/**', lambda route: route.fulfill(
                status=200, content_type='text/html', body=HTML))
            second = await resumed.new_page()
            await second.goto(ORIGIN + '/login')
            result = await second.evaluate("""async () => ({
                local: localStorage.getItem('fixture'),
                indexed: await new Promise((resolve, reject) => {
                    const request = indexedDB.open('minifish-test', 1);
                    request.onerror = () => reject(request.error);
                    request.onsuccess = () => {
                        const tx = request.result.transaction('session', 'readonly');
                        const read = tx.objectStore('session').get('fixture');
                        read.onsuccess = () => resolve(read.result);
                        read.onerror = () => reject(read.error);
                    };
                })
            })""")
            assert result == {'local': 'saved', 'indexed': 'persisted'}
            assert any(c['name'] == 'test_cookie' and c['value'] == 'fixture-only'
                       for c in await resumed.cookies(ORIGIN))
            await resumed.close()
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_real_browser_mobile_fields_and_keyboard():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=['--disable-dev-shm-usage'])
        try:
            context = await browser.new_context(viewport={'width': 390, 'height': 844},
                                                 is_mobile=True, has_touch=True)
            page = await context.new_page()
            await page.set_content(HTML)
            fields = page.locator('input:visible')
            assert await fields.count() == 1
            await fields.nth(0).fill('synthetic123')
            assert await page.locator('#phone').input_value() == 'synthetic123'
            await fields.nth(0).press('Backspace')
            assert await page.locator('#phone').input_value() == 'synthetic12'
            await context.close()
        finally:
            await browser.close()
