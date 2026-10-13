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
            turns.append({'role':'interface_question','field':message['reply_to']['field'],'content':message['reply_to']['question']})
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


def questions(domain,fields,clarifications=None,messages=None):
    profile=get_profile(domain)
    declined=declined_preferences(domain,messages)
    required=[{'field':k,'question':f['question'],'required':True} for k,f in profile['fields'].items() if f.get('required') and fields.get(k) is None]
    optional=[{'field':k,'question':f['question'],'required':False} for k,f in profile['fields'].items() if not f.get('required') and k not in fields and k not in declined]
    mentioned={item['field'] for item in (clarifications or [])}
    optional.sort(key=lambda item: item['field'] not in mentioned)
    return required+optional


def provenance(extraction,revision,messages=None):
    return {'revision':revision,'mode':extraction['mode'],'pipeline':extraction.get('pipeline','offline'),'model':extraction.get('model'),'trace':deepcopy(extraction.get('trace',[])),'fields':deepcopy(extraction['fields']),'sources':deepcopy(extraction['sources']),'unsupported':deepcopy(extraction['unsupported']),'clarifications':deepcopy(extraction.get('clarifications',[])),'guidance':extraction['explanation'],'conversation_digest':digest(messages or []),'source_message_indexes':{k:[i for i,m in enumerate(messages or []) if quote.casefold() in m['content'].casefold()] for k,quote in extraction['sources'].items()},'clarification_source_message_indexes':{item['field']:[i for i,m in enumerate(messages or []) if item['source_quote'].casefold() in m['content'].casefold()] for item in extraction.get('clarifications',[])}}
