"""Profile-driven clarification without AI consent or guessed preferences."""
from app.profile_registry import get_profile,digest
from copy import deepcopy
import json


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


def questions(domain,fields,clarifications=None):
    profile=get_profile(domain)
    required=[{'field':k,'question':f['question'],'required':True} for k,f in profile['fields'].items() if f.get('required') and fields.get(k) is None]
    optional=[{'field':k,'question':f['question'],'required':False} for k,f in profile['fields'].items() if not f.get('required') and k not in fields]
    mentioned={item['field'] for item in (clarifications or [])}
    optional.sort(key=lambda item: item['field'] not in mentioned)
    return required+optional


def provenance(extraction,revision,messages=None):
    return {'revision':revision,'mode':extraction['mode'],'pipeline':extraction.get('pipeline','offline'),'model':extraction.get('model'),'trace':deepcopy(extraction.get('trace',[])),'fields':deepcopy(extraction['fields']),'sources':deepcopy(extraction['sources']),'unsupported':deepcopy(extraction['unsupported']),'clarifications':deepcopy(extraction.get('clarifications',[])),'guidance':extraction['explanation'],'conversation_digest':digest(messages or []),'source_message_indexes':{k:[i for i,m in enumerate(messages or []) if quote.casefold() in m['content'].casefold()] for k,quote in extraction['sources'].items()},'clarification_source_message_indexes':{item['field']:[i for i,m in enumerate(messages or []) if item['source_quote'].casefold() in m['content'].casefold()] for item in extraction.get('clarifications',[])}}
