"""Provider-independent regression tests for staged intent interpretation."""
from types import SimpleNamespace

import pytest

@pytest.fixture(autouse=True)
def live_mode(monkeypatch):
 monkeypatch.setenv("MOCK_LLM","0")


def proposed():
 return {'fields':{'nonstop':True,'max_total_cents':29999},'sources':{'nonstop':'nonstop','max_total_cents':'under $300'},'unsupported':[],'explanation':'Review the airport and date.'}


def proposed5():
 p=proposed();p['clarifications']=[];return p


def test_audit_is_separate_and_cannot_silently_fallback(monkeypatch):
 from app.ai_pipeline import run_pipeline
 monkeypatch.setattr('app.ai_pipeline.reserve_ai_calls',lambda *a,**k:1)
 calls=[]
 def call(stage,*a,**k):
  calls.append(stage)
  if stage=='coverage_audit':raise RuntimeError('Audit unavailable')
  return proposed(),{'stage':stage,'model':'test','duration_ms':1,'tokens':{},'response_id':'synthetic'}
 monkeypatch.setattr('app.ai_pipeline.call_json',call)
 with pytest.raises(ValueError,match='provider is unavailable'):run_pipeline('flight','nonstop under $300','s',variant='audited')
 assert calls==['extract','coverage_audit']


def test_stage_trace_is_real_and_validated(monkeypatch):
 from app.ai_pipeline import run_pipeline
 monkeypatch.setattr('app.ai_pipeline.reserve_ai_calls',lambda *a,**k:1)
 def call(stage,*a,**k):return proposed(),{'stage':stage,'model':'test','duration_ms':3,'tokens':{'prompt_tokens':10},'response_id':'synthetic'}
 monkeypatch.setattr('app.ai_pipeline.call_json',call)
 r=run_pipeline('flight','nonstop under $300','s',variant='audited')
 assert [t['stage'] for t in r['trace']]==['extract','coverage_audit']
 assert r['fields']['nonstop'] is True and 'approved' not in r


def test_audited_mixed_quality_draft_retains_real_global_requirements(monkeypatch):
 """Reproduce the native CPH/ICN failure without another paid provider call."""
 from copy import deepcopy
 from app.ai_pipeline import run_pipeline
 message=('Please find a one-way nonstop economy flight for one adult from Copenhagen '
  'Airport in Denmark (CPH) to Seoul Incheon International Airport in South Korea (ICN). '
  'I can depart on any date from May 5 through May 9, 2027, with May 7 preferred. '
  'Keep the all-in fare under $1,200 USD, and show departures between 8 a.m. and 8 p.m.')
 draft={
  'fields':{'max_total_cents':120000,'origin_airports':['CPH'],
   'destination_airports':['ICN'],'departure_date':{'start':'2027-05-05','end':'2027-05-09'},
   'nonstop':True,'departure_window':['08:00','20:00'],'cabin':'economy','trip_type':'one-way'},
  'sources':{'max_total_cents':'under $1,200 USD',
   'origin_airports':'Copenhagen Airport in Denmark (CPH)',
   'destination_airports':'Seoul Incheon International Airport in South Korea (ICN)',
   'departure_date':'any date from May 5 through May 9, 2027','nonstop':'nonstop',
   'departure_window':'between 8 a.m. and 8 p.m.','cabin':'economy','trip_type':'one-way'},
  'unsupported':[],'clarifications':[],
  'explanation':'All criteria were captured with no unsupported conditions.',
 }
 reservations=[]
 calls=[]
 monkeypatch.setattr('app.ai_pipeline.reserve_ai_calls',
  lambda session,stages,**kw:reservations.append(stages))
 def call(stage,*args,**kwargs):
  calls.append(stage)
  return deepcopy(draft),{'stage':stage,'model':'test','duration_ms':1,'tokens':{}}
 monkeypatch.setattr('app.ai_pipeline.call_json',call)
 r=run_pipeline('flight',message,'session',variant='audited')
 assert reservations==[2] and calls==['extract','coverage_audit']
 assert r['mode']=='live' and r['fields']['max_total_cents']==119999
 assert r['fields']['origin_airports']==['CPH'] and r['fields']['destination_airports']==['ICN']
 assert r['fields']['departure_date']=={'start':'2027-05-05','end':'2027-05-09'}
 assert r['fields']['departure_window']==['08:00','20:00']
 assert 'for one adult' in r['unsupported'] and 'May 7 preferred' in r['unsupported']
 assert r['trace'][1]['partial_recovery']['rejected_fields']==[
  {'field':'max_total_cents','issue':'grounding_failed','source_grounded':True}]
 assert 'approved' not in r and 'decision' not in r and 'recovery' not in r


@pytest.mark.parametrize('malformed', [False, True])
def test_audit_recovery_cannot_accept_all_unquoted_or_malformed_fields(monkeypatch,malformed):
 from app.ai_pipeline import run_pipeline
 monkeypatch.setattr('app.ai_pipeline.reserve_ai_calls',lambda *a,**k:2)
 draft={'fields':{'origin_airports':['CPH']},'sources':{'origin_airports':'invented city'},
  'unsupported':[],'clarifications':[],'explanation':'Review.'}
 if malformed: draft['extra']='unreviewed metadata'
 monkeypatch.setattr('app.ai_pipeline.call_json',
  lambda stage,*a,**k:(draft,{'stage':stage,'tokens':{}}))
 with pytest.raises(ValueError):run_pipeline('flight','I want a flight','s',variant='audited')


def test_audit_cannot_remove_unsupported_condition(monkeypatch):
 from app.ai_pipeline import run_pipeline
 monkeypatch.setattr('app.ai_pipeline.reserve_ai_calls',lambda *a,**k:1)
 def call(stage,*a,**k):
  p=proposed()
  if stage=='extract':p['unsupported']=['checked bag']
  return p,{'stage':stage,'model':'test','duration_ms':1,'tokens':{}}
 monkeypatch.setattr('app.ai_pipeline.call_json',call)
 r=run_pipeline('flight','nonstop under $300 with checked bag','s',variant='audited')
 assert r['unsupported']==['checked bag']


def test_bad_source_quote_never_reaches_a_draft(monkeypatch):
 from app.ai_pipeline import run_pipeline
 monkeypatch.setattr('app.ai_pipeline.reserve_ai_calls',lambda *a,**k:1)
 def call(stage,*a,**k):
  p=proposed();p['sources']['nonstop']='invented quotation'
  return p,{'stage':stage,'model':'test','duration_ms':1,'tokens':{}}
 monkeypatch.setattr('app.ai_pipeline.call_json',call)
 with pytest.raises(ValueError,match='grounded'):run_pipeline('flight','nonstop under $300','s',variant='guided')


def test_assistant_question_cannot_be_used_as_customer_source(monkeypatch):
 from app.ai_pipeline import run_pipeline
 monkeypatch.setattr('app.ai_pipeline.reserve_ai_calls',lambda *a,**k:1)
 def call(stage,*a,**k):
  p=proposed();p['sources']['nonstop']='zero connections';return p,{'stage':stage,'duration_ms':1,'tokens':{}}
 monkeypatch.setattr('app.ai_pipeline.call_json',call)
 with pytest.raises(ValueError,match='grounded'):
  run_pipeline('flight','Customer: under $300\nQuestion: zero connections?\nCustomer: Yes','s',variant='guided',source_text='under $300\nYes')


def test_unset_pipeline_uses_selected_audited_default(monkeypatch):
 from app.ai_pipeline import run_pipeline
 monkeypatch.delenv('AI_PIPELINE_VERSION',raising=False)
 monkeypatch.setattr('app.ai_pipeline.reserve_ai_calls',lambda *a,**k:1)
 monkeypatch.setattr('app.ai_pipeline.call_json',lambda stage,*a,**k:(proposed(),{'stage':stage,'duration_ms':1,'tokens':{}}))
 r=run_pipeline('flight','nonstop under $300','s')
 assert r['pipeline']=='audited' and len(r['trace'])==2


def test_audit_repairs_invalid_candidate_and_retains_bounded_flag(monkeypatch):
 from app.ai_pipeline import run_pipeline
 monkeypatch.setattr('app.ai_pipeline.reserve_ai_calls',lambda *a,**k:2)
 calls=[]
 def call(stage,*a,**k):
  calls.append(stage)
  p=proposed()
  if stage=='extract':
   p['sources']['nonstop']='flight'
   p['unsupported']=['round trip']
  return p,{'stage':stage,'model':'test','duration_ms':1,'tokens':{}}
 monkeypatch.setattr('app.ai_pipeline.call_json',call)
 r=run_pipeline('flight','nonstop under $300 round trip','s',variant='audited')
 assert calls==['extract','coverage_audit']
 assert r['fields']['nonstop'] is True
 assert r['unsupported']==['round trip']


def test_audit_cannot_drop_a_valid_candidate_field(monkeypatch):
 from app.ai_pipeline import run_pipeline
 monkeypatch.setattr('app.ai_pipeline.reserve_ai_calls',lambda *a,**k:2)
 def call(stage,*a,**k):
  p=proposed()
  if stage=='coverage_audit':
   p['fields'].pop('nonstop')
   p['sources'].pop('nonstop')
  return p,{'stage':stage,'model':'test','duration_ms':1,'tokens':{}}
 monkeypatch.setattr('app.ai_pipeline.call_json',call)
 r=run_pipeline('flight','nonstop under $300','s',variant='audited')
 assert r['fields']['nonstop'] is True


def test_audit_retains_unresolved_broad_location_requirement(monkeypatch):
 from app.ai_pipeline import run_pipeline
 monkeypatch.setattr('app.ai_pipeline.reserve_ai_calls',lambda *a,**k:2)
 def call(stage,*a,**k):
  p=proposed()
  if stage=='extract':
   p['fields']['destination_airports']=['Florida']
   p['sources']['destination_airports']='Florida'
  else:
   p['fields'].pop('nonstop')
   p['sources'].pop('nonstop')
  return p,{'stage':stage,'model':'test','duration_ms':1,'tokens':{}}
 monkeypatch.setattr('app.ai_pipeline.call_json',call)
 r=run_pipeline('flight','Florida under $300','s',variant='audited')
 assert 'destination airport needs clarification: Florida' not in r['unsupported']
 assert 'Please specify a destination airport for Florida.' in r['explanation']


def test_audit_drops_only_typed_missing_field_marker(monkeypatch):
 from app.ai_pipeline import run_pipeline
 monkeypatch.setattr('app.ai_pipeline.reserve_ai_calls',lambda *a,**k:2)
 def call(stage,*a,**k):
  p=proposed()
  p['fields'].pop('nonstop')
  p['sources'].pop('nonstop')
  if stage=='extract':p['unsupported']=['destination unspecified (Florida)','round trip']
  return p,{'stage':stage,'duration_ms':1,'tokens':{}}
 monkeypatch.setattr('app.ai_pipeline.call_json',call)
 r=run_pipeline('flight','Florida under $300 round trip','s',variant='audited')
 assert r['unsupported']==['round trip']


def test_audit_retains_structured_clarification_until_customer_resolves_it(monkeypatch):
 from app.ai_pipeline import run_pipeline
 monkeypatch.setattr('app.ai_pipeline.reserve_ai_calls',lambda *a,**k:2)
 def call(stage,*a,**k):
  p=proposed5()
  p['fields'].pop('nonstop');p['sources'].pop('nonstop')
  if stage=='extract':
   p['clarifications']=[{'field':'destination_airports','source_quote':'Florida','reason':'ambiguous'}]
  return p,{'stage':stage,'duration_ms':1,'tokens':{}}
 monkeypatch.setattr('app.ai_pipeline.call_json',call)
 r=run_pipeline('flight','Florida under $300','s',variant='audited')
 assert r['unsupported']==[]
 assert r['clarifications']==[{'field':'destination_airports','source_quote':'Florida','reason':'ambiguous'}]


def test_audit_retains_grounded_unknown_clarification_as_unsupported(monkeypatch):
 from app.ai_pipeline import run_pipeline
 monkeypatch.setattr('app.ai_pipeline.reserve_ai_calls',lambda *a,**k:2)
 def call(stage,*a,**k):
  p=proposed5()
  if stage=='extract':
   p['clarifications']=[{'field':'arrival_window','source_quote':'arrive before dinner','reason':'preference'}]
  return p,{'stage':stage,'duration_ms':1,'tokens':{}}
 monkeypatch.setattr('app.ai_pipeline.call_json',call)
 r=run_pipeline('flight','nonstop under $300; arrive before dinner','s',variant='audited')
 assert r['fields']['nonstop'] is True
 assert r['clarifications']==[]
 assert r['unsupported']==['arrive before dinner']


def test_pipeline_reconciles_merged_one_way_marker_after_audit(monkeypatch):
 from app.ai_pipeline import run_pipeline
 monkeypatch.setattr('app.ai_pipeline.reserve_ai_calls',lambda *a,**k:2)
 def call(stage,*a,**k):
  return {
   'fields':{'trip_type':'one_way','max_total_cents':29999},
   'sources':{'trip_type':'only need the outbound','max_total_cents':'under $300'},
   'unsupported':['one way'] if stage=='extract' else [],
   'clarifications':[],
   'explanation':'Review the trip type and price.',
  },{'stage':stage,'duration_ms':1,'tokens':{}}
 monkeypatch.setattr('app.ai_pipeline.call_json',call)
 r=run_pipeline('flight','I only need the outbound this time under $300','s',variant='audited')
 assert r['fields']['trip_type']=='one_way'
 assert r['unsupported']==[]


@pytest.mark.parametrize('extract_legacy,audit_legacy', [(True, False), (False, True)])
def test_pipeline_reconciles_duplicate_cabin_marker_across_envelope_versions(
  monkeypatch, extract_legacy, audit_legacy,
):
 from app.ai_pipeline import run_pipeline
 monkeypatch.setattr('app.ai_pipeline.reserve_ai_calls',lambda *a,**k:2)
 def call(stage,*a,**k):
  legacy = extract_legacy if stage=='extract' else audit_legacy
  result={
   'fields':{'cabin':'Economy','max_total_cents':29999},
   'sources':{'cabin':'Economy is fine','max_total_cents':'under $300'},
   'unsupported':(
    ['Economy is fine','economy with checked bag','premium economy',"I don't want economy"]
    if stage=='extract' else []
   ),
   'explanation':'Review the cabin and price.',
  }
  if not legacy:
   result['clarifications']=[]
  return result,{'stage':stage,'duration_ms':1,'tokens':{}}
 monkeypatch.setattr('app.ai_pipeline.call_json',call)
 r=run_pipeline('flight','Economy is fine under $300','s',variant='audited')
 assert r['fields']['cabin']=='economy'
 assert r['unsupported']==['economy with checked bag','premium economy',"I don't want economy"]


def test_audit_reconciles_typed_location_marker_with_structured_clarification(monkeypatch):
 from app.ai_pipeline import run_pipeline
 monkeypatch.setattr('app.ai_pipeline.reserve_ai_calls',lambda *a,**k:2)
 def call(stage,*a,**k):
  p=proposed5()
  p['fields'].pop('nonstop');p['sources'].pop('nonstop')
  p['unsupported']=['destination unspecified (Florida)', 'round trip']
  p['clarifications']=[{'field':'destination_airports','source_quote':'Florida','reason':'ambiguous'}]
  return p,{'stage':stage,'duration_ms':1,'tokens':{}}
 monkeypatch.setattr('app.ai_pipeline.call_json',call)
 r=run_pipeline('flight','Florida under $300 round trip','s',variant='audited')
 assert r['clarifications']==[{'field':'destination_airports','source_quote':'Florida','reason':'ambiguous'}]
 assert r['unsupported']==['round trip']


def test_audit_recovers_yearless_date_without_losing_grounded_fields(monkeypatch):
 from app.ai_pipeline import run_pipeline
 monkeypatch.setattr('app.ai_pipeline.reserve_ai_calls',lambda *a,**k:2)
 def call(stage,*a,**k):
  p=proposed5()
  p['fields']={
   'origin_airports':['EWR'], 'destination_airports':['TPA'],
   'departure_date':'2026-11-07', 'max_total_cents':29999,
   'max_connections':1,
  }
  p['sources']={
   'origin_airports':'Newark', 'destination_airports':'Tampa',
   'departure_date':'Nov 7–10', 'max_total_cents':'under $300',
   'max_connections':'one connection',
  }
  p['unsupported']=['round trip']
  return p,{'stage':stage,'duration_ms':1,'tokens':{}}
 monkeypatch.setattr('app.ai_pipeline.call_json',call)
 r=run_pipeline(
  'flight',
  'I am visiting Tampa from Newark Nov 7–10 under $300 round trip with one connection',
  's',variant='audited',
 )
 assert r['fields']['origin_airports']==['EWR']
 assert r['fields']['destination_airports']==['TPA']
 assert r['fields']['max_connections']==1
 assert 'departure_date' not in r['fields']
 assert r['clarifications']==[{'field':'departure_date','source_quote':'Nov 7–10','reason':'ambiguous'}]
 assert r['unsupported']==['round trip']
 assert r['trace'][0]['grounding_recoveries']==[{'field':'departure_date','reason':'year_missing'}]


def test_invalid_candidate_quarantine_keeps_structured_clarification(monkeypatch):
 from app.ai_pipeline import run_pipeline
 monkeypatch.setattr('app.ai_pipeline.reserve_ai_calls',lambda *a,**k:2)
 captured={}
 def call(stage,*a,**k):
  p=proposed5()
  if stage=='extract':
   p['fields']['nonstop']=True
   p['sources']['nonstop']='invented'
   p['clarifications']=[{'field':'destination_airports','source_quote':'Florida','reason':'ambiguous'}]
  else:
   captured['candidate']=k['candidate']
   p['fields'].pop('nonstop')
   p['sources'].pop('nonstop')
  return p,{'stage':stage,'duration_ms':1,'tokens':{}}
 monkeypatch.setattr('app.ai_pipeline.call_json',call)
 r=run_pipeline('flight','Florida under $300','s',variant='audited')
 assert captured['candidate']['clarifications']==[{'field':'destination_airports','source_quote':'Florida','reason':'ambiguous'}]
 assert r['clarifications']==[{'field':'destination_airports','source_quote':'Florida','reason':'ambiguous'}]


def test_audit_repairs_malformed_candidate_clarification(monkeypatch):
 from app.ai_pipeline import run_pipeline
 monkeypatch.setattr('app.ai_pipeline.reserve_ai_calls',lambda *a,**k:2)
 def call(stage,*a,**k):
  p=proposed5()
  if stage=='extract':p['clarifications']=['bad']
  return p,{'stage':stage,'duration_ms':1,'tokens':{}}
 monkeypatch.setattr('app.ai_pipeline.call_json',call)
 r=run_pipeline('flight','nonstop under $300','s',variant='audited')
 assert r['fields']['nonstop'] is True
 assert r['clarifications']==[]


def test_malformed_final_clarification_is_typed_interpretation_error(monkeypatch):
 from app.ai_errors import AIServiceError
 from app.ai_pipeline import run_pipeline
 monkeypatch.setattr('app.ai_pipeline.reserve_ai_calls',lambda *a,**k:2)
 def call(stage,*a,**k):
  p=proposed5()
  if stage=='coverage_audit':p['clarifications']=['bad']
  return p,{'stage':stage,'duration_ms':1,'tokens':{}}
 monkeypatch.setattr('app.ai_pipeline.call_json',call)
 with pytest.raises(AIServiceError) as exc:
  run_pipeline('flight','nonstop under $300','s',variant='audited')
 assert exc.value.code=='ai_interpretation'
 assert exc.value.status_code==502
 assert exc.value.stage=='coverage_audit'


def test_audited_run_reserves_both_stages_atomically(monkeypatch):
 from app.ai_pipeline import run_pipeline
 reservations=[]
 def reserve(*args,**kwargs):
  reservations.append((args,kwargs))
  return 2
 monkeypatch.setattr('app.ai_pipeline.reserve_ai_calls',reserve)
 monkeypatch.setattr('app.ai_pipeline.call_json',lambda stage,*a,**k:(proposed(),{'stage':stage,'duration_ms':1,'tokens':{}}))
 result=run_pipeline('flight','nonstop under $300','session-1',variant='audited')
 assert reservations==[(('session-1',2),{'purpose':'interactive'})]
 assert 'reservation' not in result


def test_provider_configuration_failure_is_typed_without_provider_call(monkeypatch):
 from app.ai_errors import AIServiceError
 from app.ai_pipeline import call_json
 for key in ('AZURE_OPENAI_ENDPOINT','AZURE_OPENAI_API_KEY','AZURE_OPENAI_DEPLOYMENT'):
  monkeypatch.delenv(key,raising=False)
 with pytest.raises(AIServiceError) as exc:
  call_json('extract','flight','under $300','guided')
 assert exc.value.code=='ai_configuration' and exc.value.status_code==503
 assert exc.value.public()['request_id']==exc.value.request_id


def test_invalid_provider_json_is_interpretation_error(monkeypatch):
 from app.ai_errors import AIServiceError
 from app.ai_pipeline import call_json
 monkeypatch.setenv('AZURE_OPENAI_ENDPOINT','https://synthetic.example')
 monkeypatch.setenv('AZURE_OPENAI_API_KEY','synthetic-key')
 monkeypatch.setenv('AZURE_OPENAI_DEPLOYMENT','synthetic-model')
 response=SimpleNamespace(
  usage=None,
  choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content='not json'))],
  id='synthetic-response',
 )
 fake=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs:response)))
 monkeypatch.setattr('app.ai_pipeline.OpenAI',lambda **kwargs:fake)
 with pytest.raises(AIServiceError) as exc:
  call_json('extract','flight','under $300','guided')
 assert exc.value.code=='ai_interpretation' and exc.value.status_code==502


def test_invalid_reasoning_effort_is_typed_configuration_before_reservation(monkeypatch):
 from app.ai_errors import AIServiceError
 from app.ai_pipeline import run_pipeline
 monkeypatch.setenv('AI_REASONING_EFFORT','sideways')
 monkeypatch.setattr('app.ai_pipeline.reserve_ai_calls',lambda *a,**k: pytest.fail('invalid config must preflight before reservation'))
 with pytest.raises(AIServiceError) as exc:
  run_pipeline('flight','under $300','session',variant='guided')
 assert exc.value.code=='ai_configuration' and exc.value.stage=='preflight'


def test_trace_records_prompt_version_reasoning_effort_and_output_format(monkeypatch):
 from app.ai_pipeline import call_json
 monkeypatch.setenv('AZURE_OPENAI_ENDPOINT','https://synthetic.example')
 monkeypatch.setenv('AZURE_OPENAI_API_KEY','synthetic-key')
 monkeypatch.setenv('AZURE_OPENAI_DEPLOYMENT','synthetic-model')
 response=SimpleNamespace(
  usage=None,
  choices=[SimpleNamespace(
   finish_reason='stop',
   message=SimpleNamespace(content='{"fields":{},"sources":{},"unsupported":[],"clarifications":[],"explanation":"Review."}'),
  )],
  id='synthetic-response',
 )
 fake=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs:response)))
 monkeypatch.setattr('app.ai_pipeline.OpenAI',lambda **kwargs:fake)
 _,trace=call_json('extract','flight','under $300','guided')
 assert trace['prompt_version']
 assert trace['reasoning_effort']=='low'
 assert trace['output_format']=='plain-json'
