"""Catch ignored native policy, merchant tampering, and custom-constraint omission."""
from copy import deepcopy
from app.vi_adapter import issue, verify, sign_offer
from app.profile_registry import get_profile, digest


def approval():
    p=get_profile('flight')
    return {'id':'a','revision':1,'domain':'flight','profile_digest':p['digest'],'fields':{'nonstop':True,'max_total_cents':30000},'unsupported':[],'actor':'test-session'}


def offer():
    return {'id':'o','domain':'flight','total_cents':28000,'currency':'USD','route_complete':True,'technical_stops':0,'segments':[{'origin':'EWR','destination':'MCO','departure':'2026-11-12T09:00:00-05:00','arrival':'2026-11-12T12:00:00-05:00'}]}


def test_real_sdk_chain_and_merchant_signature():
    a=approval(); b=issue(a,sign_offer(offer()))
    v=verify(b,a)
    assert v['valid'] is True
    assert v['facts']['nonstop'] is True
    assert v['native_ok'] is True
    assert v['requirements']==a


def test_native_price_fails_even_when_chain_is_valid():
    a=approval(); o=offer(); o['total_cents']=31000
    v=verify(issue(a,sign_offer(o)),a)
    assert v['valid'] is True
    assert v['native_ok'] is False


def test_tampered_checkout_cannot_pass():
    a=approval(); b=issue(a,sign_offer(offer()))
    b['checkout_jwt']=b['checkout_jwt'][:-10]+'AAAAAAAAAA'
    assert verify(b,a)['valid'] is False


def test_signed_unsupported_constraint_holds():
    a=approval()
    v=verify(issue(a,sign_offer(offer()),extra_constraints=[{'type':'urn:unknown:policy'}]),a)
    assert v['valid'] is True
    assert v['native_ok'] is False
    assert any(x['status']=='missing' for x in v['ledger'])


def test_approval_not_same_as_signed_custom_constraint_blocks():
    a=approval(); b=issue(a,sign_offer(offer())); a['fields']['nonstop']=False
    assert verify(b,a)['valid'] is False


def test_nonstop_needs_disclosed_technical_stops():
    a=approval(); o=offer(); del o['technical_stops']
    assert 'nonstop' not in verify(issue(a,sign_offer(o)),a)['facts']


def test_discontinuous_signed_route_blocks():
    a=approval(); o=offer(); o['segments'].append({'origin':'JFK','destination':'MIA','departure':'2026-11-12T13:00:00-05:00','arrival':'2026-11-12T15:00:00-05:00'})
    assert verify(issue(a,sign_offer(o)),a)['valid'] is False


def test_extra_checkout_reference_cannot_receive_unchecked_pass():
    a=approval()
    v=verify(issue(a,sign_offer(offer()),extra_constraints=[{'type':'mandate.payment.reference','conditional_transaction_id':'wrong-reference'}]),a)
    assert v['native_ok'] is False
    assert any(x['type']=='mandate.payment.reference' and x['status']!='pass' for x in v['ledger'])


def test_fractional_duration_is_never_rounded_down():
    a=approval();o=offer();o['segments'][0]['arrival']='2026-11-12T11:00:59-05:00'
    v=verify(issue(a,sign_offer(o)),a)
    assert v['facts']['duration_minutes']==121
