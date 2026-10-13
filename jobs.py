"""Bounded background browser workflow executor.

Runs deterministic actions independently of the chat request, using an isolated
Playwright session. Does not interpret arbitrary natural-language instructions.
All actions are domain constrained and potentially destructive clicks blocked.
"""
from __future__ import annotations

import asyncio
import time
from urllib.parse import urlsplit

from engine import validate_url
from state_store import Store

MAX_STEPS = 20
ALLOWED = {'goto', 'click', 'fill', 'select', 'scroll', 'wait', 'snapshot'}
MAX_DELAY_SECONDS = 30 * 24 * 60 * 60


def check_steps(url, steps):
    validate_url(url)
    if not isinstance(steps, list) or not (1 <= len(steps) <= MAX_STEPS):
        raise ValueError('Укажите от 1 до 20 шагов')
    cleaned = []
    for raw in steps:
        if not isinstance(raw, dict) or raw.get('action') not in ALLOWED:
            raise ValueError('Недопустимый шаг')
        act = raw['action']
        s = {'action': act}
        if act == 'goto':
            s['url'] = validate_url(raw.get('url', ''))
        if act in ('click','fill','select','wait'):
            selector = raw.get('selector','')
            if not isinstance(selector,str) or not 0 < len(selector) <= 300:
                raise ValueError('Некорректный CSS-селектор')
            s['selector'] = selector
        if act in ('fill','select'):
            value = raw.get('value','')
            if not isinstance(value,str) or not 0 < len(value) <= 1000:
                raise ValueError('Некорректное значение поля')
            s['value'] = value
        if act == 'scroll':
            pixels = raw.get('pixels',650)
            if isinstance(pixels,bool) or not isinstance(pixels,int) or not -1500 <= pixels <= 1500:
                raise ValueError('Некорректная прокрутка')
            s['pixels'] = pixels
        if act == 'wait':
            timeout = raw.get('timeout_ms',8000)
            if isinstance(timeout,bool) or not isinstance(timeout,int) or not 100 <= timeout <= 15000:
                raise ValueError('Ожидание не более 15 секунд')
            s['timeout_ms'] = timeout
        cleaned.append(s)
    return cleaned


class JobRunner:
    def __init__(self, engine, store: Store):
        self.engine = engine
        self.store = store
        self._task = None
        self._stop = asyncio.Event()

    def submit(self, url: str, steps: list, profile: str | None = None,
               run_at: float | None = None):
        steps = check_steps(url, steps)
        if profile:
            record = self.store.get_profile(profile)
            if urlsplit(url).hostname != record['site']:
                raise ValueError('Адрес задачи должен совпадать с доменом профиля')
        start = time.time() if run_at is None else run_at
        if isinstance(start,bool) or not isinstance(start,(int,float)) or not time.time()-30 <= start <= time.time()+MAX_DELAY_SECONDS:
            raise ValueError('Время запуска: сейчас или в течение следующих 30 дней')
        return self.store.enqueue(profile=profile,site=url,steps=steps,run_at=start)

    async def start(self):
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._loop(), name='minifish-background-worker')

    async def stop(self):
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self):
        while not self._stop.is_set():
            try:
                for job_id in await asyncio.to_thread(self.store.due_ids):
                    await self.execute(job_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                # The worker must not dump private job payloads or credentials.
                pass
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=4)
            except asyncio.TimeoutError:
                pass

    async def execute(self, job_id: str):
        job = await asyncio.to_thread(self.store.claim, job_id)
        if not job:
            return
        sid = None
        progress = 0
        try:
            state = None
            if job['profile']:
                record = await asyncio.to_thread(self.store.get_profile, job['profile'])
                if urlsplit(job['site']).hostname != record['site']:
                    raise ValueError('Домен профиля не совпадает')
                state = record['state']
            opened = await self.engine.open(job['site'], storage_state=state,
                                            profile_name=job['profile'])
            sid = opened['session_id']
            for step in job['steps']:
                action = step['action']
                if action == 'goto':
                    await self.engine.goto(sid, step['url'])
                elif action == 'click':
                    await self.engine.click(sid, step['selector'], False)
                elif action == 'fill':
                    await self.engine.fill(sid, step['selector'], step['value'])
                elif action == 'select':
                    await self.engine.select(sid, step['selector'], step['value'])
                elif action == 'scroll':
                    await self.engine.scroll(sid, step['pixels'])
                elif action == 'wait':
                    s = self.engine.get(sid)
                    async with s.lock:
                        await s.page.locator(step['selector']).first.wait_for(
                            state='visible',timeout=step['timeout_ms'])
                elif action == 'snapshot':
                    # A requested final snapshot is encrypted separately from the status.
                    snap = await self.engine.snapshot(sid)
                    await asyncio.to_thread(self.store.save_job_result, job_id, {
                        'title': str(snap.get('title',''))[:200],
                        'site': urlsplit(str(snap.get('url',''))).hostname or '',
                        'text': str(snap.get('text',''))[:4000]})
                progress += 1
                await asyncio.to_thread(self.store.set_job, job_id,'running',
                                        progress=progress,summary='Шаги выполняются')
            if job['profile']:
                fresh = await self.engine.export_state(sid)
                await asyncio.to_thread(self.store.save_profile, job['profile'],
                                        urlsplit(job['site']).hostname, fresh)
            self.store.set_job(job_id,'done',progress=progress,summary='Все шаги выполнены')
        except asyncio.CancelledError:
            self.store.set_job(job_id,'interrupted',progress=progress,summary='Запуск прерван')
            raise
        except Exception as exc:
            # No exception strings: site errors may embed credentials in URLs/text.
            self.store.set_job(job_id,'failed',progress=progress,
                               summary='Ошибка на шаге '+str(progress+1)+': '+type(exc).__name__)
        finally:
            if sid:
                try:
                    await self.engine.close(sid)
                except Exception:
                    pass
