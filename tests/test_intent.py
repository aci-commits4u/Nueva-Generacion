"""Catch unsupported-field laundering, invented source quotes, and silent fallback."""
import pytest
from app.foundry_client import validate_extraction,extract
from app.intent_service import offline_extract
from app.store import get_store


def data():
    return {'fields':{'nonstop':True,'max_total_cents':29999},'sources':{'nonstop':'nonstop','max_total_cents':'under $300'},'unsupported':[],'explanation':'Review the price and route.'}


def test_source_span_must_exist_in_original():
    d=data();d['sources']['nonstop']='invented quotation'
    with pytest.raises(ValueError): validate_extraction('flight','nonstop under $300',d)


def test_unknown_conditions_cannot_be_ignored():
    d=data();d['fields']['quiet']=True
    with pytest.raises(ValueError): validate_extraction('flight','nonstop under $300',d)


def test_ai_cannot_create_no_preference():
    d=data();d['fields']['nonstop']=None
    with pytest.raises(ValueError): validate_extraction('flight','nonstop under $300',d)


def test_valid_extraction_is_still_a_draft():
    assert validate_extraction('flight','nonstop under $300',data())['fields']['nonstop'] is True


def test_live_failure_does_not_turn_into_offline(monkeypatch,tmp_path):
    monkeypatch.setenv('SQLITE_PATH',str(tmp_path/'budget.sqlite3'));monkeypatch.setenv('STORE_BACKEND','sqlite');monkeypatch.setenv('MOCK_LLM','0')
    get_store.cache_clear()
    def broken(*a,**k): raise RuntimeError('Provider unavailable')
    monkeypatch.setattr('app.foundry_client.request_model',broken)
    with pytest.raises(ValueError,match='Live AI'): extract('flight','nonstop under $300','test-session')
    get_store.cache_clear()


def test_budget_exhaustion_stops_live_requests(monkeypatch,tmp_path):
    monkeypatch.setenv('SQLITE_PATH',str(tmp_path/'budget.sqlite3'));monkeypatch.setenv('STORE_BACKEND','sqlite');monkeypatch.setenv('AI_CALL_LIMIT','1');monkeypatch.setenv('MOCK_LLM','0')
    get_store.cache_clear()
    from app.store import reserve_ai_call
    reserve_ai_call('s1')
    with pytest.raises(ValueError,match='allowance'): reserve_ai_call('s2')
    get_store.cache_clear()


def test_offline_general_keeps_unknown_conditions():
    d=offline_extract('general','Find a comfortable ethically sourced chair under $300')
    assert d['mode']=='offline'
    assert d['unsupported']
