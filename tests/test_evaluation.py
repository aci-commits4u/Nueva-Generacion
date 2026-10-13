"""Independent labels catch fluent but wrong intent interpretation."""
import pytest
from app.store import get_store,reserve_ai_call


def sample():
    return {'id':'sample','domain':'flight','message':'Nonstop under $300 with two passengers','expected_fields':{'nonstop':True,'max_total_cents':29999},'unsupported_groups':[['passengers','passenger count']]}


def result():
    return {'fields':{'nonstop':True,'max_total_cents':29999},'sources':{'nonstop':'Nonstop','max_total_cents':'under $300'},'unsupported':['two passengers'],'explanation':'Review your requirements.'}


def test_gold_scorer_rejects_missing_unsupported_condition():
    from evals.scoring import score_case
    r=result();r['unsupported']=[]
    assert not score_case(sample(),r)['passed']


def test_gold_scorer_rejects_invented_and_wrong_values():
    from evals.scoring import score_case
    r=result();r['fields']['nonstop']=False;r['fields']['cabin']='business';r['sources']['cabin']='Nonstop'
    scored=score_case(sample(),r)
    assert not scored['passed'] and 'cabin' in scored['invented_fields']


def test_gold_scorer_rejects_fabricated_source_quote():
    from evals.scoring import score_case
    r=result();r['sources']['nonstop']='zero stops'
    assert not score_case(sample(),r)['passed']


def test_gold_scorer_accepts_complete_grounded_interpretation():
    from evals.scoring import score_case
    assert score_case(sample(),result())['passed']


def test_evaluations_preserve_public_daily_quota(monkeypatch,tmp_path):
    monkeypatch.setenv('STORE_BACKEND','sqlite');monkeypatch.setenv('SQLITE_PATH',str(tmp_path/'budget.sqlite3'))
    monkeypatch.setenv('AI_DAILY_LIMIT','1');monkeypatch.setenv('AI_EVAL_DAILY_LIMIT','2');monkeypatch.setenv('AI_CALL_LIMIT','3')
    get_store.cache_clear()
    reserve_ai_call('e1',purpose='evaluation');reserve_ai_call('e2',purpose='evaluation')
    reserve_ai_call('u1')
    s=get_store().read('global-ai-budget')
    assert s['calls']==3 and s['daily_calls']==1 and s['daily_eval_calls']==2
    with pytest.raises(ValueError,match='spending allowance'):reserve_ai_call('e3',purpose='evaluation')
    get_store.cache_clear()


def test_monitor_has_independent_lifetime_limit(monkeypatch,tmp_path):
    monkeypatch.setenv('STORE_BACKEND','sqlite');monkeypatch.setenv('SQLITE_PATH',str(tmp_path/'budget.sqlite3'));monkeypatch.setenv('AI_MONITOR_CALL_LIMIT','1')
    get_store.cache_clear()
    reserve_ai_call('m1',purpose='monitor')
    with pytest.raises(ValueError,match='monitor'):reserve_ai_call('m2',purpose='monitor')
    get_store.cache_clear()
