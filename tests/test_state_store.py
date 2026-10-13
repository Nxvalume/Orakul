"""Security and persistence regressions for MiniFish profiles and job queue."""
import json
import os
import time

import pytest

from state_store import Store
from jobs import check_steps, JobRunner


def make_store(tmp_path):
    return Store(database_url='', sqlite_path=str(tmp_path/'minifish.sqlite3'), secret='x'*64)


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
    monkeypatch.setenv('BROWSER_ALLOWED_DOMAINS','example.com;github.com')
    store=make_store(tmp_path)
    runner=JobRunner(object(),store)
    with pytest.raises(ValueError):
        runner.submit('https://example.com',[{'action':'snapshot'}],profile='missing')
