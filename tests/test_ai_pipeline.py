"""Provider-independent regression tests for staged intent interpretation."""
import pytest

@pytest.fixture(autouse=True)
def live_mode(monkeypatch):
 monkeypatch.setenv("MOCK_LLM","0")


def proposed():
 return {'fields':{'nonstop':True,'max_total_cents':29999},'sources':{'nonstop':'nonstop','max_total_cents':'under $300'},'unsupported':[],'explanation':'Review the airport and date.'}


def test_audit_is_separate_and_cannot_silently_fallback(monkeypatch):
 from app.ai_pipeline import run_pipeline
 monkeypatch.setattr('app.ai_pipeline.reserve_ai_call',lambda *a,**k:1)
 calls=[]
 def call(stage,*a,**k):
  calls.append(stage)
  if stage=='coverage_audit':raise RuntimeError('Audit unavailable')
  return proposed(),{'stage':stage,'model':'test','duration_ms':1,'tokens':{},'response_id':'synthetic'}
 monkeypatch.setattr('app.ai_pipeline.call_json',call)
 with pytest.raises(ValueError,match='No fallback'):run_pipeline('flight','nonstop under $300','s',variant='audited')
 assert calls==['extract','coverage_audit']


def test_stage_trace_is_real_and_validated(monkeypatch):
 from app.ai_pipeline import run_pipeline
 monkeypatch.setattr('app.ai_pipeline.reserve_ai_call',lambda *a,**k:1)
 def call(stage,*a,**k):return proposed(),{'stage':stage,'model':'test','duration_ms':3,'tokens':{'prompt_tokens':10},'response_id':'synthetic'}
 monkeypatch.setattr('app.ai_pipeline.call_json',call)
 r=run_pipeline('flight','nonstop under $300','s',variant='audited')
 assert [t['stage'] for t in r['trace']]==['extract','coverage_audit']
 assert r['fields']['nonstop'] is True and 'approved' not in r


def test_audit_cannot_remove_unsupported_condition(monkeypatch):
 from app.ai_pipeline import run_pipeline
 monkeypatch.setattr('app.ai_pipeline.reserve_ai_call',lambda *a,**k:1)
 def call(stage,*a,**k):
  p=proposed()
  if stage=='extract':p['unsupported']=['checked bag']
  return p,{'stage':stage,'model':'test','duration_ms':1,'tokens':{}}
 monkeypatch.setattr('app.ai_pipeline.call_json',call)
 r=run_pipeline('flight','nonstop under $300 with checked bag','s',variant='audited')
 assert r['unsupported']==['checked bag']


def test_bad_source_quote_never_reaches_a_draft(monkeypatch):
 from app.ai_pipeline import run_pipeline
 monkeypatch.setattr('app.ai_pipeline.reserve_ai_call',lambda *a,**k:1)
 def call(stage,*a,**k):
  p=proposed();p['sources']['nonstop']='invented quotation'
  return p,{'stage':stage,'model':'test','duration_ms':1,'tokens':{}}
 monkeypatch.setattr('app.ai_pipeline.call_json',call)
 with pytest.raises(ValueError,match='No fallback'):run_pipeline('flight','nonstop under $300','s',variant='guided')


def test_assistant_question_cannot_be_used_as_customer_source(monkeypatch):
 from app.ai_pipeline import run_pipeline
 monkeypatch.setattr('app.ai_pipeline.reserve_ai_call',lambda *a,**k:1)
 def call(stage,*a,**k):
  p=proposed();p['sources']['nonstop']='zero connections';return p,{'stage':stage,'duration_ms':1,'tokens':{}}
 monkeypatch.setattr('app.ai_pipeline.call_json',call)
 with pytest.raises(ValueError,match='No fallback'):
  run_pipeline('flight','Customer: under $300\nQuestion: zero connections?\nCustomer: Yes','s',variant='guided',source_text='under $300\nYes')


def test_unset_pipeline_uses_selected_audited_default(monkeypatch):
 from app.ai_pipeline import run_pipeline
 monkeypatch.delenv('AI_PIPELINE_VERSION',raising=False)
 monkeypatch.setattr('app.ai_pipeline.reserve_ai_call',lambda *a,**k:1)
 monkeypatch.setattr('app.ai_pipeline.call_json',lambda stage,*a,**k:(proposed(),{'stage':stage,'duration_ms':1,'tokens':{}}))
 r=run_pipeline('flight','nonstop under $300','s')
 assert r['pipeline']=='audited' and len(r['trace'])==2
