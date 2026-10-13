"""Reviewed profiles select a fixed set of typed operators, never executable code."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()

def get_profile(domain):
    if domain not in {'flight','hotel','general'}:
        raise ValueError('Unknown domain')
    p=json.loads((ROOT/'profiles'/f'{domain}.json').read_text())
    p['digest']=digest(p)
    return p

def validate_fields(profile, fields):
    if len(fields)>30:
        raise ValueError('Too many requirements')
    for key,value in fields.items():
        if key not in profile['fields']:
            raise ValueError(f'Unsupported field: {key}')
        if value is None:
            continue
        f=profile['fields'][key]
        t=f['type']
        valid = (t=='integer' and type(value) is int and value>=0) or (t=='boolean' and type(value) is bool) or (t=='string' and type(value) is str and 0<len(value)<=120) or (t=='strings' and type(value) is list and 0<len(value)<=20 and all(type(v) is str and len(v)<=120 for v in value)) or (t=='window' and type(value) is list and len(value)==2 and all(valid_time(v) for v in value))
        if not valid:
            raise ValueError(f'Invalid value for {key}')
        if key.endswith('date'):
            from datetime import date
            date.fromisoformat(value)

def valid_time(v):
    import re
    return type(v) is str and bool(re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',v))
