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


def test_declined_optional_question_is_not_repeated_but_still_needs_review(client,monkeypatch):
    def proposal(*args,**kwargs):
        return {'fields':{'origin_airports':['EWR'],'destination_airports':['TPA'],'departure_date':'2026-11-07','max_total_cents':29999,'max_connections':1},'sources':{},'unsupported':[],'clarifications':[{'field':'nonstop','source_quote':'one connection okay','reason':'preference'}],'explanation':'Review your choices.','mode':'live','model':'test'}
    monkeypatch.setattr('app.foundry_client.extract',proposal)
    d=client.post('/api/intents',json={'mode':'live','message':'Newark to Tampa November 7, 2026, under $300, one connection okay.'}).json()
    assert d['questions'][0]['field']=='nonstop'
    d=client.post(f"/api/intents/{d['id']}/clarify",json={'revision':d['revision'],'message':'No—one connection is okay; I do not require nonstop. Leave departure time, trip duration, and refundability as no preference.'}).json()
    fields={q['field'] for q in d['questions']}
    assert not fields.intersection({'nonstop','departure_window','max_duration_minutes','refundable'})
    assert 'nonstop' not in d['fields']  # Conversation routing is not signed consent.
    assert client.post(f"/api/intents/{d['id']}/approve",json={'revision':d['revision'],'digest':d['digest'],'confirmation':True}).status_code==409


def test_question_decline_cannot_hide_missing_required_details():
    from app.conversation import questions
    q=questions('flight',{},messages=[{'role':'user','content':'No preference on departure date, departure time, or nonstop.'}])
    assert 'departure_date' in {item['field'] for item in q}
    assert 'departure_window' not in {item['field'] for item in q}


def test_hotel_accessibility_declines_advance_without_guessing_positive_requirements():
    from app.conversation import questions,declined_preferences
    for reply in ['No accessibility requirement; a standard room is fine.','Accessible room: no preference.']:
        assert 'accessible' not in {q['field'] for q in questions('hotel',{},messages=[{'role':'user','content':reply}])}
    choices=declined_preferences('flight',[{'role':'user','content':'I do not require nonstop but I require refundable.'}])
    assert 'nonstop' in choices and 'refundable' not in choices


def test_one_way_and_cabin_case_match_signed_offer_after_explicit_review(client):
    d=client.post('/api/intents',json={'mode':'offline','message':'Nonstop flight EWR to MCO on 2026-11-12 under $300'}).json()
    fields={k:None for k in client.get('/api/profiles/flight').json()['fields']}
    fields.update(origin_airports=['EWR'],destination_airports=['MCO'],departure_date='2026-11-12',max_total_cents=29999,nonstop=True,trip_type='One-way',cabin='Economy')
    r=client.post(f"/api/intents/{d['id']}/answers",json={'revision':d['revision'],'fields':fields,'unsupported':[],'confirmation':True})
    assert r.status_code==200,r.text
    d=r.json();assert d['fields']['cabin']=='economy' and d['fields']['trip_type']=='one_way'
    offers=client.post(f"/api/intents/{d['id']}/approve",json={'revision':d['revision'],'digest':d['digest'],'confirmation':True}).json()['offers']
    v=decision(client,d,offers[0]);assert v['status']=='PASS',v
    assert offers[0]['facts']['trip_type']=='one_way'
    assert client.post('/api/purchase',json={'decision_id':v['id'],'idempotency_key':'one-way-cabin-case'}).status_code==200


def test_offline_explicit_one_way_preserves_other_conditions_and_negative_direction():
    from app.intent_service import offline_extract
    message='I only need the outbound from EWR to MCO on 2026-11-12 under $300'
    result=offline_extract('flight',message)
    assert result['fields']['trip_type']=='one_way' and not result['unsupported']
    assert offline_extract('flight',message+' with checked bag')['unsupported']
    negative=offline_extract('flight','I do not want a one-way flight from EWR to MCO on 2026-11-12 under $300')
    assert 'trip_type' not in negative['fields'] and negative['unsupported']


def test_profile_upgrade_rejects_old_work_before_ai_but_preserves_past_evidence(client,monkeypatch):
    d,offers=prepare(client);v=decision(client,d,offers[0])
    receipt=client.post('/api/purchase',json={'decision_id':v['id'],'idempotency_key':'before-profile-upgrade'}).json()
    def provider(*args,**kwargs):raise AssertionError('No paid interpretation for an obsolete profile')
    monkeypatch.setattr('app.foundry_client.extract',provider)
    monkeypatch.setattr('app.foundry_client.explain',provider)
    get_store().mutate(client.cookies['ij_session'],lambda s:s['drafts'][d['id']].update(profile_digest='previous-profile-digest',mode='live'))
    saved=client.get(f"/api/intents/{d['id']}").json()
    assert saved['profile_current'] is False and saved['latest_purchase']['id']==receipt['id']
    assert client.post(f"/api/intents/{d['id']}/clarify",json={'revision':d['revision'],'message':'Actually change the departure'}).status_code==409
    assert client.post(f"/api/intents/{d['id']}/answers",json={'revision':d['revision'],'fields':d['fields'],'unsupported':[],'confirmation':True}).status_code==409
    assert client.post(f"/api/intents/{d['id']}/approve",json={'revision':d['revision'],'digest':d['digest'],'confirmation':True}).status_code==409
    assert client.post(f"/api/decisions/{v['id']}/explain").status_code==409
    assert client.get(f"/api/purchases/{receipt['id']}/evidence").json()['purchase']['id']==receipt['id']


def test_hotel_adult_capacity_uses_signed_fact_and_missing_capacity_holds():
    from app.rules_engine import evaluate
    from app.profile_registry import get_profile
    profile=get_profile('hotel')
    for requested,expected in [(1,'PASS'),(2,'PASS'),(3,'HOLD')]:
        result=evaluate(profile,{'adults':requested},{'max_adults':2})
        assert result['status']==expected
    assert evaluate(profile,{'adults':2},{})['checks'][0]['status']=='missing'
    assert evaluate(profile,{'adults':2},{'max_adults':'2'})['checks'][0]['status']=='missing'


def test_conversation_reconciles_only_duplicate_cabin_condition(client,monkeypatch):
    calls=[]
    def extraction(*args,**kwargs):
        calls.append(True)
        fields={'max_total_cents':29999};sources={'max_total_cents':'under $300'}
        if len(calls)>1:fields['cabin']='economy';sources['cabin']='Economy is fine'
        return {'fields':fields,'sources':sources,'unsupported':['Economy is fine','checked bag'] if len(calls)==1 else [],'explanation':'Review the cabin and dates.','mode':'live','model':'test'}
    monkeypatch.setattr('app.foundry_client.extract',extraction)
    d=client.post('/api/intents',json={'mode':'live','message':'Economy is fine with a checked bag, under $300.'}).json()
    r=client.post(f"/api/intents/{d['id']}/clarify",json={'revision':d['revision'],'message':'Use November 7, 2026.'}).json()
    assert r['fields']['cabin']=='economy' and r['unsupported']==['checked bag']
    assert r['ai_runs'][0]['unsupported']==['Economy is fine','checked bag']
    assert not r.get('approved')
