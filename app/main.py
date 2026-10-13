"""Intent Judge's server-owned approval, verification, and simulated purchase gate."""
import json
import os
import secrets
import time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit
from contextlib import contextmanager
from functools import wraps
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent/'.env')
from fastapi import FastAPI,HTTPException,Request,Response
from fastapi.responses import FileResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from app.models import IntentRequest,AnswerRequest,ApprovalRequest,CheckRequest,ExceptionRequest,PurchaseRequest,DisputeRequest,ClarifyRequest
from app.profile_registry import get_profile,validate_fields,digest
from app.rules_engine import evaluate
from app.store import get_store,ai_capacity
from app.ai_errors import AIServiceError
from app.ai_config import selected_pipeline,selected_reasoning_effort
from app.intent_service import offline_extract,refresh
from app.vi_adapter import issue,verify,offer_hash,sign_record,read_signed
from app.evidence import make_evidence
from app.conversation import context,user_text,questions,provenance,merge_unsupported
from demo.fixtures import offers_for

ROOT=Path(__file__).resolve().parent.parent
app=FastAPI(title='Intent Judge',version='1.0.0')
MAX_FOLLOWUPS=6


def live_configuration_ready():
    endpoint=urlsplit(os.getenv('AZURE_OPENAI_ENDPOINT',''))
    try: selected_reasoning_effort()
    except ValueError: return False
    return bool(endpoint.scheme=='https' and endpoint.netloc and
                os.getenv('AZURE_OPENAI_API_KEY') and os.getenv('AZURE_OPENAI_DEPLOYMENT') and
                selected_pipeline() in {'baseline','guided','audited'})


def conversation_view(draft):
    return {**draft,'max_followups':MAX_FOLLOWUPS,
            'followups_remaining':max(0,MAX_FOLLOWUPS-(len(draft.get('messages',[]))-1))}


@app.exception_handler(AIServiceError)
async def ai_service_error(request,exc):
    headers={'Retry-After':str(exc.retry_after_seconds)} if exc.retry_after_seconds is not None else {}
    return JSONResponse({'detail':str(exc),'error':exc.public()},status_code=exc.status_code,headers=headers)

def now(): return datetime.now(timezone.utc).isoformat()
def uid(): return secrets.token_urlsafe(16)

def session_id(request):
    sid=request.cookies.get('ij_session')
    if not sid or len(sid)!=43 or not get_store().read(sid).get('created'):
        raise HTTPException(401,'Start a demo session first.')
    if time.time()-get_store().read(sid)['created']>28800:
        raise HTTPException(401,'Demo session expired. Reload to start again.')
    return sid


@contextmanager
def interpretation_slot(sid):
    """Prevent concurrent UI/retry requests paying for the same active turn."""
    token=uid()
    def claim(state):
        pending=state.get('_ai_pending')
        if pending and time.time()-pending['started_at']<75:
            raise HTTPException(409,'A request is already being interpreted. Wait for its response before sending another detail.')
        state['_ai_pending']={'token':token,'started_at':time.time()}
    get_store().mutate(sid,claim)
    try:
        yield
    finally:
        def release(state):
            if state.get('_ai_pending',{}).get('token')==token:
                state.pop('_ai_pending',None)
        get_store().mutate(sid,release)


def serialize_interpretation(fn):
    @wraps(fn)
    def wrapped(*args,**kwargs):
        request=kwargs['request']
        with interpretation_slot(session_id(request)):
            return fn(*args,**kwargs)
    return wrapped

def event(s,kind,data):
    events=s.setdefault('events',[])
    events.append({'index':len(events),'timestamp':now(),'kind':kind,'data':data,'previous_hash':digest(events[-1]) if events else None})

def required(s,collection,id):
    obj=s.get(collection,{}).get(id)
    if obj is None: raise HTTPException(404,'This record is not in your demo session.')
    return obj

def integrity(check_id,ok,message):
    return {'check_id':check_id,'label':check_id.replace('_',' ').title(),'requirement':True,'offer_value':ok,'status':'pass' if ok else 'fail','message':message,'exception_allowed':False,'integrity':True}

def judge(s,d):
    draft=required(s,'drafts',d['intent_id'])
    approved=d['approved']
    fresh=draft.get('approved')==approved
    v=verify(d['bundle'],approved)
    gates=[integrity('approval_current',fresh,'The signed requirements must match your current approval.'),integrity('cryptographic_integrity',v['valid'],v.get('error','VI chain and merchant signature passed.'))]
    if v['valid']:
        for i,l in enumerate(v['ledger']):
            if l['status']!='pass':
                gates.append({'check_id':'native_'+str(i),'label':'VI purchasing constraint','requirement':l['type'],'offer_value':None,'status':l['status'],'message':l['message'],'exception_allowed':False})
    result=evaluate(get_profile(approved['domain']),approved['fields'],v['facts'],approved['unsupported'],gates)
    return result,v

@app.middleware('http')
async def boundaries(request,call_next):
    if request.method in {'POST','PUT','PATCH','DELETE'}:
        origin=request.headers.get('origin')
        if (origin and urlsplit(origin).netloc!=request.headers.get('host')) or request.headers.get('sec-fetch-site')=='cross-site':
            return JSONResponse({'detail':'Cross-origin writes are not allowed.'},status_code=403)
        if int(request.headers.get('content-length','0') or 0)>20000:
            return JSONResponse({'detail':'Request is too large.'},status_code=413)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    response.headers['Content-Security-Policy']="default-src 'self'; style-src 'self'; img-src 'self' data:; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    if request.url.path.startswith('/api'):
        response.headers['Cache-Control']='no-store'
    return response

@app.get('/api/quality')
def quality():
    from app.quality import overview
    return overview()

@app.get('/api/internal/quality-check')
def quality_check(request:Request):
    from app.quality import canary
    return canary(request.headers.get('authorization'))

@app.get('/api/health')
def health():
    return {'status':'ok','live_ai_configured':live_configuration_ready(),'offline_only':os.getenv('MOCK_LLM')=='1','commerce':'simulated','sdk':'verifiable-intent 0.1.0 / 356c296','storage':os.getenv('STORE_BACKEND','sqlite')}


@app.get('/api/ai/status')
def ai_status(request:Request):
    capacity=ai_capacity(session_id(request))
    pipeline=selected_pipeline()
    calls=2 if pipeline=='audited' else 1
    configured=live_configuration_ready()
    reason=None
    if not configured:
        reason=AIServiceError('ai_configuration','Live AI is not configured completely. The tutorial remains available; offline mode is an explicit alternative.')
    elif os.getenv('MOCK_LLM')=='1':
        reason=AIServiceError('ai_disabled','Live AI is disabled in this environment. Choose offline mode explicitly to try the demo.')
    elif capacity['lifetime_remaining_calls']<calls:
        reason=AIServiceError('ai_budget_limit','Live AI is paused to protect the remaining demo credit. Your request is kept; the tutorial remains available.')
    elif capacity['session_remaining_calls']<calls:
        reason=AIServiceError('ai_session_limit','This session has reached its live AI allowance. You can keep reviewing the draft or start a new request session.',status_code=429)
    elif capacity['daily_remaining_calls']<calls:
        reason=AIServiceError('ai_daily_limit','Today’s live AI allowance is reached. It resumes at midnight UTC. Your request is kept; the tutorial remains available.',status_code=429,retry_after_seconds=capacity['reset_after_seconds'])
    reset_at=datetime.fromtimestamp(time.time()+capacity['reset_after_seconds'],timezone.utc).isoformat()
    return {'configured':configured,'available':reason is None,'reason':reason.public() if reason else None,
            'pipeline':pipeline,'model':os.getenv('AZURE_OPENAI_DEPLOYMENT'),'interpretation_calls':calls,
            'remaining_calls':capacity['remaining_calls'],'session_remaining_calls':capacity['session_remaining_calls'],
            'remaining_interpretations':min(capacity['remaining_calls'],capacity['session_remaining_calls'])//calls,
            'reset_at':reset_at}

@app.get('/api/session')
def session(request:Request,response:Response):
    sid=request.cookies.get('ij_session')
    s=get_store().read(sid) if sid and len(sid)==43 else {}
    if not s or time.time()-s.get('created',0)>28800:
        sid=secrets.token_urlsafe(32)
        get_store().mutate(sid,lambda state:state.update({'created':time.time(),'drafts':{},'offers':{},'decisions':{},'purchases':{},'idempotency':{},'events':[]}))
    response.set_cookie('ij_session',sid,max_age=28800,httponly=True,secure=request.url.scheme=='https' or bool(os.getenv('VERCEL')),samesite='strict')
    s=get_store().read(sid)
    return {'synthetic_actor':'Demo traveler','ai_calls':s.get('ai_calls',0),'intents':[{'id':d['id'],'domain':d['domain'],'message':d['message'],'approved':bool(d.get('approved'))} for d in s['drafts'].values()]}

@app.post('/api/session/reset')
def reset_session(request:Request,response:Response):
    session_id(request)
    response.delete_cookie('ij_session',secure=request.url.scheme=='https' or bool(os.getenv('VERCEL')),httponly=True,samesite='strict')
    return {'reset':True}

@app.get('/api/profiles')
def profiles(): return [get_profile(x) for x in ('flight','hotel','general')]
@app.get('/api/profiles/{domain}')
def profile(domain:str):
    try: return get_profile(domain)
    except ValueError as e: raise HTTPException(404,str(e))

@app.post('/api/intents')
@serialize_interpretation
def intake(body:IntentRequest,request:Request):
    sid=session_id(request)
    s=get_store().read(sid)
    if len(s.get('drafts',{}))>=3: raise HTTPException(429,'This session has three scenarios. Start a fresh session to explore another.')
    if body.mode=='offline': extraction=offline_extract(body.domain,body.message)
    else:
        from app.foundry_client import extract
        try: extraction=extract(body.domain,body.message,sid,source_messages=[{'role':'user','content':body.message}])
        except AIServiceError: raise
        except ValueError as exc: raise HTTPException(503,str(exc))
    d=refresh({'id':uid(),'revision':1,'domain':body.domain,'profile_digest':get_profile(body.domain)['digest'],'message':body.message,'fields':extraction['fields'],'sources':extraction['sources'],'unsupported':extraction['unsupported'],'explanation':extraction['explanation'],'mode':extraction['mode'],'model':extraction['model'],'reviewed':False,'created_at':now(),'messages':[{'role':'user','content':body.message,'timestamp':now()}],'ai_runs':[provenance(extraction,1)],'questions':questions(body.domain,extraction['fields'])})
    d['ai_runs']=[provenance(extraction,1,d['messages'])]
    d['clarifications']=extraction.get('clarifications',[])
    d['questions']=questions(body.domain,d['fields'],d['clarifications'])
    try: d['unsupported']=merge_unsupported(d['unsupported'])
    except ValueError as exc: raise HTTPException(422,str(exc))
    refresh(d)
    def save(state):
        if len(state['drafts'])>=3: raise HTTPException(429,'Scenario limit reached.')
        state['drafts'][d['id']]=d;event(state,'intent_extracted',{'intent_id':d['id'],'revision':1,'mode':d['mode']})
        return d
    return conversation_view(get_store().mutate(sid,save))

@app.get('/api/intents/{id}')
def get_intent(id:str,request:Request):
    s=get_store().read(session_id(request));d=required(s,'drafts',id)
    decisions=[{k:v for k,v in obj.items() if k not in {'bundle','original_bundle','approved'}} for obj in s['decisions'].values() if obj['intent_id']==id]
    purchases=[p['receipt'] for p in s['purchases'].values() if any(v['id']==p['receipt']['decision_id'] for v in decisions)]
    return conversation_view({**d,'saved_decisions':decisions,'latest_purchase':purchases[-1] if purchases else None})

@app.post('/api/intents/{id}/clarify')
@serialize_interpretation
def clarify(id:str,body:ClarifyRequest,request:Request):
    sid=session_id(request)
    d=required(get_store().read(sid),'drafts',id)
    if body.revision!=d['revision']: raise HTTPException(409,'Your request changed. Reload the latest conversation.')
    messages=d.get('messages',[{'role':'user','content':d['message'],'timestamp':d['created_at']}])
    if len(messages)>=MAX_FOLLOWUPS+1: raise HTTPException(409,'Review the captured requirements to continue; this demo allows six AI follow-ups, and every field remains editable in review.')
    reply_to=(d.get('questions') or questions(d['domain'],d['fields']) or [None])[0]
    messages=messages+[{'role':'user','content':body.message,'timestamp':now(),'reply_to':reply_to}]
    text=context(messages)
    if len(user_text(messages))>5000: raise HTTPException(422,'Conversation is too long for this demo.')
    if d['mode']=='offline': extraction=offline_extract(d['domain'],user_text(messages))
    else:
        from app.foundry_client import extract
        try: extraction=extract(d['domain'],text,sid,source_text=user_text(messages),source_messages=messages)
        except AIServiceError: raise
        except ValueError as exc: raise HTTPException(503,str(exc))
    def save(state):
        current=required(state,'drafts',id)
        if current['revision']!=body.revision: raise HTTPException(409,'Another edit arrived during interpretation. Reload your latest draft.')
        try: unsupported=merge_unsupported(current['unsupported'],extraction['unsupported'])
        except ValueError as exc: raise HTTPException(422,str(exc))
        revision=current['revision']+1
        previous_clarifications=current.get('clarifications',[])
        current.update(fields=extraction['fields'],sources=extraction['sources'],unsupported=unsupported,explanation=extraction['explanation'],messages=messages,revision=revision,reviewed=False,questions=questions(d['domain'],extraction['fields']))
        next_clarifications=extraction.get('clarifications',[])
        by_field={item['field']:item for item in next_clarifications}
        for item in previous_clarifications:
            if item['field'] not in current['fields'] and item['field'] not in by_field:
                by_field[item['field']]=item
            elif item['field'] in current['fields']:
                event(state,'clarification_interpreted',{'intent_id':id,'revision':revision,'field':item['field'],
                      'original_quote':item['source_quote'],'proposed_value':current['fields'][item['field']],
                      'new_source_quote':current['sources'].get(item['field']),
                      'authority':'unapproved draft; customer review still required'})
        current['clarifications']=list(by_field.values())
        current['questions']=questions(d['domain'],current['fields'],current['clarifications'])
        current.setdefault('ai_runs',[]).append(provenance(extraction,revision,messages))
        current.pop('approved',None);current.pop('offer_views',None)
        refresh(current);event(state,'intent_clarified',{'intent_id':id,'revision':revision,'digest':current['digest']})
        return current
    return conversation_view(get_store().mutate(sid,save))

@app.post('/api/intents/{id}/answers')
def answers(id:str,body:AnswerRequest,request:Request):
    def update(s):
        d=required(s,'drafts',id)
        if not body.confirmation or body.revision!=d['revision']: raise HTTPException(409,'Confirm your review of the current draft revision.')
        p=get_profile(d['domain'])
        try: validate_fields(p,body.fields)
        except ValueError as e: raise HTTPException(422,str(e))
        if set(body.fields)!=set(p['fields']): raise HTTPException(409,'Review every field, including explicit no preference.')
        if any(body.fields[k] is None for k,v in p['fields'].items() if v.get('required')): raise HTTPException(409,'Required task details must be specified.')
        if any(x not in d['unsupported'] or x in body.unsupported for x in body.removed_unsupported): raise HTTPException(409,'A removed condition must exactly identify a current flagged condition.')
        if any(x not in body.unsupported and x not in body.removed_unsupported for x in d['unsupported']): raise HTTPException(409,'Flagged conditions require a specific recorded traveler removal; the AI cannot remove them.')
        if body.removed_unsupported: event(s,'condition_removed_by_traveler',{'intent_id':id,'revision':d['revision'],'draft_digest':d['digest'],'conditions':body.removed_unsupported,'meaning':'Traveler explicitly removed these as separate purchasing requirements; reviewed fields govern.'})
        if d['domain']=='hotel' and body.fields['checkout_date']<=body.fields['checkin_date']: raise HTTPException(422,'Check-out must follow check-in.')
        if d.get('clarifications'):
            event(s,'clarifications_resolved_by_traveler',{'intent_id':id,'revision':d['revision'],'draft_digest':d['digest'],
                  'choices':[{'field':item['field'],'source_quote':item['source_quote'],'reason':item['reason'],
                              'reviewed_value':body.fields[item['field']],'meaning':'explicit no preference' if body.fields[item['field']] is None else 'customer-reviewed value'}
                             for item in d['clarifications']]})
            d['clarifications']=[]
        d.update(fields=body.fields,unsupported=body.unsupported,revision=d['revision']+1,reviewed=True)
        d.pop('approved',None)
        refresh(d);event(s,'requirements_reviewed',{'intent_id':id,'revision':d['revision'],'digest':d['digest']})
        return d
    return get_store().mutate(session_id(request),update)

@app.post('/api/intents/{id}/approve')
def approve(id:str,body:ApprovalRequest,request:Request):
    sid=session_id(request)
    def action(s):
        d=required(s,'drafts',id)
        if not body.confirmation or body.revision!=d['revision'] or body.digest!=d['digest'] or not d['reviewed']:
            raise HTTPException(409,'Approve the exact reviewed draft and digest.')
        if d.get('approved'):
            return {'approved':d['approved'],'offers':d['offer_views']}
        approved={'id':id,'revision':d['revision'],'domain':d['domain'],'profile_digest':d['profile_digest'],'fields':d['fields'],'unsupported':d['unsupported'],'actor':'traveler-'+digest({'session':sid})[:20],'approved_at':now(),'draft_digest':d['digest']}
        d['approved']=approved
        views=[]
        for o in offers_for(approved):
            bundle=issue(approved,o['checkout_jwt']);v=verify(bundle,approved)
            if not v['valid']: raise HTTPException(500,'Synthetic merchant fixture did not verify.')
            s['offers'][o['id']]={'intent_id':id,'bundle':bundle,'facts':v['facts']}
            views.append({'id':o['id'],'facts':v['facts'],'offer_hash':v['offer_hash'],'expires_at':v['offer']['exp'],'merchant':'Demo Travel','signed':True})
        d['offer_views']=views;event(s,'requirements_approved',{'intent_id':id,'approved_digest':digest(approved),'signed_authorization':True})
        return {'approved':approved,'offers':views}
    return get_store().mutate(sid,action)

@app.post('/api/check')
def check(body:CheckRequest,request:Request):
    def action(s):
        draft=required(s,'drafts',body.intent_id);o=required(s,'offers',body.offer_id)
        if not draft.get('approved') or o['intent_id']!=body.intent_id: raise HTTPException(409,'Offer requires its matching approval.')
        if len(s['decisions'])>=25: raise HTTPException(429,'This session has reached its verification allowance.')
        d={'id':uid(),'intent_id':body.intent_id,'offer_id':body.offer_id,'approved':draft['approved'],'bundle':o['bundle'],'offer_hash':offer_hash(o['bundle']['checkout_jwt']),'approved_digest':digest(draft['approved']),'exceptions':[],'created_at':now()}
        result,v=judge(s,d);d.update(result,ledger=v['ledger'],facts=v['facts'])
        # Native verification shows authorized rules; domain checks capture more detailed intent.
        d['native_vi_passed']=v['valid'] and v['native_ok']
        s['decisions'][d['id']]=d;event(s,'offer_checked',{'decision_id':d['id'],'offer_hash':d['offer_hash'],'status':d['status'],'checks':d['checks']})
        return {k:v for k,v in d.items() if k not in {'bundle','approved'}}
    return get_store().mutate(session_id(request),action)

@app.post('/api/decisions/{id}/explain')
def explain_decision(id:str,request:Request):
    sid=session_id(request);s=get_store().read(sid);d=required(s,'decisions',id)
    result,v=judge(s,d)
    cache_key=digest({'checks':result['checks'],'exceptions':d['exceptions']})
    if d.get('explanation_key')==cache_key: return d['explanation']
    from app.foundry_client import explain
    try: narrative=explain(result,sid,required(s,'drafts',d['intent_id'])['mode'])
    except AIServiceError: raise
    except ValueError as exc: raise HTTPException(503,str(exc))
    def save(state):
        current=required(state,'decisions',id)
        current['explanation']=narrative;current['explanation_key']=cache_key
        event(state,'decision_explained',{'decision_id':id,'mode':narrative['mode'],'authority':'none'})
        return narrative
    return get_store().mutate(sid,save)

@app.post('/api/decisions/{id}/exceptions')
def accept_exception(id:str,body:ExceptionRequest,request:Request):
    sid=session_id(request)
    def action(s):
        d=required(s,'decisions',id);result,v=judge(s,d)
        if not body.confirmation or body.offer_hash!=d['offer_hash'] or result['status']=='BLOCK': raise HTTPException(409,'Specific acceptance needs a current, trustworthy offer and matching hash.')
        by_id={c['check_id']:c for c in result['checks']}
        selected=[]
        for check_id in set(body.check_ids):
            c=by_id.get(check_id)
            if not c or c['status']=='pass' or not c['exception_allowed']: raise HTTPException(409,'This check cannot be accepted as an exception.')
            record={'check_id':check_id,'requirement':c['requirement'],'accepted_value':c['offer_value'],'accepted_status':c['status'],'offer_hash':d['offer_hash'],'approved_digest':d['approved_digest'],'profile_digest':d['approved']['profile_digest'],'actor':d['approved']['actor'],'timestamp':now()}
            record['signature']=sign_record(record)
            selected.append(record)
        d['exceptions']=[e for e in d['exceptions'] if e['check_id'] not in body.check_ids]+selected
        if 'max_total_cents' in body.check_ids:
            if v['facts'].get('currency')!='USD' or type(v['facts'].get('total_cents')) is not int: raise HTTPException(409,'A new native amount authorization requires a known USD total.')
            # Specific signed acceptance authorizes this exact offer's revised native cap.
            d.setdefault('original_bundle',d['bundle'])
            d['bundle']=issue(d['approved'],d['bundle']['checkout_jwt'],native_max=v['facts']['total_cents'])
            d['reauthorization_exceptions']=[e['signature'] for e in d['exceptions'] if e['check_id']=='max_total_cents']
        event(s,'exceptions_accepted',{'decision_id':id,'exceptions':selected})
        return {'exceptions':d['exceptions'],'offer_hash':d['offer_hash'],'native_reauthorized':bool(d.get('original_bundle'))}
    return get_store().mutate(sid,action)

@app.post('/api/purchase')
def purchase(body:PurchaseRequest,request:Request):
    def action(s):
        old=s['idempotency'].get(body.idempotency_key)
        if old:
            if old['decision_id']!=body.decision_id: raise HTTPException(409,'Idempotency key belongs to another purchase request.')
            return s['purchases'][old['purchase_id']]['receipt']
        d=required(s,'decisions',body.decision_id)
        existing=next((p for p in s['purchases'].values() if p['receipt']['offer_hash']==d['offer_hash']),None)
        if existing: return existing['receipt']
        result,v=judge(s,d)
        failures=[c for c in result['checks'] if c['status']!='pass']
        accepted={}
        for e in d['exceptions']:
            try: payload=read_signed(e['signature'],'user','intent-judge-record+jwt')
            except ValueError: raise HTTPException(409,'Exception signature did not verify.')
            if payload!={k:v for k,v in e.items() if k!='signature'} or e['offer_hash']!=d['offer_hash'] or e['approved_digest']!=d['approved_digest'] or e['profile_digest']!=d['approved']['profile_digest']: raise HTTPException(409,'Exception binding changed.')
            accepted[e['check_id']]=e
        unaccepted=[c for c in failures if not c['exception_allowed'] or c['check_id'] not in accepted or accepted[c['check_id']]['accepted_value']!=c['offer_value'] or accepted[c['check_id']]['accepted_status']!=c['status']]
        if result['status']=='BLOCK' or unaccepted:
            raise HTTPException(409,{'message':'Purchase held. Every difference needs specific consent; integrity and unsupported conditions cannot be waived.','status':result['status'],'checks':unaccepted})
        receipt={'id':uid(),'decision_id':d['id'],'offer_id':d['offer_id'],'offer_hash':d['offer_hash'],'approved_digest':d['approved_digest'],'total_cents':v['facts']['total_cents'],'currency':v['facts']['currency'],'mode':'simulated','outcome':'confirmed','timestamp':now(),'exceptions_count':len(d['exceptions'])}
        event(s,'simulated_purchase',receipt)
        evidence=make_evidence(receipt,required(s,'drafts',d['intent_id']),d,s['events'])
        s['purchases'][receipt['id']]={'receipt':receipt,'evidence':evidence}
        s['idempotency'][body.idempotency_key]={'decision_id':d['id'],'purchase_id':receipt['id']}
        return receipt
    return get_store().mutate(session_id(request),action)

@app.get('/api/purchases/{id}/evidence')
def evidence(id:str,request:Request):
    return required(get_store().read(session_id(request)),'purchases',id)['evidence']

@app.post('/api/disputes')
def dispute(body:DisputeRequest,request:Request):
    def action(s):
        p=required(s,'purchases',body.purchase_id)
        record={'id':uid(),'purchase_id':body.purchase_id,'reason':body.reason,'timestamp':now(),'recommendation':'An analyst should compare the original request, approved constraints, verified merchant offer, and recorded exceptions.','final_decision':'dispute analyst','evidence_digest':p['evidence']['digest']}
        event(s,'dispute_requested',record)
        return record
    return get_store().mutate(session_id(request),action)

@app.get('/')
def index(): return FileResponse(ROOT/'web'/'index.html')
app.mount('/web',StaticFiles(directory=ROOT/'web'),name='web')
