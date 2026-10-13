"""Transactional synthetic session state: SQLite locally, Table ETags on Vercel."""
import json
import os
import sqlite3
import time
import zlib
import hashlib
import logging
from functools import lru_cache
from app.ai_errors import AIServiceError


def encode_entity(key,state):
    """Keep atomic session writes below Azure's 1 MiB entity and 64 KiB property caps."""
    raw=json.dumps(state,separators=(',',':'),ensure_ascii=True).encode('ascii')
    if len(raw)>4000000: raise ValueError('Session capacity reached; start a fresh demo session.')
    packed=zlib.compress(raw,level=6)
    if len(packed)>900000: raise ValueError('Session capacity reached; start a fresh demo session.')
    entity={'PartitionKey':'intent-judge-v1','RowKey':key,'encoding':'zlib-json-v1'}
    entity.update({f'blob_{i//60000:03d}':packed[i:i+60000] for i in range(0,len(packed),60000)})
    return entity


def decode_entity(entity):
    if entity.get('encoding')=='zlib-json-v1':
        packed=b''.join(entity[k] for k in sorted(entity) if k.startswith('blob_'))
        return json.loads(zlib.decompress(packed))
    # Existing preview sessions migrate on their next conditional write.
    return json.loads(''.join(entity[k] for k in sorted(entity) if k.startswith('data_')))

class SQLiteStore:
    def __init__(self,path):
        self.path=path
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
    def connect(self):
        return sqlite3.connect(self.path,timeout=15,isolation_level=None)
    def mutate(self,key,fn):
        db=self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT data FROM records WHERE id=?',(key,)).fetchone()
            state=json.loads(row[0]) if row else {}
            result=fn(state)
            db.execute('INSERT INTO records(id,data) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',(key,json.dumps(state,separators=(',',':'))))
            db.commit()
            return result
        except Exception:
            db.rollback();raise
        finally: db.close()
    def read(self,key):
        with self.connect() as db:
            row=db.execute('SELECT data FROM records WHERE id=?',(key,)).fetchone()
            return json.loads(row[0]) if row else {}

class AzureTableStore:
    def __init__(self):
        from azure.data.tables import TableServiceClient
        self.table=TableServiceClient.from_connection_string(os.environ['AZURE_TABLE_CONNECTION_STRING']).create_table_if_not_exists(os.getenv('AZURE_TABLE_NAME','IntentJudge'))
    def _read(self,key):
        from azure.core.exceptions import ResourceNotFoundError
        try:
            e=self.table.get_entity('intent-judge-v1',key)
            return decode_entity(e),e.metadata['etag']
        except ResourceNotFoundError: return {},None
    def read(self,key): return self._read(key)[0]
    def mutate(self,key,fn):
        from azure.core import MatchConditions
        from azure.core.exceptions import ResourceExistsError, ResourceModifiedError
        from azure.data.tables import UpdateMode
        for _ in range(12):
            state,etag=self._read(key)
            result=fn(state)
            e=encode_entity(key,state)
            try:
                if etag:
                    self.table.update_entity(e,mode=UpdateMode.REPLACE,etag=etag,match_condition=MatchConditions.IfNotModified)
                else: self.table.create_entity(e)
                return result
            except (ResourceExistsError,ResourceModifiedError): continue
        raise RuntimeError('Concurrent update; please retry.')

@lru_cache
def get_store():
    if os.getenv('STORE_BACKEND')=='azure': return AzureTableStore()
    if os.getenv('VERCEL'): raise RuntimeError('Vercel requires durable Azure state')
    return SQLiteStore(os.getenv('SQLITE_PATH','.intent-judge.sqlite3'))


def _session_budget_key(session):
    return hashlib.sha256(session.encode()).hexdigest()


def _limits():
    # Daily capacity can be tuned without expanding the student's lifetime allowance.
    return {'lifetime': min(200, int(os.getenv('AI_CALL_LIMIT', '200'))),
            'interactive': int(os.getenv('AI_DAILY_LIMIT', '80')),
            'evaluation': int(os.getenv('AI_EVAL_DAILY_LIMIT', '100')),
            'monitor': 2, 'session': int(os.getenv('AI_SESSION_LIMIT', '16'))}


def reserve_ai_calls(session, count, purpose='interactive'):
    """Reserve the whole pipeline in one authoritative ledger transaction.

    Session counters are a UI projection. Keeping their authority in this same
    ledger prevents rejected global reservations and concurrent calls diverging.
    A failed provider call still retains its conservative reservation.
    """
    if purpose not in {'interactive', 'evaluation', 'monitor'}:
        raise ValueError('Unknown AI call purpose')
    if type(count) is not int or not 1 <= count <= 3:
        raise ValueError('Invalid model call count')
    store = get_store()
    timestamp = time.time()
    day = time.strftime('%Y-%m-%d', time.gmtime(timestamp))
    reset = 86400 - int(timestamp) % 86400
    limits = _limits()
    session_key = _session_budget_key(session)
    legacy_session_count = store.read(session).get('ai_calls', 0) if purpose == 'interactive' else 0

    def reserve(state):
        if state.get('calls', 0) + count > limits['lifetime']:
            raise AIServiceError('ai_budget_limit', 'The demo AI spending allowance is reached. Live AI is paused to protect the remaining credit. You can still use the tutorial or explicitly choose offline mode.')
        if state.get('day') != day:
            state['day'] = day
            for key in ('daily_calls', 'daily_eval_calls', 'daily_monitor_calls'):
                state[key] = 0
        daily_key = {'interactive': 'daily_calls', 'evaluation': 'daily_eval_calls', 'monitor': 'daily_monitor_calls'}[purpose]
        if state.get(daily_key, 0) + count > limits[purpose]:
            raise AIServiceError('ai_daily_limit', f'Today’s {purpose} AI allowance is reached. Live interpretation resumes at midnight UTC. Your request is kept; the tutorial and explicit offline mode are still available.', status_code=429, retry_after_seconds=reset)
        session_counts = state.setdefault('session_reservations', {})
        session_count = session_counts.get(session_key, legacy_session_count)
        if purpose == 'interactive' and session_count + count > limits['session']:
            raise AIServiceError('ai_session_limit', 'This demo session has reached its AI call allowance. You can keep reviewing the current draft, or start a new request session.', status_code=429)
        if purpose == 'monitor' and state.get('monitor_calls', 0) + count > int(os.getenv('AI_MONITOR_CALL_LIMIT', '40')):
            raise AIServiceError('ai_monitor_limit', 'The live monitor allowance is reached; review the budget before extending it.')
        state['calls'] = state.get('calls', 0) + count
        state[daily_key] = state.get(daily_key, 0) + count
        if purpose == 'interactive':
            session_counts[session_key] = session_count + count
        else:
            state[purpose + '_calls'] = state.get(purpose + '_calls', 0) + count
        state['reserved_usd'] = round(state['calls'] * float(os.getenv('AI_RESERVATION_USD', '0.10')), 2)
        state.setdefault('usage', {'prompt_tokens': 0, 'completion_tokens': 0})
        return state['calls'], session_count + count

    reservation, session_count = store.mutate('global-ai-budget', reserve)
    if purpose == 'interactive':
        try:
            store.mutate(session, lambda state: state.update(ai_calls=max(state.get('ai_calls', 0), session_count)))
        except Exception:
            logging.getLogger(__name__).warning('AI session usage projection unavailable; authoritative reservation retained')
    return reservation


def reserve_ai_call(session, purpose='interactive'):
    return reserve_ai_calls(session, 1, purpose)


def ai_capacity(session):
    """Read availability without inference, reservations, or exposing other sessions."""
    state = get_store().read('global-ai-budget')
    limits = _limits()
    timestamp = time.time()
    same_day = state.get('day') == time.strftime('%Y-%m-%d', time.gmtime(timestamp))
    daily_remaining = max(0, limits['interactive'] - (state.get('daily_calls', 0) if same_day else 0))
    lifetime_remaining = max(0, limits['lifetime'] - state.get('calls', 0))
    session_count = state.get('session_reservations', {}).get(_session_budget_key(session), get_store().read(session).get('ai_calls', 0))
    session_remaining = max(0, limits['session'] - session_count)
    return {'remaining_calls': min(daily_remaining, lifetime_remaining),
            'session_remaining_calls': session_remaining,
            'lifetime_remaining_calls': lifetime_remaining,
            'daily_remaining_calls': daily_remaining,
            'reset_after_seconds': 86400 - int(timestamp) % 86400}


def record_usage(usage):
    def add(s):
        u=s.setdefault('usage',{'prompt_tokens':0,'completion_tokens':0})
        for k in u: u[k]+=int(usage.get(k,0) or 0)
    get_store().mutate('global-ai-budget',add)


def record_ai_outcome(stage, outcome, request_id=None):
    """Store bounded operational evidence, never prompts or provider payloads."""
    if stage not in {'preflight','extract','coverage_audit','explain'}:
        return
    if outcome not in {'passed','ai_configuration','ai_provider','ai_timeout','ai_interpretation',
                       'ai_daily_limit','ai_session_limit','ai_budget_limit','ai_disabled'}:
        return
    def add(state):
        counts=state.setdefault('counts',{})
        key=stage+':'+outcome
        counts[key]=counts.get(key,0)+1
        state['updated_at']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
        if outcome!='passed':
            state['last_failure']={'stage':stage,'code':outcome,'request_id':request_id,'timestamp':state['updated_at']}
    try:
        get_store().mutate('ai-runtime',add)
    except Exception:
        logging.getLogger(__name__).warning('AI operational counter unavailable')
