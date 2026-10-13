"""Verify the full session decision allowance through the deployed HTTP API, without AI."""
import sys
import httpx

base=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8017'
with httpx.Client(base_url=base,timeout=60) as c:
    def request(method,path,body=None):
        r=c.request(method,path,json=body)
        r.raise_for_status()
        return r.json()
    request('GET','/api/session')
    d=request('POST','/api/intents',{'domain':'flight','message':'Nonstop flight EWR to MCO on 2026-11-12 under $300','mode':'offline'})
    fields={k:None for k in request('GET','/api/profiles/flight')['fields']}
    fields.update(d['fields'])
    d=request('POST',f"/api/intents/{d['id']}/answers",{'revision':d['revision'],'fields':fields,'unsupported':d['unsupported'],'confirmation':True})
    approved=request('POST',f"/api/intents/{d['id']}/approve",{'revision':d['revision'],'digest':d['digest'],'confirmation':True})
    for _ in range(25):
        v=request('POST','/api/check',{'intent_id':d['id'],'offer_id':approved['offers'][0]['id']})
        assert v['status']=='PASS'
    p={'decision_id':v['id'],'idempotency_key':'capacity-http-regression'}
    receipt=request('POST','/api/purchase',p)
    assert request('POST','/api/purchase',p)['id']==receipt['id']
    evidence=request('GET',f"/api/purchases/{receipt['id']}/evidence")
    assert evidence['final_decision']=='dispute analyst' and evidence['signed_evidence']
    recovered=request('GET',f"/api/intents/{d['id']}")
    assert len(recovered['saved_decisions'])==25 and recovered['latest_purchase']['id']==receipt['id']
    print('PASS: 25 checks, durable receipt, idempotent retry, signed evidence, and session recovery; no AI calls.')
