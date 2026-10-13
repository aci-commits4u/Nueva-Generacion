"""Explicit offline intake for emergency operation; never claims to be a model."""
import re
from decimal import Decimal
from app.profile_registry import get_profile, digest


def offline_extract(domain,message):
    fields={};sources={}; unsupported=[]
    for key,pat,value in [('nonstop',r'non[ -]?stop',True),('refundable',r'\b(?:refundable|free cancellation)\b',True),('breakfast',r'\bbreakfast\b',True),('accessible',r'\baccessible\b',True)]:
        m=re.search(pat,message,re.I)
        if m and key in get_profile(domain)['fields']: fields[key]=value;sources[key]=m.group()
    money=re.search(r'(under|below|at most|max(?:imum)?|budget(?: of)?)\s*\$?\s*(\d+(?:\.\d{1,2})?)',message,re.I)
    if money:
        fields['max_total_cents']=int(Decimal(money.group(2))*100)-(1 if money.group(1).lower() in {'under','below'} else 0);sources['max_total_cents']=money.group()
    if domain=='flight':
        # UI replies name one airport at a time; do not wait for a full route
        # or assign the first two capitalized tokens to arbitrary roles.
        for key,pattern in [
            ('origin_airports',r'\b(?i:from|depart from|leave from)\s+([A-Z]{3})\b'),
            ('destination_airports',r'\b(?i:to|arrive at)\s+([A-Z]{3})\b'),
        ]:
            matches=list(re.finditer(pattern,message))
            if matches and matches[-1].group(1) not in {'USA','NYC','CHI'}:
                fields[key]=[matches[-1].group(1)];sources[key]=matches[-1].group()
        route=re.search(r'\b([A-Z]{3})\s+to\s+([A-Z]{3})\b',message)
        if route and 'origin_airports' not in fields and route.group(1) not in {'USA','NYC','CHI'}:
            fields['origin_airports']=[route.group(1)];sources['origin_airports']=route.group(1)
    dates=re.findall(r'\b\d{4}-\d{2}-\d{2}\b',message)
    if dates and domain=='flight': fields['departure_date']=dates[0];sources['departure_date']=dates[0]
    if domain=='hotel':
        if dates:
            fields['checkin_date']=dates[0];sources['checkin_date']=dates[0]
            if len(dates)>1: fields['checkout_date']=dates[1];sources['checkout_date']=dates[1]
        for city in ['Orlando','Miami','New York','Chicago','Boston','Tampa']:
            if city.lower() in message.lower(): fields['city']=city;sources['city']=city
    # Only consumed spans and a small grammar of neutral connecting words are
    # understood. Preserve every other word, number, negation, or condition.
    remainder=message
    for source in sources.values():
        remainder=re.sub(re.escape(source),' ',remainder,count=1,flags=re.I)
    grammar=r'\b(?:book|find|me|a|an|the|please|from|to|on|in|with|and|flight|hotel|depart|arrive|at)\b'
    remainder=re.sub(grammar,' ',remainder,flags=re.I)
    if domain=='general' or re.search(r'[^\s.,;!?]',remainder):
        unsupported=[message]
    return {'fields':fields,'sources':sources,'unsupported':unsupported,'explanation':'Emergency parsing supports a small set of explicit phrases. Review the entire original request and every field; it does not infer arbitrary intent.','mode':'offline','model':None}


def refresh(d):
    d['digest']=digest({k:v for k,v in d.items() if k!='digest'})
    return d
