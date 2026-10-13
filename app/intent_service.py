"""Explicit offline intake for emergency operation; never claims to be a model."""
import re
from decimal import Decimal
from app.profile_registry import get_profile, digest


def offline_extract(domain,message):
    fields={};sources={}; unsupported=[]
    for key,pat,value in [('nonstop',r'non[ -]?stop',True),('refundable',r'\brefundable\b',True),('breakfast',r'\bbreakfast\b',True),('accessible',r'\baccessible\b',True)]:
        m=re.search(pat,message,re.I)
        if m and key in get_profile(domain)['fields']: fields[key]=value;sources[key]=m.group()
    money=re.search(r'(under|below|at most|max(?:imum)?|budget(?: of)?)\s*\$?\s*(\d+(?:\.\d{1,2})?)',message,re.I)
    if money:
        fields['max_total_cents']=int(Decimal(money.group(2))*100)-(1 if money.group(1).lower() in {'under','below'} else 0);sources['max_total_cents']=money.group()
    airports=re.findall(r'\b[A-Z]{3}\b',message)
    if domain=='flight' and len(airports)>=2:
        fields.update(origin_airports=[airports[0]],destination_airports=[airports[1]]);sources.update(origin_airports=airports[0],destination_airports=airports[1])
    dates=re.findall(r'\b\d{4}-\d{2}-\d{2}\b',message)
    if dates and domain=='flight': fields['departure_date']=dates[0];sources['departure_date']=dates[0]
    if domain=='hotel' and dates:
        fields['checkin_date']=dates[0];sources['checkin_date']=dates[0]
        if len(dates)>1: fields['checkout_date']=dates[1];sources['checkout_date']=dates[1]
        for city in ['Orlando','Miami','New York','Chicago','Boston']:
            if city.lower() in message.lower(): fields['city']=city;sources['city']=city
    if domain=='general' or re.search(r'quiet|ethical|comfortable|near |direct|layover|baggage|bag\b|round.?trip|return flight|morning|evening',message,re.I):
        unsupported=[message]
    return {'fields':fields,'sources':sources,'unsupported':unsupported,'explanation':'Emergency parsing supports a small set of explicit phrases. Review the entire original request and every field; it does not infer arbitrary intent.','mode':'offline','model':None}


def refresh(d):
    d['digest']=digest({k:v for k,v in d.items() if k!='digest'})
    return d
