"""Explicit offline intake for emergency operation; never claims to be a model."""
import re
from decimal import Decimal
from app.profile_registry import get_profile, digest
from app.airport_reference import airport_record
from app.temporal import resolve_date_choice


_AIRPORT_WIDGETS = {
    'origin_airports': re.compile(
        r'(?im)(?:^|(?<=[.!?\n]))[ \t]*'
        r'(?P<quote>Depart\s+from\s+(?P<codes>[A-Za-z]{3}(?:\s+or\s+[A-Za-z]{3}){0,9})'
        r'(?:[.!?](?=\s|$)|(?=\s*$)))'
    ),
    'destination_airports': re.compile(
        r'(?im)(?:^|(?<=[.!?\n]))[ \t]*'
        r'(?P<quote>Arrive\s+at\s+(?P<codes>[A-Za-z]{3}(?:\s+or\s+[A-Za-z]{3}){0,9})'
        r'(?:[.!?](?=\s|$)|(?=\s*$)))'
    ),
}
_DATE_WIDGET = re.compile(
    r'(?im)(?:^|(?<=[.!?\n]))[ \t]*'
    r'(?P<quote>(?:Travel|Dates?|Departure\s+date)\b[^\n.!?]*'
    r'\d{4}-\d{2}-\d{2}[^\n.!?]*'
    r'(?:[.!?](?=\s|$)|(?=\s*$)))'
)
_BROAD_AIRPORT_CODES = {'USA', 'NYC', 'CHI'}


def _trusted_airport_choices(codes_text):
    """Return a bounded, catalog-backed IATA choice set or ``None``."""
    raw_codes = re.split(r'\s+or\s+', codes_text.strip(), flags=re.I)
    if not 1 <= len(raw_codes) <= 10:
        return None
    codes = [code.upper() for code in raw_codes]
    if len(set(codes)) != len(codes) or any(
        code in _BROAD_AIRPORT_CODES or airport_record(code) is None
        for code in codes
    ):
        return None
    return codes


def _widget_airport_values(message, key):
    """Parse all exact widget sentences, selecting only the latest valid one."""
    matches = list(_AIRPORT_WIDGETS[key].finditer(message))
    if not matches:
        return None, [], False
    latest = matches[-1]
    values = _trusted_airport_choices(latest.group('codes'))
    if values is None:
        # A malformed/unknown typed choice must stay visible as unrecognized
        # text; do not fall back to its first airport code.
        return None, [], True
    return values, [match.group('quote').strip() for match in matches], True


def _widget_date_value(message):
    """Parse the latest exact typed date sentence without choosing a date."""
    matches = list(_DATE_WIDGET.finditer(message))
    if not matches:
        return None, [], False
    latest = matches[-1]
    quote = latest.group('quote').strip()
    value = resolve_date_choice(quote)
    if value is None:
        # Keep an invalid or unsupported latest correction in HOLD instead of
        # reviving an older valid date.
        return None, [], True
    return value, [match.group('quote').strip() for match in matches], True


def offline_extract(domain,message):
    fields={};sources={}; unsupported=[]; consumed=[]
    for key,pat,value in [('nonstop',r'non[ -]?stop',True),('refundable',r'\b(?:refundable|free cancellation)\b',True),('breakfast',r'\bbreakfast\b',True),('accessible',r'\baccessible\b',True)]:
        m=re.search(pat,message,re.I)
        if m and key in get_profile(domain)['fields']: fields[key]=value;sources[key]=m.group();consumed.append(m.group())
    money=re.search(r'(under|below|at most|max(?:imum)?|budget(?: of)?)\s*\$?\s*(\d+(?:\.\d{1,2})?)',message,re.I)
    if money:
        # The emergency parser must obey the same all-in price boundary as the
        # validated model path.  A unit price such as "nightly under $220"
        # remains visible as unsupported instead of becoming a total cap that
        # a later workflow step could accidentally treat as authoritative.
        from app.ai_grounding import _price_unit_source_span
        unit_quote = _price_unit_source_span(money.group(), message)
        if unit_quote:
            unsupported.append(unit_quote)
            consumed.append(unit_quote)
        else:
            fields['max_total_cents']=int(Decimal(money.group(2))*100)-(1 if money.group(1).lower() in {'under','below'} else 0);sources['max_total_cents']=money.group();consumed.append(money.group())
    if domain=='flight':
        from app.ai_grounding import one_way_quote_supported
        one_way=re.search(r'\bone[- ]way\b|\bonly\s+(?:need|want|book|require)\s+(?:the\s+)?outbound\b|\bonly outbound\b|\boutbound only\b',message,re.I)
        if one_way and one_way_quote_supported(message):
            fields['trip_type']='one_way';sources['trip_type']=one_way.group();consumed.append(one_way.group())
        # UI replies name one airport at a time; do not wait for a full route
        # or assign the first two capitalized tokens to arbitrary roles.
        for key,pattern in [
            ('origin_airports',r'\b(?i:from|depart from|leave from)\s+([A-Z]{3})\b'),
            ('destination_airports',r'\b(?i:to|arrive at)\s+([A-Z]{3})\b'),
        ]:
            choices,widget_sources,has_widget=_widget_airport_values(message,key)
            if has_widget:
                if choices is not None and key in get_profile(domain)['fields']:
                    fields[key]=choices;sources[key]=widget_sources[-1];consumed.extend(widget_sources)
                continue
            matches=list(re.finditer(pattern,message))
            if matches and matches[-1].group(1) not in _BROAD_AIRPORT_CODES:
                fields[key]=[matches[-1].group(1)];sources[key]=matches[-1].group();consumed.append(matches[-1].group())
        route=re.search(r'\b([A-Z]{3})\s+to\s+([A-Z]{3})\b',message)
        if route and 'origin_airports' not in fields and route.group(1) not in {'USA','NYC','CHI'}:
            fields['origin_airports']=[route.group(1)];sources['origin_airports']=route.group(1);consumed.append(route.group(1))
    dates=re.findall(r'\b\d{4}-\d{2}-\d{2}\b',message)
    if dates and domain=='flight':
        date_value,date_sources,has_date_widget=_widget_date_value(message)
        if has_date_widget:
            if date_value is not None and 'departure_date' in get_profile(domain)['fields']:
                fields['departure_date']=date_value;sources['departure_date']=date_sources[-1];consumed.extend(date_sources)
        else:
            fields['departure_date']=dates[0];sources['departure_date']=dates[0];consumed.append(dates[0])
    if domain=='hotel':
        if dates:
            fields['checkin_date']=dates[0];sources['checkin_date']=dates[0];consumed.append(dates[0])
            if len(dates)>1: fields['checkout_date']=dates[1];sources['checkout_date']=dates[1];consumed.append(dates[1])
        for city in ['Orlando','Miami','New York','Chicago','Boston','Tampa']:
            if city.lower() in message.lower(): fields['city']=city;sources['city']=city;consumed.append(city)
    # Only consumed spans and a small grammar of neutral connecting words are
    # understood. Preserve every other word, number, negation, or condition.
    remainder=message
    for source in consumed:
        remainder=re.sub(re.escape(source),' ',remainder,count=1,flags=re.I)
    grammar=r'\b(?:book|find|me|i|a|an|the|please|from|to|on|in|with|and|or|flight|hotel|depart|arrive|at|travel|between|inclusive|date|dates)\b'
    remainder=re.sub(grammar,' ',remainder,flags=re.I)
    if domain=='general' or re.search(r'[^\s.,;!?]',remainder):
        unsupported=[message]
    return {'fields':fields,'sources':sources,'unsupported':unsupported,'explanation':'Emergency parsing supports a small set of explicit phrases. Review the entire original request and every field; it does not infer arbitrary intent.','mode':'offline','model':None}


def refresh(d):
    d['digest']=digest({k:v for k,v in d.items() if k!='digest'})
    return d
