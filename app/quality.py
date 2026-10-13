"""Synthetic quality reports and bounded authenticated production canaries."""
import json
import os
import secrets
import statistics
from datetime import datetime,timezone
from pathlib import Path
from fastapi import HTTPException
from app.store import get_store
from evals.scoring import score_case

ROOT=Path(__file__).resolve().parent.parent


def overview():
    benchmarks=[]
    for file in sorted((ROOT/'evals/reports').glob('*.json')):
        report=json.loads(file.read_text())
        rows=report['rows']
        benchmarks.append({'variant':report['variant'],'split':report['split'],'cases':report['cases'],'passed':report['passed'],'median_ms':round(statistics.median(r['duration_ms'] for r in rows)),'model_calls':sum(len(r['result'].get('trace',[])) for r in rows),'model':report['model'],'created_at':report['created_at']})
    current=get_store().read('quality-latest')
    return {'pipeline':os.getenv('AI_PIPELINE_VERSION','audited'),'benchmarks':benchmarks,'monitor':current.get('report'),'limitations':'Small synthetic benchmark, not a guarantee of complete understanding. The audited development run missed a direct-flight ambiguity (11/12); the untouched holdout passed 6/6. Customer review and deterministic enforcement remain mandatory.'}


def canary(authorization):
    secret=os.getenv('CRON_SECRET','')
    if not secret or not secrets.compare_digest((authorization or '').encode(),('Bearer '+secret).encode()):
        raise HTTPException(401,'Authenticated quality scheduler required.')
    date=datetime.now(timezone.utc).date()
    key='quality-'+date.isoformat()
    owner=secrets.token_hex(12)
    cases=json.loads((ROOT/'evals/cases.json').read_text())['cases']
    case=cases[date.toordinal()%len(cases)]
    def claim(state):
        if state.get('report'):return False,state['report']
        report={'date':date.isoformat(),'case_id':case['id'],'status':'running','started_at':datetime.now(timezone.utc).isoformat()}
        state.update(owner=owner,report=report)
        return True,report
    claimed,report=get_store().mutate(key,claim)
    if not claimed:return report
    try:
        from app.ai_pipeline import run_pipeline
        result=run_pipeline(case['domain'],case['message'],key,variant=os.getenv('AI_PIPELINE_VERSION','audited'),purpose='monitor')
        score=score_case(case,result)
        report.update(status='passed' if score['passed'] else 'failed',score=score,stages=len(result.get('trace',[])))
    except Exception:
        # No provider exception text or payload can reach this public report.
        report.update(status='unavailable',reason='Live inference could not complete within its configured limits. No fallback was used.')
    report['completed_at']=datetime.now(timezone.utc).isoformat()
    def finish(state):
        if state.get('owner')==owner:state['report']=report
    get_store().mutate(key,finish)
    get_store().mutate('quality-latest',lambda state:state.update(report=report))
    return report
