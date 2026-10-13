"""Additional adversarial and cross-domain acceptance scenarios."""
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.store import get_store,SQLiteStore
from app.vi_adapter import issue,sign_offer,read_signed
from test_enforcement import client,prepare,decision


def test_expired_signed_offer_is_nonwaivable(client):
    d,o=prepare(client);sid=client.cookies.get('ij_session')
    def expire(s):
        stored=s['offers'][o[0]['id']]
        payload=read_signed(stored['bundle']['checkout_jwt'],'merchant','intent-judge-checkout+jwt');payload['exp']=1
        from app.vi_adapter import sign_record
        jwt=sign_record(payload,'merchant','intent-judge-checkout+jwt')
        stored['bundle']=issue(s['drafts'][d['id']]['approved'],jwt)
    get_store().mutate(sid,expire)
    v=decision(client,d,o[0]);assert v['status']=='BLOCK'
    assert client.post(f"/api/decisions/{v['id']}/exceptions",json={'check_ids':['cryptographic_integrity'],'offer_hash':v['offer_hash'],'confirmation':True}).status_code==409


def test_over_budget_needs_new_native_authorization(client):
    d,o=prepare(client);sid=client.cookies.get('ij_session')
    def reprice(s):
        stored=s['offers'][o[0]['id']]
        payload=read_signed(stored['bundle']['checkout_jwt'],'merchant','intent-judge-checkout+jwt');payload['total_cents']=31000
        stored['bundle']=issue(s['drafts'][d['id']]['approved'],sign_offer(payload))
    get_store().mutate(sid,reprice)
    v=decision(client,d,o[0]);assert v['status']=='HOLD';assert not v['native_vi_passed']
    p={'decision_id':v['id'],'idempotency_key':'reprice-consent-1'}
    assert client.post('/api/purchase',json=p).status_code==409
    response=client.post(f"/api/decisions/{v['id']}/exceptions",json={'check_ids':['max_total_cents'],'offer_hash':v['offer_hash'],'confirmation':True})
    assert response.status_code==200,response.text
    assert response.json()['native_reauthorized']
    assert client.post('/api/purchase',json=p).status_code==200


def test_new_review_invalidates_earlier_decision(client):
    d,o=prepare(client);v=decision(client,d,o[0])
    r=client.post(f"/api/intents/{d['id']}/answers",json={'revision':d['revision'],'fields':d['fields'],'unsupported':[],'confirmation':True})
    assert r.status_code==200
    assert client.post('/api/purchase',json={'decision_id':v['id'],'idempotency_key':'stale-approval-1'}).status_code==409


def test_exception_for_one_offer_cannot_authorize_another(client):
    d,o=prepare(client);v=decision(client,d,o[1]);w=decision(client,d,o[1])
    assert client.post(f"/api/decisions/{v['id']}/exceptions",json={'check_ids':['nonstop'],'offer_hash':v['offer_hash'],'confirmation':True}).status_code==200
    assert client.post('/api/purchase',json={'decision_id':w['id'],'idempotency_key':'other-decision-1'}).status_code==409


def test_general_unknown_requirement_stays_held(client):
    d=client.post('/api/intents',json={'domain':'general','message':'Ethically sourced comfortable chair under $300','mode':'offline'}).json()
    d=client.post(f"/api/intents/{d['id']}/answers",json={'revision':1,'fields':{'max_total_cents':29999},'unsupported':d['unsupported'],'confirmation':True}).json()
    a=client.post(f"/api/intents/{d['id']}/approve",json={'revision':d['revision'],'digest':d['digest'],'confirmation':True}).json()
    v=decision(client,d,a['offers'][0]);assert v['status']=='HOLD'
    assert client.post(f"/api/decisions/{v['id']}/exceptions",json={'check_ids':['unsupported_0'],'offer_hash':v['offer_hash'],'confirmation':True}).status_code==409


def test_hotel_end_to_end_reuses_approval_and_gate(client):
    d=client.post('/api/intents',json={'domain':'hotel','message':'Hotel Orlando 2026-11-12 2026-11-14 under $300 with breakfast','mode':'offline'}).json()
    fields={k:None for k in client.get('/api/profiles/hotel').json()['fields']}
    fields.update(city='Orlando',checkin_date='2026-11-12',checkout_date='2026-11-14',max_total_cents=29999,breakfast=True)
    d=client.post(f"/api/intents/{d['id']}/answers",json={'revision':1,'fields':fields,'unsupported':[],'confirmation':True}).json()
    a=client.post(f"/api/intents/{d['id']}/approve",json={'revision':d['revision'],'digest':d['digest'],'confirmation':True}).json()
    assert decision(client,d,a['offers'][0])['status']=='PASS'
    assert decision(client,d,a['offers'][1])['status']=='HOLD'


def test_sqlite_mutation_preserves_concurrent_reservations(tmp_path):
    store=SQLiteStore(str(tmp_path/'concurrent.sqlite3'))
    def increment(_):
        def update(s): s['count']=s.get('count',0)+1
        store.mutate('budget',update)
    with ThreadPoolExecutor(max_workers=6) as pool: list(pool.map(increment,range(30)))
    assert store.read('budget')['count']==30
