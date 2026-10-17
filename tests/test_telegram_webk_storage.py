"""Telegram Web K 2026 storage regression. Fixtures contain no auth secrets."""
import pytest
from playwright.async_api import async_playwright

from engine import BrowserEngine
from server import _telegram_state_shape


async def put_synthetic_record(page, db_name: str, store_name: str):
    await page.evaluate("""async ({name, storeName}) => {
        await new Promise((resolve, reject) => {
            const request = indexedDB.open(name, 1);
            request.onupgradeneeded = () => request.result.createObjectStore(storeName);
            request.onerror = () => reject(request.error);
            request.onsuccess = () => {
                const db = request.result;
                const tx = db.transaction(storeName, 'readwrite');
                tx.objectStore(storeName).put('test-fixture', 'key');
                tx.oncomplete = () => { db.close(); resolve(); };
                tx.onerror = () => { db.close(); reject(tx.error); };
            };
        });
    }""", {'name': db_name, 'storeName': store_name})


@pytest.mark.asyncio
@pytest.mark.parametrize('db_name,store_name', [
    ('telegram', 'session'),
    ('tweb', 'session'),
    ('tweb-common', 'session'),
    ('tweb-account-1', 'session'),
    ('tweb-account-4', 'session__encrypted'),
])
async def test_readiness_detects_actual_telegram_webk_databases(db_name, store_name):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            context = await browser.new_context()
            page = await context.new_page()
            await page.route('https://web.telegram.org/**', lambda route: route.fulfill(
                status=200, content_type='text/html', body='<title>Safe fixture</title>'))
            await page.goto('https://web.telegram.org/k/')
            engine = BrowserEngine()
            assert await engine._telegram_indexeddb_auth_ready(page) is False
            await put_synthetic_record(page, db_name, store_name)
            assert await engine._telegram_indexeddb_auth_ready(page) is True
            await context.close()
        finally:
            await browser.close()


def test_profile_shape_counts_modern_webk_session_records_without_values():
    secret = 'FAKE_SECRET_CANNOT_BE_DISCLOSED'
    state = {'origins': [{
        'origin': 'https://web.telegram.org',
        'indexedDB': [
            {'name': 'tweb-account-1', 'stores': [
                {'name': 'session__encrypted', 'records': [{'value': secret}]}]},
            {'name': 'tweb-common', 'stores': [
                {'name': 'session', 'records': [{'value': secret}]}]}]}]}
    shape = _telegram_state_shape(state)
    assert shape['telegram_session_db'] is True
    assert shape['telegram_session_records'] == 2
    assert secret not in str(shape)
