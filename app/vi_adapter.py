"""Pinned VI SDK adapter plus independent merchant verification.

The draft stock checker rejects unknown custom types in an open mandate.
After cryptographic verification we explicitly dispatch every constraint.
The original signed L2 is never rewritten or passed as if natively supported.
"""
import base64
import json
import os
import time
import math
from datetime import datetime
from functools import lru_cache
from verifiable_intent import (IssuerCredential, UserMandate, CheckoutMandate, PaymentMandate, MandateMode, PaymentAmountConstraint, CheckoutLineItemsConstraint, CheckoutL3Mandate, PaymentL3Mandate, FinalCheckoutMandate, FinalPaymentMandate, create_layer1, create_layer2_autonomous, create_layer3_checkout, create_layer3_payment, verify_chain)
from verifiable_intent.models.constraints import Constraint
from verifiable_intent.crypto.signing import generate_es256_key, public_key_to_jwk, jwk_to_private_key, _jwt_encode, _jwt_decode_parts, es256_verify
from verifiable_intent.crypto.sd_jwt import decode_sd_jwt
from verifiable_intent.crypto.disclosure import hash_bytes, hash_disclosure, build_selective_presentation
from verifiable_intent.verification.constraint_checker import check_constraints, StrictnessMode
from app.profile_registry import get_profile, digest

ISSUER='https://issuer.intent-judge.example'
WALLET='https://wallet.intent-judge.example'
AGENT='https://agent.intent-judge.example'
NETWORK='https://network.intent-judge.example'
MERCHANT='https://merchant.intent-judge.example'
MERCHANT_ID={'id':'synthetic-merchant','name':'Demo Travel','website':MERCHANT}
INSTRUMENT={'type':'synthetic.demo','id':'demo-instrument','description':'Synthetic instrument — no card'}

@lru_cache
def keys():
    raw=os.getenv('DEMO_SIGNING_KEYS')
    if raw:
        data=json.loads(raw)
        return {k:jwk_to_private_key(data[k]) for k in ('issuer','user','agent','merchant')}
    if os.getenv('VERCEL'):
        raise RuntimeError('Hosted signing keys must be configured')
    return {k:generate_es256_key() for k in ('issuer','user','agent','merchant')}


def sign_record(payload, role='user', typ='intent-judge-record+jwt'):
    return _jwt_encode({'alg':'ES256','typ':typ,'kid':f'demo-{role}-v1'},payload,keys()[role])


def read_signed(token,role,typ):
    h,p,sig=_jwt_decode_parts(token)
    if h.get('alg')!='ES256' or h.get('typ')!=typ or h.get('kid')!=f'demo-{role}-v1':
        raise ValueError('Invalid signing algorithm or trusted key identifier')
    if not es256_verify(token.rsplit('.',1)[0].encode('ascii'),sig,keys()[role].public_key()):
        raise ValueError('Signature did not verify')
    return p


def sign_offer(offer):
    now=int(time.time())
    p={**offer,'iss':MERCHANT,'aud':AGENT,'iat':now,'exp':now+3600,'merchant_id':MERCHANT_ID['id'],'all_in':True,'line_items':offer.get('line_items',[{'id':'demo-travel','quantity':1}])}
    return sign_record(p,'merchant','intent-judge-checkout+jwt')


def offer_hash(jwt):
    return hash_bytes(jwt.encode('ascii'))


def issue(approved,checkout_jwt,extra_constraints=(),native_max=None):
    k=keys(); now=int(time.time()); p=get_profile(approved['domain'])
    l1=create_layer1(IssuerCredential(iss=ISSUER,sub=approved['actor'],iat=now,exp=now+3600,aud=WALLET,cnf_jwk=public_key_to_jwk(k['user']),scheme='Synthetic demo',card_id=INSTRUMENT['id']),k['issuer'])
    custom=Constraint(type=p['custom_constraint_type'],extra_fields={'approved_requirements':approved,'profile_digest':p['digest']})
    cm=CheckoutMandate(cnf_jwk=public_key_to_jwk(k['agent']),cnf_kid='demo-agent-v1',constraints=[custom,CheckoutLineItemsConstraint(items=[{"id":"travel","acceptable_items":[{"id":"demo-travel","title":"Synthetic travel offer"}],"quantity":1}],match_mode="exact")]+[Constraint(type=c['type'],extra_fields={a:b for a,b in c.items() if a!='type'}) for c in extra_constraints])
    cap=approved['fields'].get('max_total_cents') if native_max is None else native_max
    pm=PaymentMandate(cnf_jwk=public_key_to_jwk(k['agent']),cnf_kid='demo-agent-v1',payment_instrument=INSTRUMENT,constraints=[PaymentAmountConstraint(currency='USD',min=0,max=cap)])
    nonce=digest({'approved':approved,'checkout_hash':offer_hash(checkout_jwt)})
    l2=create_layer2_autonomous(UserMandate(nonce=nonce,aud=AGENT,iat=now,iss=WALLET,exp=now+3600,mode=MandateMode.AUTONOMOUS,sd_hash=hash_bytes(l1.serialize().encode('ascii')),checkout_mandate=cm,payment_mandate=pm,merchants=[MERCHANT_ID],acceptable_items=[{"id":"demo-travel","title":"Synthetic travel offer"}]),k['user'])
    base=l2.serialize().split('~')[0]
    def disc(vct):
        return next(s for s,v in zip(l2.disclosures,l2.disclosure_values) if isinstance(v[-1],dict) and v[-1].get('vct')==vct)
    cd,pd=disc('mandate.checkout.open.1'),disc('mandate.payment.open.1')
    md=next(s for s,v in zip(l2.disclosures,l2.disclosure_values) if isinstance(v[-1],dict) and v[-1].get('id')==MERCHANT_ID['id'])
    it=next(s for s,v in zip(l2.disclosures,l2.disclosure_values) if isinstance(v[-1],dict) and v[-1].get('id')=='demo-travel')
    # Issuance is a demo shopping adapter, not verification: it may select a bad offer.
    _,o,_=_jwt_decode_parts(checkout_jwt); ch=offer_hash(checkout_jwt)
    fp=FinalPaymentMandate(transaction_id=ch,payee=MERCHANT_ID,payment_amount={'currency':o.get('currency'),'amount':o.get('total_cents')},payment_instrument=INSTRUMENT)
    l3p=create_layer3_payment(PaymentL3Mandate(nonce=nonce+'-p',aud=NETWORK,iat=now,iss=AGENT,exp=now+3600,final_payment=fp,final_merchant=MERCHANT_ID),k['agent'],base,pd,md,kid='demo-agent-v1')
    l3c=create_layer3_checkout(CheckoutL3Mandate(nonce=nonce+'-c',aud=MERCHANT,iat=now,iss=AGENT,exp=now+3600,final_checkout=FinalCheckoutMandate(checkout_jwt=checkout_jwt,checkout_hash=ch)),k['agent'],base,cd,it,kid='demo-agent-v1')
    return {'l1':l1.serialize(),'l2':l2.serialize(),'l3_payment':l3p.serialize(),'l3_checkout':l3c.serialize(),'l2_payment':build_selective_presentation(base,[pd,md]),'l2_checkout':build_selective_presentation(base,[cd,it]),'checkout_jwt':checkout_jwt,'nonce':nonce}


def normalize_offer(o):
    facts={k:v for k,v in o.items() if k not in {'segments','description'}}
    if o.get('all_in') is not True:
        facts.pop('total_cents',None)
    if type(o.get('total_cents')) is not int or o['total_cents']<0:
        raise ValueError('Invalid all-in amount')
    if o.get('domain')!='flight':
        return facts
    segments=o.get('segments')
    if not isinstance(segments,list) or not segments or o.get('route_complete') is not True:
        return {k:v for k,v in facts.items() if k not in {'nonstop','connection_count','origin','destination','departure_date','departure_local','duration_minutes'}}
    prev=None; first=None; last=None
    for s in segments:
        dep,arr=datetime.fromisoformat(s['departure']),datetime.fromisoformat(s['arrival'])
        if dep.utcoffset() is None or arr.utcoffset() is None or arr<=dep or (prev and (prev['destination']!=s['origin'] or dep<last)):
            raise ValueError('Invalid complete itinerary')
        if first is None: first=dep
        prev=s; last=arr
    facts.update(origin=segments[0]['origin'],destination=segments[-1]['destination'],departure_date=first.date().isoformat(),departure_local=first.strftime('%H:%M'),duration_minutes=math.ceil((last-first).total_seconds()/60),connection_count=len(segments)-1)
    facts.pop('nonstop',None)
    stops=o.get('technical_stops')
    if type(stops) is int and stops>=0:
        facts['nonstop']=len(segments)==1 and stops==0
    return facts


def verify(bundle,approved):
    ledger=[]
    try:
        result=verify_chain(decode_sd_jwt(bundle['l1']),decode_sd_jwt(bundle['l2']),l3_payment=decode_sd_jwt(bundle['l3_payment']),l3_checkout=decode_sd_jwt(bundle['l3_checkout']),issuer_public_key=keys()['issuer'].public_key(),clock_skew_seconds=0,l1_serialized=bundle['l1'],l2_serialized=bundle['l2'],l2_payment_serialized=bundle['l2_payment'],l2_checkout_serialized=bundle['l2_checkout'],expected_l2_aud=AGENT,expected_l2_nonce=bundle['nonce'],expected_l3_payment_aud=NETWORK,expected_l3_payment_nonce=bundle['nonce']+'-p',expected_l3_checkout_aud=MERCHANT,expected_l3_checkout_nonce=bundle['nonce']+'-c')
        if not result.valid:
            raise ValueError('VI chain did not verify: '+ '; '.join(result.errors))
        o=read_signed(bundle['checkout_jwt'],'merchant','intent-judge-checkout+jwt')
        now=int(time.time())
        if o.get('iss')!=MERCHANT or o.get('aud')!=AGENT or o.get('merchant_id')!=MERCHANT_ID['id'] or type(o.get('exp')) is not int or o['exp']<=now or type(o.get('iat')) is not int or o['iat']>now:
            raise ValueError('Untrusted or expired merchant offer')
        p=get_profile(approved['domain'])
        if approved['profile_digest']!=p['digest'] or o.get('domain')!=approved['domain']:
            raise ValueError('Profile/domain changed')
        payment=result.l3_payment_claims['delegate_payload']
        checkout=result.l3_checkout_claims['delegate_payload']
        # Draft SDK exposes delegate payload as a dict in L3.
        if isinstance(payment,list): payment=next(x for x in payment if 'payment_amount' in x)
        if isinstance(checkout,list): checkout=checkout[0]
        amount=payment.get('payment_amount',{})
        if amount!={'currency':o.get('currency'),'amount':o.get('total_cents')} or payment.get('payee',{}).get('id')!=MERCHANT_ID['id'] or payment.get('transaction_id')!=offer_hash(bundle['checkout_jwt']) or checkout.get('checkout_jwt')!=bundle['checkout_jwt'] or checkout.get('checkout_hash')!=offer_hash(bundle['checkout_jwt']):
            raise ValueError('Payment and merchant checkout binding differ')
        custom_count=0
        for pair in result.pair_results:
            for role,mandate in (('checkout',pair.checkout_mandate),('payment',pair.payment_mandate)):
                for i,c in enumerate(mandate.get('constraints',[])):
                    typ=c.get('type')
                    if typ==p['custom_constraint_type']:
                        custom_count+=1
                        if c.get('approved_requirements')!=approved or c.get('profile_digest')!=p['digest']:
                            raise ValueError('Signed requirements differ from traveler approval')
                        status='pass'; message='Custom constraint routed to the deterministic profile engine.'
                    elif typ=='mandate.checkout.line_items':
                        resolved=json.loads(json.dumps(c))
                        l2=decode_sd_jwt(bundle['l2'])
                        disclosed={hash_disclosure(s):v[-1] for s,v in zip(l2.disclosures,l2.disclosure_values)}
                        for item in resolved['items']:
                            item['acceptable_items']=[disclosed[x['...']] if '...' in x else x for x in item['acceptable_items']]
                        checked=check_constraints([resolved],{'line_items':o.get('line_items',[])},mode=StrictnessMode.STRICT,is_open_mandate=True)
                        status='pass' if checked.satisfied else 'fail';message='Native product and quantity policy evaluated against signed checkout.'
                    elif typ=='mandate.payment.reference':
                        count=sum(x.get('type')==typ for x in mandate.get('constraints',[]))
                        ok=role=='payment' and count==1 and bool(pair.pairing_key) and c.get('conditional_transaction_id')==pair.pairing_key
                        status='pass' if ok else 'missing'
                        message='Payment reference matches the exact signed checkout disclosure.' if ok else 'Unsupported or mismatched reference instance; checkout is held.'
                    elif typ=='mandate.payment.amount_range':
                        checked=check_constraints([c],payment,mode=StrictnessMode.STRICT,is_open_mandate=True)
                        status='pass' if checked.satisfied and o.get('currency')=='USD' else 'fail'
                        message='Native VI payment amount constraint evaluated separately from chain signatures.'
                    else:
                        status='missing';message='This constraint has no implemented evaluator; checkout is held.'
                    ledger.append({'type':typ,'status':status,'message':message})
        if custom_count!=1: raise ValueError('Exactly one domain constraint is required')
        return {'valid':True,'native_ok':all(x['status']=='pass' for x in ledger),'requirements':approved,'facts':normalize_offer(o),'offer':o,'offer_hash':offer_hash(bundle['checkout_jwt']),'ledger':ledger,'chain_checks':result.checks_performed}
    except (ValueError,KeyError,TypeError,IndexError,StopIteration) as exc:
        return {'valid':False,'native_ok':False,'facts':{},'ledger':ledger,'error':str(exc)}


def public_keys():
    return {role:public_key_to_jwk(key) for role,key in keys().items()}
