"""Evidence is application context for an analyst, never a liability ruling."""
from app.vi_adapter import sign_record,public_keys
from app.profile_registry import digest


def make_evidence(receipt,draft,decision,events):
    packet={'schema':'intent-judge.evidence.v1','mode':'synthetic demo','purchase':receipt,'original_request':draft['message'],'extraction_mode':draft['mode'],'conversation':draft.get('messages',[]),'interpretation_runs':draft.get('ai_runs',[]),'approved_requirements':decision['approved'],'decision':{k:v for k,v in decision.items() if k not in {'bundle','original_bundle','approved','exceptions'}},'exceptions':decision.get('exceptions',[]),'vi_bundle':decision['bundle'],'original_vi_bundle':decision.get('original_bundle'),'events':events,'public_keys':public_keys(),'responsibility_recommendation':'Review the approved requirements, verified offer, and specific exceptions before allocating responsibility.','final_decision':'dispute analyst'}
    if draft.get('intent_ledger') is not None:
        packet['intent_ledger']=draft['intent_ledger']
    packet['digest']=digest(packet)
    packet['signed_evidence']=sign_record({'evidence_digest':packet['digest'],'purchase_id':receipt['id']},'issuer')
    return packet
