"""Chromium DOM snapshot selectors are valid CSS, including root HTML."""
import pytest
from playwright.async_api import async_playwright
from engine import BrowserEngine, Session


@pytest.mark.asyncio
async def test_snapshot_selector_can_target_a_button_on_real_chromium():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=['--disable-dev-shm-usage'])
        try:
            context = await browser.new_context()
            page = await context.new_page()
            await page.set_content('<!doctype html><html><body><main><button id="go">Test</button><a href="#help">More</a></main></body></html>')
            engine = BrowserEngine()
            engine._sessions['selector-test'] = Session(context=context, page=page)
            result = await engine.snapshot('selector-test')
            assert len(result['elements']) == 2
            for item in result['elements']:
                selector = item['selector']
                assert ':nth-of-type(0)' not in selector
                assert await page.locator(selector).count() == 1
                assert await page.locator(selector).first.is_visible()
        finally:
            await browser.close()
