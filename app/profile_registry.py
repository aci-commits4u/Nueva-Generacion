"""Reviewed profiles select a fixed set of typed operators, never executable code."""
import hashlib
import json
import re
from datetime import date
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

def normalise_review_fields(domain,fields):
    """Canonicalize case-only task values, preserving reviewed meaning."""
    result=dict(fields)
    if domain=='flight':
        if isinstance(result.get('cabin'),str):result['cabin']=result['cabin'].strip().casefold()
        if isinstance(result.get('trip_type'),str) and result['trip_type'].strip().casefold() in {'one way','one-way','one_way'}:
            result['trip_type']='one_way'
    return result


_ISO_DATE = re.compile(r"\A\d{4}-\d{2}-\d{2}\Z")


def valid_iso_date(value):
    """Accept only the canonical date shape used by signed merchant facts."""
    if type(value) is not str or not _ISO_DATE.fullmatch(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def valid_date_choice(value):
    """Validate an exact date, bounded range, or finite date alternatives."""
    if valid_iso_date(value):
        return True
    if type(value) is not dict:
        return False
    if set(value) == {'start', 'end'}:
        start, end = value['start'], value['end']
        if not valid_iso_date(start) or not valid_iso_date(end):
            return False
        start_date, end_date = date.fromisoformat(start), date.fromisoformat(end)
        return start_date <= end_date and (end_date - start_date).days <= 366
    if set(value) == {'dates'}:
        dates = value['dates']
        return (
            type(dates) is list
            and 0 < len(dates) <= 20
            and all(valid_iso_date(item) for item in dates)
            and len(set(dates)) == len(dates)
        )
    return False

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
        valid = (t=='integer' and type(value) is int and value>=0) or (t=='boolean' and type(value) is bool) or (t=='string' and type(value) is str and 0<len(value)<=120) or (t=='strings' and type(value) is list and 0<len(value)<=20 and all(type(v) is str and len(v)<=120 for v in value)) or (t=='window' and type(value) is list and len(value)==2 and all(valid_time(v) for v in value)) or (t=='date_choice' and valid_date_choice(value))
        if not valid:
            raise ValueError(f'Invalid value for {key}')
        if f.get('enum') and value not in f['enum']:
            raise ValueError(f'Unsupported choice for {key}')
        if f.get('min') is not None and (type(value) is not int or value<f['min']):
            raise ValueError(f'Invalid minimum value for {key}')
        if key in {'origin_airports','destination_airports'}:
            import re
            if any(not re.fullmatch(r'[A-Z]{3}',airport) or airport in {'USA','NYC','CHI'} for airport in value):
                raise ValueError('Choose three-letter airport codes, such as EWR or MCO; city and region names need clarification.')
        if t=='date_choice' and not valid_date_choice(value):
            raise ValueError(f'Invalid value for {key}')
        if key.endswith('date') and t=='string':
            if not valid_iso_date(value):
                raise ValueError(f'Invalid value for {key}')

def valid_time(v):
    import re
    return type(v) is str and bool(re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',v))
