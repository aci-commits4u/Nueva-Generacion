"""Profile-driven clarification without AI consent or guessed preferences."""
from app.profile_registry import get_profile,digest
from copy import deepcopy
import json
import re


def user_text(messages):
    return '\n'.join(m['content'] for m in messages)


def context(messages):
    turns=[]
    for message in messages:
        if message.get('reply_to'):
            reply=message['reply_to']
            # Interface text is context only.  Keeping the stable question
            # contract here lets the model understand a short answer without
            # treating the interface wording as customer evidence.
            turns.append({'role':'interface_question',
                          'question_id':reply.get('question_id',reply.get('id')),
                          'field':reply.get('field'),
                          'response_type':reply.get('response_type'),
                          'options':reply.get('options',[]),
                          'content':reply.get('question')})
        turns.append({'role':'customer','content':message['content']})
    return json.dumps(turns,ensure_ascii=True)


def merge_unsupported(*groups):
    values=list(dict.fromkeys(x for group in groups for x in group))
    if len(values)>20 or sum(len(x.encode()) for x in values)>6000:
        raise ValueError('Too many flagged conditions for a reviewable demo request. Your previous draft is preserved; use review or split the request.')
    return values


def declined_preferences(domain,messages):
    """Route past explicit declines without turning them into approval.

    These source-linked choices only suppress redundant optional questions.
    Every omitted field must still be explicitly reviewed before signing.
    Required fields are never skipped by a no-preference statement.
    """
    profile=get_profile(domain)
    terms={
        'nonstop':r'non[- ]?stop', 'refundable':r'refundable|refundability|cancellation',
        'breakfast':r'breakfast', 'accessible':r'accessible|accessibility',
        'departure_window':r'departure time|departure window|takeoff time',
        'max_duration_minutes':r'trip duration|journey duration|flight duration',
        'max_connections':r'connections?|layovers?', 'cabin':r'cabin',
        'trip_type':r'trip type', 'rooms':r'rooms?',
    }
    declined={}
    for message in messages or []:
        if message.get('role') not in {'user','customer'}:continue
        text=message.get('content','')
        reply=message.get('reply_to') or {}
        field=reply.get('field');spec=profile['fields'].get(field,{})
        if (spec and not spec.get('required') and reply.get('question')==spec['question']
                and re.fullmatch(r'(?:no(?: thanks)?|no preference)[.!?, ]*',text.strip(),re.I)):
            declined[field]=text
        for clause in re.split(r'[.!?;\n]|\bbut\b|\bhowever\b|\band\s+(?=I\s+(?:require|need|want)\b)',text,flags=re.I):
            declines=re.search(r'\bno preference\b|\bno (?:need|requirement)\b|\b(?:do not|don[’\']t)\s+(?:require|need|care)\b|\bnot (?:required|needed)\b',clause,re.I)
            for key,term in terms.items():
                explicit_no_requirement=re.search(r'\bno\s+(?:'+term+r')\s+requirement\b',clause,re.I)
                if ((declines or explicit_no_requirement) and key in profile['fields'] and not profile['fields'][key].get('required')
                        and re.search(r'\b(?:'+term+r')\b',clause,re.I)):
                    declined[key]=clause.strip()
    return declined


def _response_type(spec):
    """Map a reviewed profile field to the shape of its customer answer."""
    field_type=spec.get('type') if isinstance(spec,dict) else None
    return {
        'strings':'multi',
        'date_choice':'date_choice',
        'window':'time_range',
    }.get(field_type,'single')


def _question_id(domain,field,spec):
    """Return a stable id for one profile question and answer contract."""
    question=spec.get('question','') if isinstance(spec,dict) else ''
    response_type=_response_type(spec)
    return f"q_{digest({'domain':domain,'field':field,'question':question,'response_type':response_type})[:16]}"


def _question(domain,field,spec,*,required=False):
    response_type=_response_type(spec)
    choices=spec.get('choices') or spec.get('enum') or spec.get('values') or []
    if not isinstance(choices,list):
        choices=[]
    question_id=_question_id(domain,field,spec)
    return {
        'id':question_id,
        'question_id':question_id,
        'field':field,
        'question':spec['question'],
        'required':bool(required),
        'response_type':response_type,
        'allow_multiple':response_type=='multi',
        'options':deepcopy(choices),
    }


def questions(domain,fields,clarifications=None,messages=None):
    """Plan only required gaps and source-backed ambiguities.

    Optional profile fields are choices for review, not an interrogation list.
    They become conversational questions only when the customer actually
    mentioned an ambiguous supported condition.  This prevents a nonstop
    requirement from triggering a redundant maximum-connections question.
    """
    profile=get_profile(domain)
    declined=declined_preferences(domain,messages)
    planned=[]
    for key,spec in profile['fields'].items():
        if spec.get('required') and fields.get(key) is None:
            planned.append(_question(domain,key,spec,required=True))
    planned_fields={item['field'] for item in planned}
    mentioned={}
    for item in clarifications or []:
        if not isinstance(item,dict):
            continue
        field=item.get('field')
        if (field not in profile['fields'] or fields.get(field) is not None
                or not item.get('source_quote')):
            continue
        if field in declined:
            continue
        mentioned.setdefault(field,item)
    for key,spec in profile['fields'].items():
        if key not in mentioned or key in planned_fields:
            continue
        # Nonstop is a stricter form of the connections rule. Asking for both
        # makes the conversation appear contradictory and invites a model to
        # manufacture a second preference.
        if key=='max_connections' and fields.get('nonstop') is True:
            continue
        planned.append(_question(domain,key,spec,required=bool(spec.get('required'))))
    return planned


_TEXT_EQUIVALENTS=str.maketrans({
    '\u2010':'-', '\u2011':'-', '\u2012':'-', '\u2013':'-', '\u2014':'-',
    '\u2015':'-', '\u2212':'-', '\u00a0':' ', '\u202f':' ',
})


def _quote_in_latest_turn(quote,latest_turn):
    if not isinstance(quote,str) or not isinstance(latest_turn,str):
        return False
    return quote.translate(_TEXT_EQUIVALENTS).casefold() in latest_turn.translate(_TEXT_EQUIVALENTS).casefold()


_CLARIFICATION_FIELD_HINTS={
    'max_total_cents':('budget','price','cost','total','under','up to','maximum','$','usd','dollar','flexible'),
    'origin_airports':('airport','depart','departure','from','newark','jfk','laguardia','lga','ewr'),
    'destination_airports':('airport','arrive','arrival','to','orlando','miami','tampa','mco','mia','tpa','fll','florida'),
    'departure_date':('date','travel','depart','departure','today','tomorrow','week','jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'),
    'nonstop':('nonstop','direct','connection','layover','stop'),
    'max_connections':('connection','layover','stop'),
    'departure_window':('time','morning','afternoon','evening','night','am','pm',':'),
    'max_duration_minutes':('duration','hour','minute','long'),
    'cabin':('cabin','economy','business','first','premium'),
    'refundable':('refund','refundable','cancellation'),
    'trip_type':('one-way','one way','outbound','round trip'),
    'city':('city','hotel','new york','orlando','miami','tampa','boston'),
    'checkin_date':('check-in','checkin','date','today','tomorrow','jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'),
    'checkout_date':('check-out','checkout','date','today','tomorrow','jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'),
    'breakfast':('breakfast','morning meal'),
    'accessible':('accessible','accessibility'),
    'rooms':('room','rooms'),
    'adults':('adult','adults','guest','guests'),
}


def _clarification_field_supported(domain,field,item,latest_turn,messages):
    """Bound a latest-turn clarification to the field it actually discusses."""
    quote=item.get('source_quote') if isinstance(item,dict) else None
    if field not in get_profile(domain).get('fields',{}) or not _quote_in_latest_turn(quote,latest_turn):
        return False
    # Grounding may provide a richer semantic-unit map as it evolves. Keep
    # this call optional so conversation state remains usable with older code.
    try:
        from app.ai_grounding import clarification_field_supported
    except ImportError:
        clarification_field_supported=None
    if clarification_field_supported is not None:
        try:
            if clarification_field_supported(
                field=field,quote=quote,domain=domain,source_messages=messages,
            ):
                return True
        except TypeError:
            pass
    latest_reply={}
    for message in reversed(messages or []):
        if message.get('content')==latest_turn and message.get('reply_to'):
            latest_reply=message['reply_to']
            break
    if latest_reply.get('field')==field:
        return True
    lowered=quote.translate(_TEXT_EQUIVALENTS).casefold()
    return any(token in lowered for token in _CLARIFICATION_FIELD_HINTS.get(field,()))


def merge_revision_state(domain,current,proposed,latest_turn,messages):
    """Reconcile a model proposal into the previous unapproved draft.

    The provider may omit a previously captured field while re-reading the
    whole conversation.  Omission therefore retains state.  A changed value
    is accepted only when its exact source quotation occurs in the latest
    customer turn; this keeps old model text from overwriting a newer choice.
    A latest source-backed clarification can reopen an existing value as a
    pending review item, while the change record keeps the old value and
    provenance for auditability.
    Explicit optional no-preference language clears a field for this draft,
    but remains unapproved until the structured review.
    """
    previous_fields=deepcopy(current.get('fields',{}))
    previous_sources=deepcopy(current.get('sources',{}))
    proposed_fields=proposed.get('fields',{}) if isinstance(proposed,dict) else {}
    proposed_sources=proposed.get('sources',{}) if isinstance(proposed,dict) else {}
    proposed_clarifications=proposed.get('clarifications',[]) if isinstance(proposed,dict) else []
    fields=deepcopy(previous_fields)
    sources=deepcopy(previous_sources)
    changes=[]
    all_declines=declined_preferences(domain,messages)
    latest_declines=declined_preferences(domain,[messages[-1]] if messages else [])
    latest_reopens={}
    for item in proposed_clarifications or []:
        field=item.get('field') if isinstance(item,dict) else None
        if (field in fields and field not in latest_declines
                and _clarification_field_supported(domain,field,item,latest_turn,messages)):
            latest_reopens[field]=deepcopy(item)
    for key,value in proposed_fields.items():
        quote=proposed_sources.get(key)
        if key not in fields:
            # A full-history provider response can recover a criterion that
            # the previous proposal missed. The original source remains
            # usable unless the customer explicitly declined that field in a
            # prior turn; a latest-turn quote always wins and supports a new
            # capture even after an earlier decline.
            if (not _quote_in_latest_turn(quote,latest_turn)
                    and key in all_declines):
                continue
            fields[key]=deepcopy(value)
            if isinstance(quote,str):
                sources[key]=deepcopy(quote)
            changes.append({'field':key,'kind':'captured','new_value':deepcopy(value),'new_source_quote':quote})
            continue
        if fields[key]==value:
            # Keep the original provenance unless the model supplied a newer
            # exact quote for the same value.
            if _quote_in_latest_turn(quote,latest_turn):
                sources[key]=deepcopy(quote)
            continue
        if _quote_in_latest_turn(quote,latest_turn):
            changes.append({'field':key,'kind':'corrected','old_value':deepcopy(fields[key]),
                            'new_value':deepcopy(value),'old_source_quote':sources.get(key),
                            'new_source_quote':quote})
            fields[key]=deepcopy(value)
            if isinstance(quote,str):
                sources[key]=deepcopy(quote)
    for key in latest_declines:
        if key in fields and not get_profile(domain)['fields'].get(key,{}).get('required'):
            changes.append({'field':key,'kind':'declined','old_value':deepcopy(fields[key]),
                            'old_source_quote':sources.get(key)})
            fields.pop(key,None)
            sources.pop(key,None)
    for key,item in latest_reopens.items():
        if key not in fields:
            continue
        changes.append({'field':key,'kind':'clarified','old_value':deepcopy(fields[key]),
                        'old_source_quote':sources.get(key),
                        'new_clarification':deepcopy(item)})
        fields.pop(key,None)
        sources.pop(key,None)
    clarifications={}
    for item in current.get('clarifications',[]) or []:
        if isinstance(item,dict) and item.get('field') not in fields:
            clarifications[item['field']]=deepcopy(item)
    for item in proposed_clarifications or []:
        if (isinstance(item,dict)
                and (item.get('field') not in fields or item.get('field') in latest_reopens)):
            clarifications[item.get('field')]=deepcopy(item)
    for key in latest_declines:
        clarifications.pop(key,None)
    return {
        'fields':fields,
        'sources':sources,
        'clarifications':list(clarifications.values()),
        'changes':changes,
    }


def provenance(extraction,revision,messages=None):
    return {'revision':revision,'mode':extraction['mode'],'pipeline':extraction.get('pipeline','offline'),'model':extraction.get('model'),'trace':deepcopy(extraction.get('trace',[])),'fields':deepcopy(extraction['fields']),'sources':deepcopy(extraction['sources']),'unsupported':deepcopy(extraction['unsupported']),'clarifications':deepcopy(extraction.get('clarifications',[])),'guidance':extraction['explanation'],'conversation_digest':digest(messages or []),'source_message_indexes':{k:[i for i,m in enumerate(messages or []) if quote.casefold() in m['content'].casefold()] for k,quote in extraction['sources'].items()},'clarification_source_message_indexes':{item['field']:[i for i,m in enumerate(messages or []) if item['source_quote'].casefold() in m['content'].casefold()] for item in extraction.get('clarifications',[])}}
