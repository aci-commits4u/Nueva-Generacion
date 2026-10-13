"""Bounded gold-label experiments using the actual Foundry deployment."""
import argparse
import json
import time
import uuid
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
from app.ai_pipeline import run_pipeline
from evals.scoring import score_case


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--variant',choices=['baseline','guided','audited'],required=True)
    parser.add_argument('--split',choices=['development','holdout','regression'],default='development')
    args=parser.parse_args()
    cases=json.loads(Path('evals/cases.json').read_text())
    if isinstance(cases,dict): cases=cases['cases']
    cases=[c for c in cases if c['split']==args.split]
    session='eval-'+uuid.uuid4().hex
    rows=[]
    for case in cases:
        started=time.monotonic()
        try: result=run_pipeline(case['domain'],case['message'],session,variant=args.variant,purpose='evaluation')
        except ValueError as exc: result={'error':str(exc)}
        score=score_case(case,result)
        rows.append({'case':case,'result':result,'score':score,'duration_ms':round((time.monotonic()-started)*1000)})
        print(json.dumps({'case':case['id'],'passed':score['passed'],'duration_ms':rows[-1]['duration_ms'],'wrong':score.get('wrong_fields'),'invented':score.get('invented_fields'),'missed_unsupported':score.get('missed_unsupported')}),flush=True)
    report={'created_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'variant':args.variant,'split':args.split,'model':__import__('os').getenv('AZURE_OPENAI_DEPLOYMENT'),'cases':len(rows),'passed':sum(r['score']['passed'] for r in rows),'rows':rows}
    output=Path('evals/reports');output.mkdir(exist_ok=True)
    path=output/f'{args.variant}-{args.split}.json';path.write_text(json.dumps(report,indent=2))
    print(json.dumps({'report':str(path),'passed':report['passed'],'cases':len(rows)}))

if __name__=='__main__':main()
