"""Catch dropped approved fields, coercion, missing facts and wrong boundaries."""
import pytest
from app.rules_engine import evaluate
from app.profile_registry import get_profile


def rule(fields, facts, domain='flight'):
    return evaluate(get_profile(domain), fields, facts)


def test_nonstop_mismatch_holds():
    d = rule({'nonstop': True, 'max_total_cents': 30000}, {'nonstop': False, 'total_cents':28000, 'currency':'USD'})
    assert d['status'] == 'HOLD'
    assert [c['check_id'] for c in d['checks'] if c['status']=='fail'] == ['nonstop']


def test_missing_required_fact_holds():
    d = rule({'nonstop':True}, {})
    assert d['status']=='HOLD'
    assert d['checks'][0]['status']=='missing'


@pytest.mark.parametrize('price,want', [(29999,'PASS'),(30000,'PASS'),(30001,'HOLD')])
def test_price_boundary(price,want):
    assert rule({'max_total_cents':30000},{'total_cents':price,'currency':'USD'})['status']==want


def test_currency_is_explicit():
    assert rule({'max_total_cents':30000},{'total_cents':100})['status']=='HOLD'
    assert rule({'max_total_cents':30000},{'total_cents':100,'currency':'EUR'})['status']=='HOLD'


def test_bool_is_not_an_integer():
    assert rule({'max_connections':0},{'connection_count':False})['status']=='HOLD'


def test_unrecognized_requirement_is_not_dropped():
    assert rule({'quiet_aircraft':True},{})['status']=='HOLD'


def test_explicit_no_preference_does_not_require_fact():
    assert rule({'nonstop':None},{})['status']=='PASS'


def test_hotel_configuration_reuses_engine():
    assert rule({'breakfast':True},{'breakfast':False},'hotel')['status']=='HOLD'
    assert rule({'breakfast':True},{'breakfast':True},'hotel')['status']=='PASS'


def test_window_handles_overnight():
    assert rule({'departure_window':['22:00','05:00']},{'departure_local':'23:30'})['status']=='PASS'
    assert rule({'departure_window':['22:00','05:00']},{'departure_local':'12:00'})['status']=='HOLD'
