"""Only this module assigns purchase decisions. No network or language model."""
from app.profile_registry import valid_time


def evaluate(profile, fields, facts, unsupported=(), gates=()):
    checks=[]
    for key,required in fields.items():
        if required is None:
            continue  # Explicitly reviewed no preference, never an untouched field.
        spec=profile['fields'].get(key)
        value=facts.get(spec['fact']) if spec else None
        status='missing'
        reason='The signed offer does not provide the information needed.'
        if not spec:
            reason='This requirement does not have a supported deterministic check.'
        elif value is not None:
            op,t=spec['op'],spec['type']
            valid = (t=='integer' and type(value) is int and value>=0 and type(required) is int) or (t=='boolean' and type(value) is bool and type(required) is bool) or (t=='string' and type(value) is str and type(required) is str) or (t=='strings' and type(value) is str and type(required) is list and all(type(x) is str for x in required)) or (t=='window' and valid_time(value) and type(required) is list and len(required)==2 and all(valid_time(x) for x in required))
            if valid:
                if op=='lte': ok=value<=required
                elif op=='gte': ok=value>=required
                elif op=='eq': ok=value==required
                elif op=='in': ok=value in required
                elif op=='window':
                    start,end=required
                    ok=(start<=value<=end) if start<=end else (value>=start or value<=end)
                else: ok=False
                status='pass' if ok else 'fail'
                reason='Matches your approved requirement.' if ok else 'This offer differs from your approved requirement.'
            else:
                reason='The signed offer has an invalid or unsupported value type.'
        if key=='max_total_cents' and facts.get('currency')!='USD':
            status='missing' if facts.get('currency') is None else 'fail'
            reason='The approved price is in USD; an explicit matching currency is required.'
        checks.append({'check_id':key,'label':spec['label'] if spec else key,'requirement':required,'offer_value':value,'status':status,'message':reason,'exception_allowed':bool(spec and spec.get('exception_allowed',True))})
    for i,text in enumerate(unsupported):
        checks.append({'check_id':f'unsupported_{i}','label':'Unsupported condition','requirement':text,'offer_value':None,'status':'missing','message':'A reviewed profile and trustworthy offer facts are needed for this condition.','exception_allowed':False})
    checks.extend(gates)
    status='BLOCK' if any(c['status']!='pass' and c.get('integrity') for c in checks) else 'HOLD' if any(c['status']!='pass' for c in checks) else 'PASS'
    return {'status':status,'checks':checks}
