"""Synthetic quality reports and bounded authenticated production canaries."""
import json
import os
import secrets
import statistics
from datetime import datetime,timezone
from pathlib import Path
from fastapi import HTTPException
from app.store import get_store
from app.ai_config import selected_pipeline,PROMPT_VERSION
from evals.scoring import score_case

ROOT=Path(__file__).resolve().parent.parent


def display_report(report):
    if report and report.get('status')=='running':
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(report['started_at'])).total_seconds()
        if age>75:
            return {**report,'status':'unavailable','reason':'The scheduled worker was interrupted. Paid inference will not be replayed for this day.'}
    return report


def overview():
    benchmarks=[]
    for file in sorted((ROOT/'evals/reports').glob('*.json')):
        report=json.loads(file.read_text())
        rows=report['rows']
        benchmarks.append({'variant':report['variant'],'split':report['split'],'cases':report['cases'],'passed':report['passed'],'median_ms':round(statistics.median(r['duration_ms'] for r in rows)) if rows else 0,'model_calls':sum(len(r['result'].get('trace',[])) for r in rows),'reserved_calls':report.get('reserved_calls'),'model':report['model'],'created_at':report['created_at']})
    today=datetime.now(timezone.utc).date().isoformat()
    current=get_store().read('quality-'+today) or get_store().read('quality-latest')
    publication=ROOT/'evals/native-publication.json'
    return {'pipeline':selected_pipeline(),'prompt_version':PROMPT_VERSION,'benchmarks':benchmarks,'monitor':display_report(current.get('report')),
            'runtime':get_store().read('ai-runtime'),
            'native_evaluation':json.loads(publication.read_text()) if publication.exists() else None,
            'limitations':'Small synthetic benchmarks, not a guarantee of complete understanding. Original development and holdout scores describe the earlier prompts. Reliability-development includes deliberately difficult requests and records failures as well as successes. Customer review and deterministic enforcement remain mandatory.'}


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
        if state.get('report'):
            state['report']=display_report(state['report'])
            return False,state['report']
        report={'date':date.isoformat(),'case_id':case['id'],'status':'running','prompt_version':PROMPT_VERSION,'started_at':datetime.now(timezone.utc).isoformat()}
        state.update(owner=owner,report=report)
        return True,report
    claimed,report=get_store().mutate(key,claim)
    get_store().mutate('quality-latest',lambda state:state.update(report=report))
    if not claimed:return report
    try:
        from app.ai_pipeline import run_pipeline
        result=run_pipeline(case['domain'],case['message'],key,variant=selected_pipeline(),purpose='monitor')
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
