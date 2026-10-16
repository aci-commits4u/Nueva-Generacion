"""Presentation tests only: fixture proposals do not prove live AI quality."""
from copy import deepcopy

from app.conversation import apply_adaptive_plan, is_trusted_adaptive_question, question_contract_current
from app.ai_config import LEDGER_PROMPT_VERSION


def draft():
    return {'id':'fixture','domain':'flight','revision':1,'mode':'live',
            'messages':[{'role':'user','content':'Either EWR or JFK to MCO, no layovers.'}],
            'fields':{},'sources':{},'unsupported':[],
            'ai_runs':[{'trace':[{'prompt_version':LEDGER_PROMPT_VERSION}]}]}


def extraction(field='departure_date', known=False):
    fields={'origin_airports':['EWR','JFK'],'destination_airports':['MCO'],'max_connections':0}
    if known: fields[field]='2026-11-12'
    return {'pipeline':'ledger','mode':'live','model':'fixture',
            'fields':fields,'sources':{k:'Either EWR or JFK to MCO, no layovers.' for k in fields},
            'unsupported':[],'clarifications':[],
            'intent_ledger':{'revision':1,'records':[],'history':[]},
            'criteria':[{'key':k,'field':k,'text':k,'source_quote':'Either EWR or JFK to MCO, no layovers.',
                         'status':'captured','kind':'requirement','verification':'supported'} for k in fields],
            'adaptive_plan':{'action':'ask_user','assistant_message':'What date will you travel?',
                             'question':{'criterion_key':field,'field':field,'text':'What date will you travel?',
                                         'why':'The date determines which itinerary is acceptable.',
                                         'answer_kind':'date_choice','options':[]}}}


def test_ledger_question_is_bound_and_mirrored_without_snapshot_repair():
    d=draft(); e=extraction()
    apply_adaptive_plan(d,e)
    assert d['pipeline']=='ledger'
    assert d['fields']==e['fields']
    assert d['questions'][0]==d['adaptive_plan']['question']
    assert is_trusted_adaptive_question(d['questions'][0],domain='flight')
    assert question_contract_current(d)
    assert d['agent_tools']==[]


def test_settled_question_and_repeated_assistant_bubble_are_both_removed():
    d=draft(); e=extraction(known=True)
    apply_adaptive_plan(d,e)
    assert d['fields']['departure_date']=='2026-11-12'
    assert d['questions']==[]
    assert d['adaptive_plan']['question'] is None
    assert d['adaptive_plan']['assistant_message']==''
    assert question_contract_current(d)


def test_preferred_unknown_is_not_hardened_by_legacy_generic_condition_bridge():
    d=draft();e=extraction()
    e['criteria'].append({'key':'quiet','field':None,'text':'A quiet cabin would be nice',
                          'source_quote':'A quiet cabin would be nice','kind':'preference',
                          'verification':'unsupported','status':'captured'})
    apply_adaptive_plan(d,e)
    assert d['unsupported']==[]
    assert any(item['key']=='quiet' and item['kind']=='preference' for item in d['criteria'])
    assert e['criteria'][-1]['key']=='quiet'


def test_bad_ledger_revision_cannot_mutate_stored_state():
    import pytest
    d=draft();before=deepcopy(d);e=extraction();e['intent_ledger']['revision']=2
    with pytest.raises(ValueError,match='revision'):apply_adaptive_plan(d,e)
    assert d==before
