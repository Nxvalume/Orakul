"""Low-latency authenticated browser screencast over WebSocket.

Chromium CDP emits real JPEG video frames as the page repaints. A bounded
queue drops stale frames; each frame is acknowledged immediately, so the MCP
browser controller is not blocked by a slow phone or network connection.
"""
from __future__ import annotations

import asyncio
import base64
import re
import time
from urllib.parse import urlsplit

from starlette.websockets import WebSocket, WebSocketDisconnect

_viewing: set[str] = set()
MAX_FPS = 8
MAX_FRAME_BYTES = 300_000


def same_origin(ws: WebSocket) -> bool:
    origin = ws.headers.get('origin', '')
    host = ws.headers.get('host', '').lower()
    if not origin or not host:
        return False
    parsed = urlsplit(origin)
    return parsed.scheme in ('https', 'http') and parsed.netloc.lower() == host


def screencast_socket(engine, authorized_owner):
    async def video(ws: WebSocket):
        if not authorized_owner(ws) or not same_origin(ws):
            await ws.close(code=1008)
            return
        sid = ws.query_params.get('session_id', '')
        if not re.fullmatch(r'[0-9a-f-]{36}', sid):
            await ws.close(code=1008)
            return
        s = engine._sessions.get(sid)
        if (s is None or s.page.is_closed()
                or time.monotonic() - s.touched > 900 or sid in _viewing):
            await ws.close(code=1008)
            return

        _viewing.add(sid)
        cdp = None
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1)
        ack_tasks: set[asyncio.Task] = set()

        def frame_received(event: dict):
            if 'sessionId' in event and cdp is not None and len(ack_tasks) < 3:
                # Bound in-flight CDP acknowledgement tasks. Unbounded
                # tasks accumulate when the phone/network is slow.
                task = asyncio.create_task(cdp.send(
                    'Page.screencastFrameAck', {'sessionId': event['sessionId']}))
                ack_tasks.add(task)
                task.add_done_callback(ack_tasks.discard)
            encoded = event.get('data')
            if isinstance(encoded, str) and len(encoded) <= MAX_FRAME_BYTES * 2:
                if queue.full():
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                queue.put_nowait(encoded)

        try:
            await ws.accept()
            cdp = await s.context.new_cdp_session(s.page)
            cdp.on('Page.screencastFrame', frame_received)
            await cdp.send('Page.startScreencast', {
                'format': 'jpeg', 'quality': 40,
                'maxWidth': 800, 'maxHeight': 562,
                'everyNthFrame': 1,
            })
            await ws.send_json({'type': 'ready', 'mode': 'live-jpeg',
                                'max_fps': MAX_FPS})
            last_frame = 0.0
            while engine._sessions.get(sid) is s and not s.page.is_closed():
                try:
                    encoded = await asyncio.wait_for(queue.get(), timeout=6)
                except asyncio.TimeoutError:
                    await ws.send_json({'type': 'heartbeat'})
                    s.touched = time.monotonic()
                    continue
                delta = 1 / MAX_FPS - (time.monotonic() - last_frame)
                if delta > 0:
                    await asyncio.sleep(delta)
                data = base64.b64decode(encoded, validate=True)
                if not data or len(data) > MAX_FRAME_BYTES:
                    continue
                await ws.send_bytes(data)
                last_frame = time.monotonic()
                # Owner actively watching the secure live video keeps it open.
                s.touched = last_frame
        except (WebSocketDisconnect, RuntimeError, ConnectionError, asyncio.CancelledError):
            pass
        except Exception:
            # Do not expose browser data, auth headers or raw CDP messages.
            try:
                await ws.send_json({'type': 'unavailable'})
            except Exception:
                pass
        finally:
            if cdp is not None:
                try:
                    await cdp.send('Page.stopScreencast')
                    await cdp.detach()
                except Exception:
                    pass
            if ack_tasks:
                for task in ack_tasks:
                    task.cancel()
            _viewing.discard(sid)
            try:
                await ws.close()
            except Exception:
                pass

    return video
