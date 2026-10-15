"""Regressions for compressed encrypted browser authentication state."""
import json
from pathlib import Path

from state_store import Store, MAX_STATE_SIZE


def test_large_telegram_state_is_saved_encrypted_and_read_back(tmp_path):
    db=Store(database_url='', sqlite_path=str(tmp_path/'mf-test.sqlite'),
             secret='profile-test-only-secret-abcde'*3)
    fake_state={'cookies':[{'name':'fake', 'value':'sentinel-secret-never-leak'}],
                'origins':[{'origin':'https://web.telegram.org',
                            'localStorage':[{'name':'mock', 'value':'A'*1_200_000}]}]}
    result=db.save_profile('telegram','web.telegram.org',fake_state)
    assert result['name']=='telegram'
    loaded=db.get_profile('telegram')
    assert loaded['site']=='web.telegram.org'
    assert loaded['state']==fake_state
    encrypted=db.execute('SELECT encrypted_state FROM mf_profiles WHERE name=?',
                         ('telegram',),fetch=True)[0][0]
    assert b'sentinel-secret-never-leak' not in encrypted
    assert len(encrypted)<MAX_STATE_SIZE // 2


def test_old_uncompressed_encrypted_profile_still_opens(tmp_path):
    db=Store(database_url='',sqlite_path=str(tmp_path/'legacy.sqlite'),
             secret='profile-test-only-secret-abcde'*3)
    obj={'cookies':[{'name':'test','value':'legacy'}], 'origins':[]}
    old=db.cipher.encrypt(json.dumps(obj).encode())
    db.execute('INSERT INTO mf_profiles (name,site,encrypted_state,updated) VALUES (?,?,?,?)',
               ('telegram','web.telegram.org',old,1.0))
    assert db.get_profile('telegram')['state']==obj
