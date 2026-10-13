"""Exercise real API signing and purchase gates, not a mocked judge."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.store import get_store

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('STORE_BACKEND','sqlite');monkeypatch.setenv('SQLITE_PATH',str(tmp_path/'state.sqlite3'))
    get_store.cache_clear()
    with TestClient(app) as c:
        c.get('/api/session')
        yield c
    get_store.cache_clear()


def prepare(c):
    d=c.post('/api/intents',json={'domain':'flight','message':'Nonstop flight EWR to MCO on 2026-11-12 under $300','mode':'offline'}).json()
    fields={k:None for k in c.get('/api/profiles/flight').json()['fields']}
    fields.update(nonstop=True,max_total_cents=29999,origin_airports=['EWR'],destination_airports=['MCO'],departure_date='2026-11-12')
    d=c.post(f"/api/intents/{d['id']}/answers",json={'revision':d['revision'],'fields':fields,'unsupported':[],'confirmation':True}).json()
    r=c.post(f"/api/intents/{d['id']}/approve",json={'revision':d['revision'],'digest':d['digest'],'confirmation':True})
    assert r.status_code==200,r.text
    return d,r.json()['offers']


def decision(c,d,offer):
    r=c.post('/api/check',json={'intent_id':d['id'],'offer_id':offer['id']})
    assert r.status_code==200,r.text
    return r.json()


def test_purchase_refuses_mismatch_until_exact_exception(client):
    d,offers=prepare(client);v=decision(client,d,offers[1]);assert v['status']=='HOLD'
    p={'decision_id':v['id'],'idempotency_key':'purchase-unique-1'}
    assert client.post('/api/purchase',json=p).status_code==409
    bad=client.post(f"/api/decisions/{v['id']}/exceptions",json={'check_ids':['nonstop'],'offer_hash':'wrong','confirmation':True})
    assert bad.status_code==409
    r=client.post(f"/api/decisions/{v['id']}/exceptions",json={'check_ids':['nonstop'],'offer_hash':v['offer_hash'],'confirmation':True})
    assert r.status_code==200,r.text
    receipt=client.post('/api/purchase',json=p);assert receipt.status_code==200,receipt.text
    assert receipt.json()['mode']=='simulated'
    again=client.post('/api/purchase',json=p);assert again.json()['id']==receipt.json()['id']
    evidence=client.get(f"/api/purchases/{receipt.json()['id']}/evidence").json()
    assert evidence['final_decision']=='dispute analyst'
    assert evidence['exceptions'][0]['accepted_value'] is False
    assert evidence['exceptions'][0]['offer_hash']==v['offer_hash']
    assert evidence['signed_evidence']


def test_matching_purchase_passes(client):
    d,o=prepare(client);v=decision(client,d,o[0]);assert v['status']=='PASS'
    assert client.post('/api/purchase',json={'decision_id':v['id'],'idempotency_key':'matched-purchase-1'}).status_code==200


def test_cross_session_cannot_use_decision(client):
    d,o=prepare(client);v=decision(client,d,o[0])
    client.cookies.clear();client.get('/api/session')
    assert client.post('/api/purchase',json={'decision_id':v['id'],'idempotency_key':'other-session-1'}).status_code==404


def test_approval_needs_complete_explicit_review(client):
    d=client.post('/api/intents',json={'message':'Book cheapest flight please','mode':'offline'}).json()
    assert client.post(f"/api/intents/{d['id']}/approve",json={'revision':d['revision'],'digest':d['digest'],'confirmation':True}).status_code==409


def test_stale_revision_and_false_confirmation(client):
    d,o=prepare(client)
    assert client.post(f"/api/intents/{d['id']}/approve",json={'revision':0,'digest':d['digest'],'confirmation':True}).status_code==409
    assert client.post(f"/api/intents/{d['id']}/approve",json={'revision':d['revision'],'digest':d['digest'],'confirmation':False}).status_code==409


def test_cross_origin_write_is_refused(client):
    assert client.post('/api/intents',headers={'Origin':'https://evil.example'},json={'message':'Buy a flight','mode':'offline'}).status_code==403
