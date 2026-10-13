"""Conversation revisions must never weaken approval or enforcement."""
from tests.test_enforcement import client,prepare,decision


def fake(domain,message,session):
 return {'fields':{'nonstop':True,'max_total_cents':29999},'sources':{'nonstop':'Nonstop','max_total_cents':'under $300'},'unsupported':[],'explanation':'Choose your airports.','mode':'live','model':'test','pipeline':'audited','trace':[{'stage':'extract','duration_ms':1}]}


def test_conversation_records_sources_and_rejects_stale_revision(client,monkeypatch):
 monkeypatch.setattr('app.foundry_client.extract',fake)
 d=client.post('/api/intents',json={'message':'Nonstop under $300','mode':'live'}).json()
 assert d['messages'][0]['content']=='Nonstop under $300'
 r=client.post(f"/api/intents/{d['id']}/clarify",json={'revision':1,'message':'From EWR to MCO on 2026-11-12'})
 assert r.status_code==200,r.text
 assert r.json()['revision']==2 and len(r.json()['messages'])==2
 assert r.json()['ai_runs'][1]['revision']==2
 assert client.post(f"/api/intents/{d['id']}/clarify",json={'revision':1,'message':'Another date please'}).status_code==409


def test_clarification_preserves_unsupported_conditions(client,monkeypatch):
 monkeypatch.setattr('app.foundry_client.extract',fake)
 d=client.post('/api/intents',json={'message':'Nonstop under $300','mode':'live'}).json()
 from app.store import get_store
 sid=client.cookies['ij_session']
 get_store().mutate(sid,lambda s:s['drafts'][d['id']].update(unsupported=['checked bag']))
 r=client.post(f"/api/intents/{d['id']}/clarify",json={'revision':1,'message':'From EWR'})
 assert r.status_code==200 and r.json()['unsupported']==['checked bag']


def test_changed_conversation_invalidates_prior_purchase(client,monkeypatch):
 d,offers=prepare(client);v=decision(client,d,offers[0])
 monkeypatch.setattr('app.foundry_client.extract',fake)
 r=client.post(f"/api/intents/{d['id']}/clarify",json={'revision':d['revision'],'message':'Actually use JFK please'})
 assert r.status_code==200,r.text
 assert not r.json().get('approved')
 assert client.post('/api/purchase',json={'decision_id':v['id'],'idempotency_key':'old-conversation-offer'}).status_code==409


def test_cross_session_cannot_clarify(client,monkeypatch):
 monkeypatch.setattr('app.foundry_client.extract',fake)
 d=client.post('/api/intents',json={'message':'Nonstop under $300','mode':'live'}).json()
 client.cookies.clear();client.get('/api/session')
 assert client.post(f"/api/intents/{d['id']}/clarify",json={'revision':1,'message':'Use EWR please'}).status_code==404


def test_concurrent_edit_during_inference_does_not_overwrite_current_draft(client,monkeypatch):
 monkeypatch.setattr('app.foundry_client.extract',fake)
 d=client.post('/api/intents',json={'message':'Nonstop under $300','mode':'live'}).json()
 from app.store import get_store
 sid=client.cookies['ij_session']
 def racing(*a):
  get_store().mutate(sid,lambda s:s['drafts'][d['id']].update(revision=2))
  return fake(*a)
 monkeypatch.setattr('app.foundry_client.extract',racing)
 r=client.post(f"/api/intents/{d['id']}/clarify",json={'revision':1,'message':'From EWR please'})
 assert r.status_code==409
 saved=client.get(f"/api/intents/{d['id']}").json()
 assert saved['revision']==2 and len(saved['messages'])==1


def test_evidence_contains_customer_conversation_and_actual_stage_record(client):
 d,offers=prepare(client);v=decision(client,d,offers[0])
 receipt=client.post('/api/purchase',json={'decision_id':v['id'],'idempotency_key':'conversation-evidence'}).json()
 evidence=client.get(f"/api/purchases/{receipt['id']}/evidence").json()
 assert evidence['conversation'][0]['content']==d['message']
 assert evidence['interpretation_runs'][0]['mode']=='offline'
 assert evidence['final_decision']=='dispute analyst'
