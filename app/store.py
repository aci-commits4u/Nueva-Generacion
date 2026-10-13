"""Transactional synthetic session state: SQLite locally, Table ETags on Vercel."""
import json
import os
import sqlite3
import time
import zlib
from functools import lru_cache


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


def reserve_ai_call(session):
    store=get_store(); now=time.time();day=time.strftime('%Y-%m-%d',time.gmtime(now))
    def session_reserve(s):
        if s.get('ai_calls',0)>=int(os.getenv('AI_SESSION_LIMIT','8')):
            raise ValueError('This demo session has reached its AI call allowance.')
        s['ai_calls']=s.get('ai_calls',0)+1
    store.mutate(session,session_reserve)
    def global_reserve(s):
        if s.get('calls',0)>=int(os.getenv('AI_CALL_LIMIT','200')): raise ValueError('The demo AI spending allowance is reached. Live AI is paused; offline mode remains available explicitly.')
        if s.get('day')!=day: s['day']=day;s['daily_calls']=0
        if s.get('daily_calls',0)>=int(os.getenv('AI_DAILY_LIMIT','40')): raise ValueError('Today’s live AI demonstration allowance is reached.')
        s['calls']=s.get('calls',0)+1;s['daily_calls']=s.get('daily_calls',0)+1
        s['reserved_usd']=round(s['calls']*float(os.getenv('AI_RESERVATION_USD','0.10')),2)
        s.setdefault('usage',{'prompt_tokens':0,'completion_tokens':0})
        return s['calls']
    return store.mutate('global-ai-budget',global_reserve)


def record_usage(usage):
    def add(s):
        u=s.setdefault('usage',{'prompt_tokens':0,'completion_tokens':0})
        for k in u: u[k]+=int(usage.get(k,0) or 0)
    get_store().mutate('global-ai-budget',add)
