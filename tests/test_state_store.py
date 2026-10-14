"""Security and persistence regressions for MiniFish profiles and job queue."""
import json
import os
import time

import pytest

from state_store import Store
from jobs import check_steps, JobRunner


def make_store(tmp_path):
    return Store(database_url='', sqlite_path=str(tmp_path/'minifish.sqlite3'), secret='x'*64)


def test_postgres_schema_is_private(tmp_path):
    store = make_store(tmp_path)
    store.is_postgres = True
    assert store.sql('SELECT * FROM mf_profiles WHERE name=?') == (
        'SELECT * FROM minifish.mf_profiles WHERE name=%s')
    assert store.sql('ALTER TABLE mf_jobs ENABLE ROW LEVEL SECURITY') == (
        'ALTER TABLE minifish.mf_jobs ENABLE ROW LEVEL SECURITY')


def test_owner_domains_survive_store_reopen(tmp_path):
    first = make_store(tmp_path)
    first.save_domain('example.com')
    assert make_store(tmp_path).list_domains() == ['example.com']
    with pytest.raises(ValueError):
        first.save_domain('exampleXcom')
    with pytest.raises(ValueError):
        first.save_domain('127.0.0.1')


def test_profile_encrypted_and_restored(tmp_path):
    store=make_store(tmp_path)
    state={'cookies':[{'name':'session','value':'private-cookie-123','domain':'example.com',
                       'path':'/','expires':-1,'httpOnly':True,'secure':True,'sameSite':'Lax'}],
           'origins':[]}
    saved=store.save_profile('test_browser','example.com',state)
    assert saved['name']=='test_browser'
    data=(tmp_path/'minifish.sqlite3').read_bytes()
    assert b'private-cookie-123' not in data
    assert store.get_profile('test_browser')['state']==state
    # Same key can read the profile across process restart.
    other=make_store(tmp_path)
    assert other.get_profile('test_browser')['state']==state
    with pytest.raises(ValueError):
        other.get_profile('../bad')
    assert other.delete_profile('test_browser')['deleted']


def test_jobs_are_encrypted_and_recover_safely(tmp_path):
    store=make_store(tmp_path)
    steps=[{'action':'fill','selector':'#search','value':'sensitive-test-string'}]
    job=store.enqueue(profile=None,site='https://example.com',steps=steps,run_at=time.time())
    assert job['status']=='queued'
    assert b'sensitive-test-string' not in (tmp_path/'minifish.sqlite3').read_bytes()
    claimed=store.claim(job['id'])
    assert claimed['steps']==steps
    # A running workflow must NOT automatically be repeated after crash.
    restarted=make_store(tmp_path)
    assert restarted.get_job(job['id'])['status']=='interrupted'
    assert job['id'] not in restarted.due_ids()


def test_job_result_encrypted(tmp_path):
    store=make_store(tmp_path)
    job=store.enqueue(profile=None,site='https://example.com',
                      steps=[{'action':'snapshot'}],run_at=time.time())
    store.save_job_result(job['id'], {'title':'Result', 'text':'private-page-text'})
    raw=(tmp_path/'minifish.sqlite3').read_bytes()
    assert b'private-page-text' not in raw
    data=make_store(tmp_path).get_job_result(job['id'])
    assert data['result']['text']=='private-page-text'


@pytest.mark.asyncio
async def test_background_job_executes_without_open_chat(tmp_path):
    class BrowserStub:
        def __init__(self):self.closed=False
        async def open(self,url,**kwargs):return {'session_id':'test-session'}
        async def snapshot(self,sid):
            return {'url':'https://example.com/','title':'Example','text':'Completed'}
        async def close(self,sid):self.closed=True
    store=make_store(tmp_path)
    job=store.enqueue(profile=None,site='https://example.com',
                      steps=[{'action':'snapshot'}],run_at=time.time())
    engine=BrowserStub()
    await JobRunner(engine,store).execute(job['id'])
    assert engine.closed
    assert store.get_job(job['id'])['status']=='done'
    assert store.get_job_result(job['id'])['result']['text']=='Completed'


@pytest.mark.asyncio
async def test_worker_consumes_job_independently_of_client(tmp_path):
    import asyncio
    class BrowserStub:
        async def open(self, url, **kwargs):
            return {'session_id':'background-worker-session'}
        async def snapshot(self, sid):
            return {'url':'https://example.com','title':'Example','text':'Worker finished'}
        async def close(self, sid):
            return {'closed':True}
    store=make_store(tmp_path)
    job=store.enqueue(profile=None, site='https://example.com',
                      steps=[{'action':'snapshot'}],run_at=time.time())
    runner=JobRunner(BrowserStub(),store)
    await runner.start()
    try:
        for _ in range(40):
            if store.get_job(job['id'])['status']=='done':
                break
            await asyncio.sleep(0.05)
    finally:
        await runner.stop()
    assert store.get_job(job['id'])['status']=='done'


def test_queue_cancel(tmp_path):
    store=make_store(tmp_path)
    job=store.enqueue(profile=None,site='https://example.com',
                      steps=[{'action':'snapshot'}],run_at=time.time())
    assert store.cancel(job['id'])['status']=='cancelled'
    assert store.claim(job['id']) is None
    with pytest.raises(ValueError):
        store.cancel(job['id'])


def test_validate_background_workflow(monkeypatch):
    monkeypatch.setenv('BROWSER_ALLOWED_DOMAINS','example.com')
    monkeypatch.setattr('engine.socket.getaddrinfo', lambda *a, **kw: [(None,None,None,None,('93.184.215.14',443))])
    assert check_steps('https://example.com',[{'action':'snapshot'}])==[{'action':'snapshot'}]
    for spec in ([{'action':'execute_js','value':'alert(1)'}],
                 [{'action':'goto','url':'http://example.com'}],
                 [{'action':'click','selector':''}],
                 [{'action':'wait','selector':'#x','timeout_ms':60000}]):
        with pytest.raises(ValueError):
            check_steps('https://example.com',spec)
    with pytest.raises(ValueError):
        check_steps('https://example.com',[])


def test_unavailable_profile_or_mismatched_domain(tmp_path,monkeypatch):
    monkeypatch.setenv('BROWSER_ALLOWED_DOMAINS','example.com,github.com')
    monkeypatch.setattr('engine.socket.getaddrinfo', lambda *a, **kw: [(None,None,None,None,('93.184.215.14',443))])
    store=make_store(tmp_path)
    runner=JobRunner(object(),store)
    with pytest.raises(ValueError):
        runner.submit('https://example.com',[{'action':'snapshot'}],profile='missing')
