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
