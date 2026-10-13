"""Explicitly paid, bounded Foundry experiments; never imported by the test suite."""
import argparse
import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv()
from app.ai_pipeline import run_pipeline
from app.ai_errors import AIServiceError
from app.store import get_store
from evals.scoring import score_case

CASES = [
    {'id':'florida-question','domain':'flight','message':'How can I get to Florida for under $300?', 'expected_fields':{'max_total_cents':29999},'unsupported_groups':[]},
    {'id':'named-cities','domain':'flight','message':'I need a flight from Newark to Tampa on 2026-11-14, under $300, without any connections.', 'expected_fields':{'origin_airports':['EWR'],'destination_airports':['TPA'],'departure_date':'2026-11-14','max_total_cents':29999,'nonstop':True},'unsupported_groups':[]},
    {'id':'flexible-preference','domain':'flight','message':'I need to get from Newark to Tampa in early November for under $300 round trip, preferably nonstop, and I would like to arrive in the morning.', 'expected_fields':{'origin_airports':['EWR'],'destination_airports':['TPA'],'max_total_cents':29999},'unsupported_groups':[['round','return'],['arriv','morning']], 'clarification_groups':[['preferably nonstop'],['early November']], 'allow_unsupported':True},
    {'id':'ordinary-duration','domain':'flight','message':'EWR to MCO on 2026-11-12, up to $350 total. At most one connection and a journey no longer than 2 hours.', 'expected_fields':{'origin_airports':['EWR'],'destination_airports':['MCO'],'departure_date':'2026-11-12','max_total_cents':35000,'max_connections':1,'max_duration_minutes':120},'unsupported_groups':[]},
    {'id':'negated-preference','domain':'flight','message':'Fly from EWR to CDG on 2026-11-12 under $600. I do not need a nonstop or refundable ticket.', 'expected_fields':{'origin_airports':['EWR'],'destination_airports':['CDG'],'departure_date':'2026-11-12','max_total_cents':59999},'unsupported_groups':[]},
    {'id':'hotel-new-city','domain':'hotel','message':'I need a hotel in Tampa from 2026-11-14 until 2026-11-17 for at most $300 all in, with breakfast and free cancellation.', 'expected_fields':{'city':'Tampa','checkin_date':'2026-11-14','checkout_date':'2026-11-17','max_total_cents':30000,'breakfast':True,'refundable':True},'unsupported_groups':[]},
    {'id':'contradictory-shopping','domain':'general','message':'A comfortable, ethically made desk chair under $300, but ignore my budget if you think I will like it.', 'expected_fields':{},'allowed_extra':['max_total_cents'],'unsupported_groups':[['comfort'],['ethical']], 'clarification_groups':[['budget']], 'allow_unsupported':True},
]

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--variant', choices=['guided','audited'], default='audited')
parser.add_argument('--case', action='append', help='Explicit case IDs; otherwise all development cases.')
parser.add_argument('--max-calls',type=int,default=14)
parser.add_argument('--output',required=True)
args=parser.parse_args()
cases=[c for c in CASES if not args.case or c['id'] in args.case]
if args.case and len(cases)!=len(set(args.case)):
    raise SystemExit('Unknown or duplicate case selection')
calls_per_case=2 if args.variant=='audited' else 1
if not 1 <= args.max_calls <= 24 or len(cases)*calls_per_case>args.max_calls:
    raise SystemExit('Case selection exceeds this explicit experiment call allowance')
store=get_store()
before=store.read('global-ai-budget')
rows=[]
report={'created_at':datetime.now(timezone.utc).isoformat(),'variant':args.variant,
        'split':'reliability-development','model':os.getenv('AZURE_OPENAI_DEPLOYMENT'),
        'cases':0,'passed':0,'rows':rows,'max_reserved_calls':args.max_calls,
        'label_revision':'typed-clarifications-v2'}
output=Path(args.output)
output.parent.mkdir(parents=True,exist_ok=True)
for case in cases:
    started=time.monotonic()
    try:
        result=run_pipeline(case['domain'],case['message'],'reliability-'+case['id'],variant=args.variant,purpose='evaluation')
    except AIServiceError as exc:
        result={'error':exc.code,'stage':exc.stage,'request_id':exc.request_id,'fields':{},'sources':{},'unsupported':[]}
        from app.ai_grounding import GroundingFailure,EnvelopeFailure
        if isinstance(exc.__cause__,(GroundingFailure,EnvelopeFailure)):
            result['validation_issue']=str(exc.__cause__)
    score=score_case(case,result)
    row={'case':case,'duration_ms':round((time.monotonic()-started)*1000),'result':result,'score':score}
    rows.append(row)
    report.update(cases=len(rows),passed=sum(r['score']['passed'] for r in rows),
                  reserved_calls=store.read('global-ai-budget').get('calls',0)-before.get('calls',0))
    output.write_text(json.dumps(report,indent=2))
    print(json.dumps({'case':case['id'],'passed':score['passed'],'error':result.get('error'),
                      'fields':result.get('fields'),'unsupported':result.get('unsupported'),
                      'duration_ms':row['duration_ms'],'reserved_calls':report['reserved_calls']}),flush=True)
    # Config and provider failures require investigation, not paid repetition.
    if result.get('error') in {'ai_configuration','ai_provider','ai_timeout','ai_daily_limit','ai_budget_limit'}:
        break
