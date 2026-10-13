"""Deterministic gold labels score interpretation, not the model's self-assessment."""
import json

def same_value(a,b):
    if isinstance(a,list) and isinstance(b,list) and all(isinstance(x,str) for x in a+b):
        a,b=sorted(a),sorted(b)
    return json.dumps(a,sort_keys=True)==json.dumps(b,sort_keys=True)

def score_case(case,result):
    fields=result.get('fields',{});sources=result.get('sources',{})
    valid=isinstance(fields,dict) and isinstance(sources,dict) and not result.get('error')
    if not valid:fields={};sources={}
    expected=case['expected_fields']
    correct=[k for k,v in expected.items() if k in fields and same_value(fields[k],v)]
    invented=sorted(set(fields)-set(expected)-set(case.get('allowed_extra',[])))
    bad_sources=[k for k in fields if not isinstance(sources.get(k),str) or not sources[k] or sources[k].casefold() not in case['message'].casefold()]
    unsupported=' '.join(result.get('unsupported',[])).casefold()
    missing=[group for group in case.get('unsupported_groups',[]) if not any(s.casefold() in unsupported for s in group)]
    unnecessary_hold=bool(unsupported) and not case.get('unsupported_groups') and not case.get('allow_unsupported',False)
    return {'case_id':case['id'],'passed':valid and len(correct)==len(expected) and not invented and not bad_sources and not missing and not unnecessary_hold,'field_accuracy':len(correct)/max(len(expected),1),'correct_fields':correct,'wrong_or_missing_fields':sorted(set(expected)-set(correct)),'invented_fields':invented,'ungrounded_fields':bad_sources,'missed_unsupported_groups':missing,'unnecessary_hold':unnecessary_hold,'error':result.get('error')}
