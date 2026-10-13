"""One-off boot diagnostic; never prints credentials or cookie data."""
import asyncio
from engine import BrowserEngine

async def smoke():
    engine = BrowserEngine()
    sid = None
    try:
        opened = await engine.open('https://example.com')
        sid = opened['session_id']
        snapshot = await engine.snapshot(sid)
        if 'example' not in snapshot['title'].lower():
            raise AssertionError('Unexpected title')
        png = await engine.screenshot(sid)
        if not png.startswith(b'\x89PNG\r\n\x1a\n') or len(png) < 100:
            raise AssertionError('Chromium screenshot missing')
        print('MINIFISH_SMOKE_OK: Chromium navigation, DOM and screenshot', flush=True)
    except Exception as exc:
        print('MINIFISH_SMOKE_FAILED: ' + type(exc).__name__ + ': ' + str(exc)[:250], flush=True)
    finally:
        try:
            if sid:
                await engine.close(sid)
            await engine.shutdown()
        except Exception as exc:
            print('MINIFISH_SMOKE_CLEANUP_FAILED: ' + type(exc).__name__, flush=True)

if __name__ == '__main__':
    asyncio.run(smoke())
