"""Profile-driven clarification without AI consent or guessed preferences."""
from app.profile_registry import get_profile


def context(messages):
    return '\n'.join(m['content'] for m in messages)


def questions(domain,fields):
    profile=get_profile(domain)
    required=[{'field':k,'question':f['question'],'required':True} for k,f in profile['fields'].items() if f.get('required') and fields.get(k) is None]
    optional=[{'field':k,'question':f['question'],'required':False} for k,f in profile['fields'].items() if not f.get('required') and k not in fields]
    return required+optional


def provenance(extraction,revision):
    return {'revision':revision,'mode':extraction['mode'],'pipeline':extraction.get('pipeline','offline'),'model':extraction.get('model'),'trace':extraction.get('trace',[])}
