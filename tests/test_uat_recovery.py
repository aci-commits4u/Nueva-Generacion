"""Regressions from independent browser use, separate from live UAT."""
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from tests.test_enforcement import client,prepare,decision
from app.store import get_store


def test_offline_single_airport_reply_advances_next_question(client):
    d=client.post('/api/intents',json={'mode':'offline','message':'Get me to Florida under $300'}).json()
    assert d['questions'][0]['field']=='origin_airports'
    d=client.post(f"/api/intents/{d['id']}/clarify",json={'revision':d['revision'],'message':'Depart from EWR.'}).json()
    assert d['fields']['origin_airports']==['EWR']
    assert d['questions'][0]['field']=='destination_airports'
    d=client.post(f"/api/intents/{d['id']}/clarify",json={'revision':d['revision'],'message':'Arrive at MCO.'}).json()
    assert d['fields']['destination_airports']==['MCO']
    assert d['questions'][0]['field']=='departure_date'
    assert d['unsupported']  # Broad original text is never silently discarded.


def test_offline_hotel_city_is_independent_of_dates():
    from app.intent_service import offline_extract
    assert offline_extract('hotel','Find a hotel in Tampa under $300')['fields']['city']=='Tampa'


def test_pending_clarification_blocks_old_review_approval_and_purchase(client,monkeypatch):
    from tests.test_conversation import fake
    d,offers=prepare(client);v=decision(client,d,offers[0])
    entered,release=Event(),Event()
    def delayed(*args,**kwargs):
        entered.set();assert release.wait(5)
        return fake(*args,**kwargs)
    monkeypatch.setattr('app.foundry_client.extract',delayed)
    sid=client.cookies['ij_session']
    get_store().mutate(sid,lambda s:s['drafts'][d['id']].update(mode='live'))
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending=pool.submit(client.post,f"/api/intents/{d['id']}/clarify",json={'revision':d['revision'],'message':'Actually depart from JFK'})
        assert entered.wait(5)
        review=client.post(f"/api/intents/{d['id']}/answers",json={'revision':d['revision'],'fields':d['fields'],'unsupported':[],'confirmation':True})
        approve=client.post(f"/api/intents/{d['id']}/approve",json={'revision':d['revision'],'digest':d['digest'],'confirmation':True})
        purchase=client.post('/api/purchase',json={'decision_id':v['id'],'idempotency_key':'pending-change-purchase'})
        release.set();assert pending.result().status_code==200
    assert review.status_code==approve.status_code==purchase.status_code==409
    saved=client.get(f"/api/intents/{d['id']}").json()
    assert saved['messages'][-1]['content']=='Actually depart from JFK'


def test_abandoned_ai_lease_does_not_permanently_block_review(client):
    d,offers=prepare(client)
    get_store().mutate(client.cookies['ij_session'],lambda s:s.update(_ai_pending={'kind':'interpretation','intent_id':d['id'],'started_at':time.time()-80}))
    r=client.post(f"/api/intents/{d['id']}/answers",json={'revision':d['revision'],'fields':d['fields'],'unsupported':[],'confirmation':True})
    assert r.status_code==200,r.text


def test_concurrent_explanations_call_provider_once_then_use_cache(client,monkeypatch):
    d,offers=prepare(client);v=decision(client,d,offers[0])
    entered,release=Event(),Event();calls=[]
    def delayed(*args,**kwargs):
        calls.append(True);entered.set();assert release.wait(5)
        return {'text':'All approved requirements match the merchant-signed offer.','mode':'live'}
    monkeypatch.setattr('app.foundry_client.explain',delayed)
    path=f"/api/decisions/{v['id']}/explain"
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(client.post,path)
        assert entered.wait(5)
        duplicate=client.post(path)
        release.set();assert first.result().status_code==200
    assert duplicate.status_code==409 and len(calls)==1
    assert client.post(path).status_code==200 and len(calls)==1


def test_offline_explanation_names_each_uncheckable_condition():
    from app.foundry_client import explain
    from app.rules_engine import evaluate
    from app.profile_registry import get_profile
    result=evaluate(get_profile('flight'),{}, {},['round trip','land before dinner'])
    text=explain(result,'unused','offline')['text']
    assert 'round trip' in text and 'land before dinner' in text
