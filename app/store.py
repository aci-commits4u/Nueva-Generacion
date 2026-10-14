"""Transactional synthetic session state: SQLite locally, Table ETags on Vercel."""
import json
import os
import sqlite3
import time
import zlib
import hashlib
import logging
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from functools import lru_cache
from app.ai_errors import AIServiceError


# The money cap is intentionally independent from the model-call cap.  The
# latter is a safety valve for runaway retries; this immutable allowance is
# what keeps a change in per-call reservation price from spending the team's
# ordinary demo budget.
ORDINARY_AI_BUDGET_CENTS = 2_000
# The emergency allowance is deliberately opt-in.  It exists for an explicitly
# authorized validation/deployment window; an exhausted ordinary allowance must
# never silently unlock it.  Keep the code-side ceiling below the user's
# authorized emergency maximum so a bad deployment setting cannot expand spend.
EMERGENCY_AI_BUDGET_ENV = 'AI_EMERGENCY_BUDGET_CENTS'
MAX_EMERGENCY_AI_BUDGET_CENTS = 1_000
LEGACY_RESERVATION_CENTS = 10
MIN_RESERVATION_CENTS = 2


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
    return {'lifetime': max(0, min(500, int(os.getenv('AI_CALL_LIMIT', '500')))),
            'interactive': int(os.getenv('AI_DAILY_LIMIT', '80')),
            'evaluation': int(os.getenv('AI_EVAL_DAILY_LIMIT', '100')),
            'monitor': 2, 'session': int(os.getenv('AI_SESSION_LIMIT', '16'))}


def _reservation_rate_cents():
    """Return the configured future reservation cost, rounded up to cents.

    ``reserved_usd`` is a historical ledger field, so changing this setting
    must never recalculate what has already been reserved.  A minimum of two
    cents prevents a zero-cost configuration from making the call ceiling
    meaningless.  Invalid configuration fails before a store transaction.
    """
    raw = os.getenv('AI_RESERVATION_USD')
    if raw is None:
        raw = '0.10'
    try:
        amount = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        raise AIServiceError('ai_configuration', 'AI_RESERVATION_USD must be a finite non-negative amount.', stage='preflight')
    if not amount.is_finite() or amount < 0:
        raise AIServiceError('ai_configuration', 'AI_RESERVATION_USD must be a finite non-negative amount.', stage='preflight')
    if amount < Decimal('0.02'):
        raise AIServiceError('ai_configuration', 'AI_RESERVATION_USD must be at least $0.02 per reserved model call.', stage='preflight')
    cents = int((amount * 100).to_integral_value(rounding=ROUND_CEILING))
    return max(MIN_RESERVATION_CENTS, cents)


def _emergency_budget_cents():
    """Return the explicitly enabled emergency allowance in cents.

    The ordinary $20 allowance remains the default and is intentionally
    independent of this setting.  A malformed value fails closed to zero;
    positive values above the code-side ceiling are bounded rather than
    allowing an environment typo to expand the authorized spend.
    """
    raw = os.getenv(EMERGENCY_AI_BUDGET_ENV, '0')
    try:
        amount = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        return 0
    if (not amount.is_finite() or amount < 0 or
            amount != amount.to_integral_value()):
        return 0
    return min(MAX_EMERGENCY_AI_BUDGET_CENTS, int(amount))


def _total_ai_budget_cents():
    """Return the ordinary allowance plus the explicit emergency allowance."""
    return ORDINARY_AI_BUDGET_CENTS + _emergency_budget_cents()


def _reserved_cents(state):
    """Read the ledger without repricing historical reservations.

    ``reserved_cents`` is the exact representation written by this version.
    Older ledgers only have ``reserved_usd``; use its ceiling so fractional
    historical values cannot create unbudgeted headroom.  During rolling
    deploys an older worker can update ``reserved_usd`` while leaving the
    newer cents field stale, so both valid representations are honored and
    the larger value wins.  Very old records without either field are
    conservatively valued at the former $0.10/call.
    """
    parsed = []
    malformed = False
    if 'reserved_cents' in state:
        try:
            value = state['reserved_cents']
            if isinstance(value, bool):
                raise ValueError('boolean is not a ledger amount')
            amount = Decimal(str(value))
            if (not amount.is_finite() or amount < 0 or
                    amount != amount.to_integral_value()):
                raise ValueError('negative ledger amount')
            cents = int(amount)
            parsed.append(cents)
        except (InvalidOperation, TypeError, ValueError, OverflowError):
            malformed = True

    if 'reserved_usd' in state:
        try:
            value = state['reserved_usd']
            if isinstance(value, bool):
                raise ValueError('boolean is not a ledger amount')
            amount = Decimal(str(value))
            if not amount.is_finite() or amount < 0:
                raise ValueError('invalid ledger amount')
            parsed.append(int((amount * 100).to_integral_value(rounding=ROUND_CEILING)))
        except (InvalidOperation, ValueError, TypeError, OverflowError):
            malformed = True

    if malformed:
        # A corrupt amount must never create new spendable headroom.  Value it
        # at the complete currently configured cap so an explicitly enabled
        # emergency allowance cannot turn a corrupt ledger into capacity.
        return _total_ai_budget_cents()
    if parsed:
        return max(parsed)

    calls = state.get('calls', 0)
    try:
        calls = max(0, int(calls))
    except (TypeError, ValueError, OverflowError):
        calls = 0
    # A malformed positive ledger is safer when treated as fully spent than
    # when it silently grants new capacity.
    return calls * LEGACY_RESERVATION_CENTS


def _display_reserved_usd(cents):
    """Keep the legacy two-decimal field useful for existing dashboards."""
    return float(Decimal(cents) / Decimal(100))


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
    reservation_cents = _reservation_rate_cents()
    store = get_store()
    timestamp = time.time()
    day = time.strftime('%Y-%m-%d', time.gmtime(timestamp))
    reset = 86400 - int(timestamp) % 86400
    limits = _limits()
    session_key = _session_budget_key(session)
    legacy_session_count = store.read(session).get('ai_calls', 0) if purpose == 'interactive' else 0

    def reserve(state):
        current_reserved = _reserved_cents(state)
        proposed_reserved = current_reserved + (count * reservation_cents)
        if proposed_reserved > _total_ai_budget_cents():
            raise AIServiceError('ai_budget_limit', 'The configured AI spending allowance is reached. Live AI is paused to protect the remaining credit. You can still use the tutorial or explicitly choose offline mode.')
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
        # This is an additive reservation.  In particular, changing the
        # configured future rate never reprices already reserved calls.
        state['reserved_cents'] = proposed_reserved
        state['reserved_usd'] = _display_reserved_usd(proposed_reserved)
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
    reservation_cents = _reservation_rate_cents()
    timestamp = time.time()
    same_day = state.get('day') == time.strftime('%Y-%m-%d', time.gmtime(timestamp))
    daily_remaining = max(0, limits['interactive'] - (state.get('daily_calls', 0) if same_day else 0))
    call_lifetime_remaining = max(0, limits['lifetime'] - state.get('calls', 0))
    reserved_cents = _reserved_cents(state)
    emergency_allowance_cents = _emergency_budget_cents()
    ordinary_used_cents = min(ORDINARY_AI_BUDGET_CENTS, reserved_cents)
    emergency_used_cents = max(0, reserved_cents - ORDINARY_AI_BUDGET_CENTS)
    emergency_used_cents = min(emergency_allowance_cents, emergency_used_cents)
    ordinary_remaining_cents = max(0, ORDINARY_AI_BUDGET_CENTS - reserved_cents)
    emergency_remaining_cents = max(0, emergency_allowance_cents - emergency_used_cents)
    monetary_remaining = ordinary_remaining_cents + emergency_remaining_cents
    money_lifetime_remaining = monetary_remaining // reservation_cents
    # Keep the legacy lifetime key as the effective limit so callers that
    # gate on it cannot advertise capacity that the money ledger rejects.
    lifetime_remaining = min(call_lifetime_remaining, money_lifetime_remaining)
    session_count = state.get('session_reservations', {}).get(_session_budget_key(session), get_store().read(session).get('ai_calls', 0))
    session_remaining = max(0, limits['session'] - session_count)
    return {'remaining_calls': min(daily_remaining, lifetime_remaining),
            'session_remaining_calls': session_remaining,
            'lifetime_remaining_calls': lifetime_remaining,
            'daily_remaining_calls': daily_remaining,
            'call_lifetime_remaining_calls': call_lifetime_remaining,
            'monetary_remaining_calls': money_lifetime_remaining,
            'reserved_cents': reserved_cents,
            'reservation_cents': reservation_cents,
            'ordinary_allowance_cents': ORDINARY_AI_BUDGET_CENTS,
            'emergency_allowance_cents': emergency_allowance_cents,
            'ordinary_used_cents': ordinary_used_cents,
            'emergency_used_cents': emergency_used_cents,
            'ordinary_remaining_cents': ordinary_remaining_cents,
            'emergency_remaining_cents': emergency_remaining_cents,
            'total_allowance_cents': ORDINARY_AI_BUDGET_CENTS + emergency_allowance_cents,
            'emergency_enabled': emergency_allowance_cents > 0,
            'reset_after_seconds': 86400 - int(timestamp) % 86400}


def record_usage(usage):
    def add(s):
        u=s.setdefault('usage',{'prompt_tokens':0,'completion_tokens':0})
        for k in u: u[k]+=int(usage.get(k,0) or 0)
    get_store().mutate('global-ai-budget',add)


def record_ai_outcome(stage, outcome, request_id=None):
    """Store bounded operational evidence, never prompts or provider payloads."""
    if stage not in {'preflight','extract','coverage_audit','explain',
                     'adaptive_plan','adaptive_review','adaptive_latest_turn_coverage'}:
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
