"""Real API/state/VI gates with a fixture model; these are not live UAT."""
from copy import deepcopy
import pytest

from tests.test_fast_api import client
from app.ai_config import LEDGER_PROMPT_VERSION
from app.intent_ledger import empty_ledger, reduce_ledger, compile_ledger
from app.structured_intent import build_source_catalog
from app.profile_registry import get_profile, digest
from app.ai_errors import AIServiceError


def _proposal(domain,messages,ops,current=None):
    catalog=build_source_catalog(source_messages=messages)
    base=deepcopy((current or {}).get('intent_ledger') or empty_ledger())
    raw={'expected_revision':base['revision'],'operations':ops,'action':'ready_for_review',
         'question':None,'assistant_message':'I recorded these requirements.','explanation':'Compare the recorded intent with your request.'}
    ledger=reduce_ledger(domain,base,raw,catalog,expected_revision=base['revision'])
    projected=compile_ledger(domain,ledger,catalog)
    return {**projected,'intent_ledger':ledger,'pipeline':'ledger','mode':'live','model':'synthetic-fixture',
            'explanation':raw['explanation'],'adaptive_plan':{'action':raw['action'],'question':None,'assistant_message':raw['assistant_message']},
            'trace':[{'stage':'ledger_plan','prompt_version':LEDGER_PROMPT_VERSION,'raw_proposal':raw}],
            'ledger_transition':{'before_revision':base['revision'],'after_revision':ledger['revision'],'operation_count':len(ops)}}


def _op(field,value,ref,*,op='add',target=None,strength='required',status='active',key=None,text=None):
    return {'op':op,'target_id':target,'key':key or field,'field':field,'value':value,
            'strength':strength,'status':status,'text':text or field,
            'source_refs':[ref],'unit':'total' if field=='max_total_cents' and value is not None else None}


def _install_flight(monkeypatch):
    calls=[]
    def fake(domain,message,session,**kwargs):
        messages=kwargs['source_messages'];catalog=build_source_catalog(source_messages=messages)
        current=kwargs.get('current_draft');calls.append(kwargs)
        if not current:
            ref=catalog[0]['id']
            ops=[_op(k,v,ref) for k,v in {'origin_airports':['LAX','BUR'],'destination_airports':['SFO','OAK'],
                                        'departure_date':'2026-11-20','max_total_cents':60000,'max_connections':0}.items()]
        else:
            old=next(r for r in current['intent_ledger']['records'] if r['field']=='max_total_cents' and r['status']=='active')
            ref=next(r['id'] for r in catalog if r['id'].startswith('t2p0'))
            ops=[_op('max_total_cents',70000,ref,op='replace',target=old['id'])]
        return _proposal(domain,messages,ops,current)
    monkeypatch.setattr('app.foundry_client.extract',fake)
    return calls


def test_api_ledger_correction_review_purchase_and_evidence_bindings(client,monkeypatch):
    calls=_install_flight(monkeypatch)
    start=client.post('/api/intents',json={'domain':'flight','mode':'live',
          'message':'LAX or BUR to SFO or OAK November 20, 2026, up to $600. No layovers.'})
    assert start.status_code==200,start.text
    d=start.json();path=f"/api/intents/{d['id']}"
    assert d['pipeline']=='ledger' and d['intent_ledger']['revision']==1
    changed=client.post(path+'/clarify',json={'revision':1,'message':'Actually up to $700, keep everything else.'})
    assert changed.status_code==200,changed.text
    d=changed.json()
    assert calls[-1]['pipeline']=='ledger'
    assert d['fields']['max_total_cents']==70000
    assert d['fields']['max_connections']==0
    assert d['fields']['origin_airports']==['LAX','BUR']
    assert d['fields']['destination_airports']==['SFO','OAK']
    assert d['fields']['departure_date']=='2026-11-20'
    assert len(d['intent_ledger']['history'])==6
    assert d['questions']==[]
    fields={k:d['fields'].get(k) for k in get_profile('flight')['fields']}
    reviewed=client.post(path+'/answers',json={'revision':2,'fields':fields,'unsupported':[],'confirmation':True})
    assert reviewed.status_code==200,reviewed.text
    d=reviewed.json()
    assert d['intent_ledger']['revision']==d['revision']==3
    assert d['intent_ledger']['history'][-1]['actor']=='customer_review'
    approved=client.post(path+'/approve',json={'revision':d['revision'],'digest':d['digest'],'confirmation':True})
    assert approved.status_code==200,approved.text
    auth=approved.json()
    assert auth['approved']['intent_ledger_digest']==digest(d['intent_ledger'])
    assert auth['approved']['intent_ledger_revision']==3
    decisions=[client.post('/api/check',json={'intent_id':d['id'],'offer_id':o['id']}).json() for o in auth['offers']]
    assert decisions[0]['status']=='PASS'
    assert decisions[1]['status']=='HOLD'
    assert client.post('/api/purchase',json={'decision_id':decisions[1]['id'],'idempotency_key':'ledger-conflicting-offer'}).status_code==409
    bought=client.post('/api/purchase',json={'decision_id':decisions[0]['id'],'idempotency_key':'ledger-matching-offer'})
    assert bought.status_code==200,bought.text
    receipt=bought.json()
    packet=client.get(f"/api/purchases/{receipt['id']}/evidence").json()
    assert packet['intent_ledger']==d['intent_ledger']
    assert packet['approved_requirements']['intent_ledger_digest']==digest(packet['intent_ledger'])
    assert packet['purchase']['offer_hash']==receipt['offer_hash']
    assert client.get(path).json()['latest_purchase']['id']==receipt['id']


def test_ledger_failed_and_stale_edits_preserve_state_and_approval(client,monkeypatch):
    _install_flight(monkeypatch)
    d=client.post('/api/intents',json={'domain':'flight','mode':'live','message':'LAX or BUR to SFO or OAK November 20, 2026, up to $600. No layovers.'}).json()
    path=f"/api/intents/{d['id']}"
    before=client.get(path).json()
    def fail(*a,**kw):raise AIServiceError('ai_timeout','Live AI timed out; no changes were applied.',stage='ledger_plan')
    monkeypatch.setattr('app.foundry_client.extract',fail)
    assert client.post(path+'/clarify',json={'revision':0,'message':'Make it $700.'}).status_code==409
    assert client.post(path+'/clarify',json={'revision':1,'message':'Make it $700.'}).status_code>=500
    after=client.get(path).json()
    assert after['revision']==before['revision']
    assert after['intent_ledger']==before['intent_ledger']
    assert after['fields']==before['fields']


def test_refresh_keeps_ledger_pipeline_when_deployment_default_changes(client,monkeypatch):
    from app.store import get_store
    calls=_install_flight(monkeypatch)
    d=client.post('/api/intents',json={'domain':'flight','mode':'live',
        'message':'LAX or BUR to SFO or OAK November 20, 2026, up to $600. No layovers.'}).json()
    path=f"/api/intents/{d['id']}"
    def stale(state):
        state['drafts'][d['id']]['profile_digest']='previous-profile'
    get_store().mutate(client.cookies['ij_session'],stale)
    monkeypatch.setenv('AI_PIPELINE_VERSION','adaptive_fast')
    def unchanged(domain,message,session,**kwargs):
        calls.append(kwargs)
        return _proposal(domain,kwargs['source_messages'],[],kwargs['current_draft'])
    monkeypatch.setattr('app.foundry_client.extract',unchanged)
    result=client.post(path+'/refresh-profile',json={'revision':1,'time_zone':'UTC'})
    assert result.status_code==200,result.text
    refreshed=result.json()
    assert calls[-1]['pipeline']=='ledger'
    assert refreshed['pipeline']=='ledger'
    assert refreshed['fields']==d['fields']
    assert refreshed['intent_ledger']['revision']==refreshed['revision']==2
    assert refreshed['ai_runs'][-1]['pipeline']=='ledger'


def test_generic_required_review_keeps_hold_and_soft_unknown_not_required(client,monkeypatch):
    def fake(domain,message,session,**kw):
        messages=kw['source_messages'];ref=build_source_catalog(source_messages=messages)[0]['id']
        return _proposal(domain,messages,[
            _op('max_total_cents',30000,ref),
            _op(None,None,ref,key='repairable',text='Repairable frame',status='needs_clarification'),
            _op(None,None,ref,key='quiet',text='Quiet would be nice',strength='preferred'),
        ])
    monkeypatch.setattr('app.foundry_client.extract',fake)
    result=client.post('/api/intents',json={'domain':'general','mode':'live',
                                         'message':'A chair up to $300, a repairable frame required; quiet would be nice.'})
    assert result.status_code==200,result.text
    d=result.json();path=f"/api/intents/{d['id']}"
    assert d['unsupported']==['Repairable frame']
    reviewed=client.post(path+'/answers',json={'revision':1,'fields':{'max_total_cents':30000},
                                              'unsupported':['Repairable frame'],'confirmation':True})
    assert reviewed.status_code==200,reviewed.text
    d=reviewed.json()
    assert any(r['key']=='quiet' and r['status']=='active' for r in d['intent_ledger']['records'])
    assert d['clarifications']==compile_ledger('general',d['intent_ledger'])['clarifications']
    approved=client.post(path+'/approve',json={'revision':d['revision'],'digest':d['digest'],'confirmation':True})
    assert approved.status_code==200,approved.text
    for o in approved.json()['offers']:
        decision=client.post('/api/check',json={'intent_id':d['id'],'offer_id':o['id']}).json()
        assert decision['status']=='HOLD'
        assert client.post('/api/purchase',json={'decision_id':decision['id'],'idempotency_key':'ledger-unsupported-condition'}).status_code==409


def test_typed_airport_multiselect_survives_a_model_omission(client,monkeypatch):
    import app.ledger_pipeline as pipeline
    from app.conversation import canonical_airport_answer
    calls=[]
    monkeypatch.setenv('AI_PIPELINE_VERSION','ledger')
    def model(stage,**kw):
        p=kw['payload'];calls.append(stage)
        ref=p['customer_source_catalog'][0]['id']
        if p['ledger_revision']==0:
            ops=[_op(k,v,ref) for k,v in {'destination_airports':['DEN'],
                 'departure_date':'2026-11-20','max_total_cents':50000,'max_connections':0}.items()]
            q={'criterion_key':'origin_airports','field':'origin_airports','text':'Which departure airports work for you?',
               'why':'I need the acceptable departure set to preserve your route choice.',
               'answer_kind':'multi','answer_semantics':None,'options':[]}
        else:
            ops=[];q=None  # The model must not erase/ignore the actual widget choice.
        raw={'expected_revision':p['ledger_revision'],'operations':ops,'action':'ask_user' if q else 'ready_for_review',
             'question':q,'assistant_message':'Which departure airports work for you?' if q else 'Recorded your choice.',
             'explanation':'Review these requirements.'}
        return {'proposal':raw,'trace':{'model':'synthetic-fixture'}}
    monkeypatch.setattr(pipeline,'call_model',model)
    response=client.post('/api/intents',json={'domain':'flight','mode':'live',
          'message':'Fly to DEN November 20, 2026, up to $500, no layovers. I can depart from the DC area.'})
    assert response.status_code==200,response.text
    d=response.json();q=d['questions'][0];path=f"/api/intents/{d['id']}"
    msg=canonical_airport_answer('origin_airports',['DCA','IAD'])
    answer={'question_id':q['question_id'],'field':'origin_airports','values':['DCA','IAD']}
    wrong=client.post(path+'/clarify',json={'revision':1,'message':msg,'structured_answer':{**answer,'question_id':'stale'}})
    assert wrong.status_code==422,wrong.text
    before=len(calls)
    selected=client.post(path+'/clarify',json={'revision':1,'message':msg,'structured_answer':answer})
    assert selected.status_code==200,selected.text
    saved=selected.json()
    assert len(calls)>before
    assert saved['fields']['origin_airports']==['DCA','IAD']
    assert saved['fields']['max_connections']==0
    assert saved['questions']==[]
    origin=next(r for r in saved['intent_ledger']['records'] if r['field']=='origin_airports' and r['status']=='active')
    assert origin['provenance']=='customer_widget'
    assert origin['source_quotes']==[msg]
