"""Regression tests for MiniFish encrypted Supabase HTTPS persistence."""
import base64
import json
from types import SimpleNamespace

from remote_store import RemoteStore


def test_gateway_durable_and_encrypted(monkeypatch):
    requests=[]
    def fake_post(url, **kwargs):
        requests.append({'url': url, **kwargs})
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {'ok':True,'rowcount':1,'rows':[]})
    monkeypatch.setenv('MINIFISH_STORE_API_URL',
                       'https://test-project.supabase.co/functions/v1/minifish-store')
    monkeypatch.setenv('MINIFISH_STORE_API_TOKEN','a'*96)
    monkeypatch.setenv('MINIFISH_SECRET','b'*64)
    monkeypatch.setattr('httpx.post', fake_post)
    store=RemoteStore()
    assert store.durable
    assert store.sql("SELECT site FROM mf_profiles WHERE name=?") == (
        "SELECT site FROM minifish.mf_profiles WHERE name=" + chr(36) + "1")
    state={'cookies':[{'name':'session','value':'example-private-cookie'}],
           'origins':[]}
    store.save_profile('test','example.com',state)
    body=json.dumps(requests[-1]['json'])
    assert 'example-private-cookie' not in body
    assert requests[-1]['headers']['x-minifish-token']=='a'*96


def test_gateway_decodes_bytes(monkeypatch):
    secret=b'secret-encrypted-binary'
    def fake_post(url, **kwargs):
        if kwargs['json']['fetch']:
            return SimpleNamespace(raise_for_status=lambda: None,
                                   json=lambda: {'ok':True,
                                       'rows':[[{'binary':base64.b64encode(secret).decode()}]]})
        return SimpleNamespace(raise_for_status=lambda: None,
                               json=lambda: {'ok':True,'rowcount':1})
    monkeypatch.setenv('MINIFISH_STORE_API_URL',
                       'https://test-project.supabase.co/functions/v1/minifish-store')
    monkeypatch.setenv('MINIFISH_STORE_API_TOKEN','a'*96)
    monkeypatch.setenv('MINIFISH_SECRET','b'*64)
    monkeypatch.setattr('httpx.post', fake_post)
    store=RemoteStore()
    rows=store.execute('SELECT encrypted_state FROM mf_profiles WHERE name=?',
                       ('test',),fetch=True)
    assert rows == [(secret,)]
