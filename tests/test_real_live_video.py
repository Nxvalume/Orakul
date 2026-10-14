"""Integration: Chromium really streams JPEG frames and shows MiniFish cursor."""
import asyncio
import base64

import pytest
from playwright.async_api import async_playwright

from engine import CURSOR_INIT


@pytest.mark.asyncio
async def test_real_chromium_screencast_and_visible_pointer():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True, args=['--disable-dev-shm-usage'])
        try:
            context = await browser.new_context(viewport={'width':480,'height':360})
            await context.add_init_script(CURSOR_INIT)
            page = await context.new_page()
            await page.goto('data:text/html,<html><body><button>Test</button></body></html>')
            assert await page.locator('#__minifish_cursor').count() == 1
            await page.mouse.move(120,130)
            opacity = await page.locator('#__minifish_cursor').evaluate(
                '(el) => el.style.opacity')
            assert opacity == '1'

            cdp = await context.new_cdp_session(page)
            frames = asyncio.Queue(maxsize=4)
            cdp.on('Page.screencastFrame', lambda event: frames.put_nowait(event)
                   if not frames.full() else None)
            try:
                await cdp.send('Page.startScreencast', {
                    'format':'jpeg','quality':48,'maxWidth':480,
                    'maxHeight':360,'everyNthFrame':1})
                await page.evaluate(
                    """() => { document.body.style.background = '#123456'; }""")
                frame = await asyncio.wait_for(frames.get(), timeout=9)
                binary = base64.b64decode(frame['data'])
                assert binary.startswith(bytes.fromhex('ffd8ff'))
                assert len(binary) > 100
                await cdp.send('Page.screencastFrameAck',
                               {'sessionId':frame['sessionId']})
            finally:
                await cdp.send('Page.stopScreencast')
                await cdp.detach()
        finally:
            await browser.close()
