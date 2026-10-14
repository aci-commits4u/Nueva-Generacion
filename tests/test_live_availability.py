"""Availability failures are actionable and cannot spend a rejected allowance."""
from concurrent.futures import ThreadPoolExecutor
import pytest
from app.ai_errors import AIServiceError
from app.store import get_store


@pytest.fixture
def budget(monkeypatch, tmp_path):
    monkeypatch.setenv('STORE_BACKEND', 'sqlite')
    monkeypatch.setenv('SQLITE_PATH', str(tmp_path / 'availability.sqlite3'))
    monkeypatch.setenv('AI_CALL_LIMIT', '20')
    monkeypatch.setenv('AI_DAILY_LIMIT', '10')
    monkeypatch.setenv('AI_SESSION_LIMIT', '8')
    monkeypatch.setenv('AI_EVAL_DAILY_LIMIT', '6')
    monkeypatch.delenv('AI_EMERGENCY_BUDGET_CENTS', raising=False)
    get_store.cache_clear()
    yield get_store()
    get_store.cache_clear()


def test_rejected_global_allowance_does_not_charge_session(budget, monkeypatch):
    from app.store import reserve_ai_call
    monkeypatch.setenv('AI_DAILY_LIMIT', '0')
    with pytest.raises(AIServiceError) as exc:
        reserve_ai_call('traveler')
    assert exc.value.code == 'ai_daily_limit'
    assert not exc.value.retryable
    assert budget.read('traveler').get('ai_calls', 0) == 0
    assert budget.read('global-ai-budget').get('calls', 0) == 0


def test_two_stage_reservation_rejects_before_any_provider_slot(budget, monkeypatch):
    from app.store import reserve_ai_calls
    monkeypatch.setenv('AI_DAILY_LIMIT', '1')
    with pytest.raises(AIServiceError):
        reserve_ai_calls('traveler', 2)
    assert budget.read('global-ai-budget').get('calls', 0) == 0


def test_concurrent_interpretations_never_overspend(budget, monkeypatch):
    from app.store import reserve_ai_calls
    monkeypatch.setenv('AI_CALL_LIMIT', '6')
    def reserve(i):
        try:
            reserve_ai_calls(f'traveler-{i}', 2)
            return True
        except AIServiceError:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(reserve, range(8)))
    assert sum(results) == 3
    assert budget.read('global-ai-budget')['calls'] == 6
    assert sum(budget.read(f'traveler-{i}').get('ai_calls', 0) for i in range(8)) == 6


def test_rejected_session_allowance_leaves_global_unchanged(budget, monkeypatch):
    from app.store import reserve_ai_calls
    monkeypatch.setenv('AI_SESSION_LIMIT', '2')
    reserve_ai_calls('traveler', 2)
    # A stale UI/session projection cannot bypass the authoritative ledger.
    budget.mutate('traveler', lambda s: s.update(ai_calls=0))
    with pytest.raises(AIServiceError) as exc:
        reserve_ai_calls('traveler', 2)
    assert exc.value.code == 'ai_session_limit'
    assert budget.read('global-ai-budget')['calls'] == 2


def test_evaluation_batch_preserves_interactive_quota(budget):
    from app.store import reserve_ai_calls
    reserve_ai_calls('evaluation', 2, purpose='evaluation')
    assert budget.read('global-ai-budget')['daily_calls'] == 0
    assert budget.read('global-ai-budget')['daily_eval_calls'] == 2


def test_existing_lifetime_reservations_are_not_reset(budget, monkeypatch):
    from app.store import reserve_ai_calls
    monkeypatch.setenv('AI_CALL_LIMIT', '104')
    budget.mutate('global-ai-budget', lambda s: s.update(calls=103, reserved_usd=10.3))
    with pytest.raises(AIServiceError) as exc:
        reserve_ai_calls('traveler', 2)
    assert exc.value.code == 'ai_budget_limit'
    assert budget.read('global-ai-budget')['calls'] == 103


def test_future_rate_is_additive_to_legacy_reservations(budget, monkeypatch):
    """Changing the configured rate must not reprice historical calls."""
    from app.store import reserve_ai_calls
    monkeypatch.setenv('AI_RESERVATION_USD', '0.02')
    monkeypatch.setenv('AI_CALL_LIMIT', '500')
    budget.mutate('global-ai-budget', lambda s: s.update(calls=178, reserved_usd=17.80))
    reserve_ai_calls('evaluation', 2, purpose='evaluation')
    ledger = budget.read('global-ai-budget')
    assert ledger['reserved_cents'] == 1784
    assert ledger['reserved_usd'] == 17.84


def test_rolling_workers_preserve_the_larger_legacy_money_representation(budget, monkeypatch):
    """An old worker may update dollars while a new cents field is stale."""
    from app.store import reserve_ai_calls
    monkeypatch.setenv('AI_RESERVATION_USD', '0.02')
    monkeypatch.setenv('AI_CALL_LIMIT', '500')
    budget.mutate('global-ai-budget', lambda s: s.update(calls=100, reserved_usd=10.00, reserved_cents=100))
    reserve_ai_calls('evaluation', 1, purpose='evaluation')
    ledger = budget.read('global-ai-budget')
    assert ledger['reserved_cents'] == 1002
    assert ledger['reserved_usd'] == 10.02


def test_concurrent_money_reservations_never_cross_twenty_dollars(budget, monkeypatch):
    from app.store import reserve_ai_calls
    monkeypatch.setenv('AI_RESERVATION_USD', '0.02')
    budget.mutate('global-ai-budget', lambda s: s.update(reserved_cents=1998, reserved_usd=19.98))

    def reserve(i):
        try:
            reserve_ai_calls(f'money-traveler-{i}', 1)
            return True
        except AIServiceError as exc:
            assert exc.code == 'ai_budget_limit'
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(reserve, range(8)))
    assert sum(results) == 1
    ledger = budget.read('global-ai-budget')
    assert ledger['reserved_cents'] == 2000
    assert ledger['calls'] == 1


def test_rejected_money_allowance_does_not_charge_session(budget, monkeypatch):
    from app.store import reserve_ai_calls
    monkeypatch.setenv('AI_RESERVATION_USD', '0.02')
    budget.mutate('global-ai-budget', lambda s: s.update(reserved_cents=1999, reserved_usd=19.99))
    with pytest.raises(AIServiceError) as exc:
        reserve_ai_calls('money-traveler', 1)
    assert exc.value.code == 'ai_budget_limit'
    assert budget.read('global-ai-budget').get('calls', 0) == 0
    assert budget.read('money-traveler').get('ai_calls', 0) == 0


def test_lower_future_rate_does_not_reset_past_usage(budget, monkeypatch):
    from app.store import reserve_ai_calls
    monkeypatch.setenv('AI_CALL_LIMIT', '500')
    budget.mutate('global-ai-budget', lambda s: s.update(calls=178, reserved_usd=17.80))
    monkeypatch.setenv('AI_RESERVATION_USD', '0.10')
    reserve_ai_calls('evaluation', 1, purpose='evaluation')
    monkeypatch.setenv('AI_RESERVATION_USD', '0.02')
    reserve_ai_calls('evaluation', 1, purpose='evaluation')
    assert budget.read('global-ai-budget')['reserved_cents'] == 1792


def test_capacity_is_limited_by_remaining_money(budget, monkeypatch):
    from app.store import ai_capacity
    monkeypatch.setenv('AI_RESERVATION_USD', '0.02')
    budget.mutate('global-ai-budget', lambda s: s.update(calls=10, reserved_cents=1996, reserved_usd=19.96))
    capacity = ai_capacity('capacity-traveler')
    assert capacity['monetary_remaining_calls'] == 2
    assert capacity['lifetime_remaining_calls'] == 2
    assert capacity['remaining_calls'] == 2
    assert capacity['reserved_cents'] == 1996


def test_invalid_or_free_future_rate_fails_before_store_mutation(budget, monkeypatch):
    from app.store import reserve_ai_calls
    for raw in ('nan', 'inf', '-0.01', '0.01'):
        monkeypatch.setenv('AI_RESERVATION_USD', raw)
        with pytest.raises(AIServiceError) as exc:
            reserve_ai_calls('configuration-traveler', 1)
        assert exc.value.code == 'ai_configuration'
        assert budget.read('global-ai-budget').get('calls', 0) == 0


def test_malformed_money_ledger_grants_no_capacity(budget, monkeypatch):
    from app.store import ai_capacity, reserve_ai_calls
    monkeypatch.setenv('AI_RESERVATION_USD', '0.02')
    for invalid in ('not-an-amount', 'nan', True, -1, 0.5):
        budget.mutate('global-ai-budget', lambda s: s.update(reserved_cents=invalid, reserved_usd=1.0))
        assert ai_capacity('corrupt-ledger')['lifetime_remaining_calls'] == 0
        with pytest.raises(AIServiceError) as exc:
            reserve_ai_calls('corrupt-ledger', 1)
        assert exc.value.code == 'ai_budget_limit'
        assert budget.read('corrupt-ledger').get('ai_calls', 0) == 0


def test_emergency_allowance_is_explicit_and_transparent(budget, monkeypatch):
    """The ordinary cap stays separate; only an explicit $2 extension adds headroom."""
    from app.store import ai_capacity, reserve_ai_calls
    monkeypatch.setenv('AI_EMERGENCY_BUDGET_CENTS', '200')
    monkeypatch.setenv('AI_RESERVATION_USD', '0.02')
    monkeypatch.setenv('AI_CALL_LIMIT', '500')
    monkeypatch.setenv('AI_EVAL_DAILY_LIMIT', '500')
    budget.mutate('global-ai-budget', lambda s: s.update(calls=100, reserved_cents=2000, reserved_usd=20.00))

    capacity = ai_capacity('emergency-traveler')
    assert capacity['ordinary_allowance_cents'] == 2000
    assert capacity['emergency_allowance_cents'] == 200
    assert capacity['ordinary_used_cents'] == 2000
    assert capacity['emergency_used_cents'] == 0
    assert capacity['emergency_remaining_cents'] == 200
    assert capacity['total_allowance_cents'] == 2200
    assert capacity['monetary_remaining_calls'] == 100

    reserve_ai_calls('emergency-traveler', 2, purpose='evaluation')
    capacity = ai_capacity('emergency-traveler')
    assert capacity['reserved_cents'] == 2004
    assert capacity['ordinary_used_cents'] == 2000
    assert capacity['emergency_used_cents'] == 4
    assert capacity['emergency_remaining_cents'] == 196


def test_emergency_allowance_is_bounded_and_malformed_values_fail_closed(budget, monkeypatch):
    from app.store import ai_capacity, reserve_ai_calls
    monkeypatch.setenv('AI_RESERVATION_USD', '0.02')
    monkeypatch.setenv('AI_CALL_LIMIT', '500')
    monkeypatch.setenv('AI_EVAL_DAILY_LIMIT', '500')
    budget.mutate('global-ai-budget', lambda s: s.update(calls=100, reserved_cents=2000, reserved_usd=20.00))

    monkeypatch.setenv('AI_EMERGENCY_BUDGET_CENTS', '999999')
    bounded = ai_capacity('bounded-traveler')
    assert bounded['emergency_allowance_cents'] == 1000
    assert bounded['total_allowance_cents'] == 3000

    monkeypatch.setenv('AI_EMERGENCY_BUDGET_CENTS', 'not-a-number')
    closed = ai_capacity('malformed-emergency')
    assert closed['emergency_allowance_cents'] == 0
    assert closed['total_allowance_cents'] == 2000
    assert closed['monetary_remaining_calls'] == 0
    with pytest.raises(AIServiceError) as exc:
        reserve_ai_calls('malformed-emergency', 1, purpose='evaluation')
    assert exc.value.code == 'ai_budget_limit'


def test_emergency_cap_never_overspends_under_concurrency(budget, monkeypatch):
    from app.store import reserve_ai_calls
    monkeypatch.setenv('AI_EMERGENCY_BUDGET_CENTS', '200')
    monkeypatch.setenv('AI_RESERVATION_USD', '0.02')
    monkeypatch.setenv('AI_CALL_LIMIT', '500')
    monkeypatch.setenv('AI_EVAL_DAILY_LIMIT', '500')
    budget.mutate('global-ai-budget', lambda s: s.update(calls=100, reserved_cents=2000, reserved_usd=20.00))

    def reserve(i):
        try:
            reserve_ai_calls(f'emergency-{i}', 1, purpose='evaluation')
            return True
        except AIServiceError as exc:
            assert exc.code == 'ai_budget_limit'
            return False

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(reserve, range(120)))
    assert sum(results) == 100
    ledger = budget.read('global-ai-budget')
    assert ledger['reserved_cents'] == 2200
    assert ledger['calls'] == 200


@pytest.fixture
def client(budget, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setenv('MOCK_LLM', '0')
    monkeypatch.setenv('AZURE_OPENAI_ENDPOINT', 'https://synthetic.openai.azure.com/')
    monkeypatch.setenv('AZURE_OPENAI_API_KEY', 'synthetic-key')
    monkeypatch.setenv('AZURE_OPENAI_DEPLOYMENT', 'synthetic-model')
    with TestClient(app) as client:
        client.get('/api/session')
        yield client


def test_status_reveals_exhausted_daily_allowance_without_a_model_call(client, monkeypatch):
    monkeypatch.setenv('AI_DAILY_LIMIT', '0')
    response = client.get('/api/ai/status')
    assert response.status_code == 200
    assert response.json()['configured'] is True
    assert response.json()['available'] is False
    assert response.json()['reason']['code'] == 'ai_daily_limit'
    assert response.json()['remaining_interpretations'] == 0


def test_status_checks_endpoint_and_disabled_live_mode(client, monkeypatch):
    monkeypatch.delenv('AZURE_OPENAI_ENDPOINT')
    assert client.get('/api/health').json()['live_ai_configured'] is False
    assert client.get('/api/ai/status').json()['reason']['code'] == 'ai_configuration'
    monkeypatch.setenv('AZURE_OPENAI_ENDPOINT', 'https://synthetic.openai.azure.com/')
    monkeypatch.setenv('MOCK_LLM', '1')
    assert client.get('/api/ai/status').json()['reason']['code'] == 'ai_disabled'


def test_public_quota_error_keeps_actionable_type_and_no_provider_details(client, monkeypatch):
    def unavailable(*args, **kwargs):
        raise AIServiceError('ai_daily_limit', 'Live AI daily allowance is reached.', status_code=429, retry_after_seconds=300)
    monkeypatch.setattr('app.foundry_client.extract', unavailable)
    response = client.post('/api/intents', json={'domain': 'flight', 'message': 'Florida under $300', 'mode': 'live'})
    assert response.status_code == 429
    assert response.headers['retry-after'] == '300'
    assert response.json()['error']['code'] == 'ai_daily_limit'
    assert response.json()['error']['retryable'] is False
    assert response.json()['detail'] == 'Live AI daily allowance is reached.'
    assert client.get('/api/session').json()['intents'] == []


def test_clarification_allows_six_turns_with_explicit_remaining_count(client):
    draft = client.post('/api/intents', json={'domain': 'flight', 'message': 'nonstop under $300', 'mode': 'offline'}).json()
    assert draft['followups_remaining'] == 6
    for i in range(6):
        response = client.post(f"/api/intents/{draft['id']}/clarify", json={'revision': draft['revision'], 'message': f'EWR detail {i}'})
        assert response.status_code == 200
        draft = response.json()
        assert draft['followups_remaining'] == 5 - i
    response = client.post(f"/api/intents/{draft['id']}/clarify", json={'revision': draft['revision'], 'message': 'another detail'})
    assert response.status_code == 409


def test_customer_review_records_exact_clarification_resolution(client, monkeypatch, budget):
    def proposed(*args, **kwargs):
        return {'fields':{'max_total_cents':29999},'sources':{'max_total_cents':'under $300'},
                'unsupported':[],'clarifications':[{'field':'destination_airports','source_quote':'Florida','reason':'ambiguous'},
                                                    {'field':'nonstop','source_quote':'preferably nonstop','reason':'preference'}],
                'explanation':'Choose the arrival airport and whether nonstop is required.','mode':'live','model':'synthetic','trace':[]}
    monkeypatch.setattr('app.foundry_client.extract',proposed)
    draft=client.post('/api/intents',json={'message':'Florida under $300, preferably nonstop','mode':'live'}).json()
    assert draft['clarifications'][0]['source_quote']=='Florida'
    assert draft['ai_runs'][0]['clarifications']==draft['clarifications']
    fields={key:None for key in client.get('/api/profiles/flight').json()['fields']}
    fields.update(max_total_cents=29999,origin_airports=['EWR'],destination_airports=['MCO'],departure_date='2026-11-12')
    response=client.post(f"/api/intents/{draft['id']}/answers",json={'revision':draft['revision'],'fields':fields,'unsupported':[],'confirmation':True})
    assert response.status_code==200
    assert response.json()['clarifications']==[]
    events=budget.read(client.cookies['ij_session'])['events']
    resolved=next(e for e in events if e['kind']=='clarifications_resolved_by_traveler')
    assert resolved['data']['choices'][0]['reviewed_value']==['MCO']
    assert resolved['data']['choices'][1]['reviewed_value'] is None
    assert resolved['data']['choices'][1]['meaning']=='explicit no preference'


def test_failed_clarification_preserves_prior_revision(client, monkeypatch):
    from tests.test_conversation import fake
    monkeypatch.setattr('app.foundry_client.extract',fake)
    draft=client.post('/api/intents',json={'message':'Nonstop under $300','mode':'live'}).json()
    def failed(*args,**kwargs):
        raise AIServiceError('ai_timeout','Live AI timed out. Your draft is preserved.',retryable=True)
    monkeypatch.setattr('app.foundry_client.extract',failed)
    response=client.post(f"/api/intents/{draft['id']}/clarify",json={'revision':draft['revision'],'message':'From Newark please'})
    assert response.status_code==503 and response.json()['error']['code']=='ai_timeout'
    saved=client.get(f"/api/intents/{draft['id']}").json()
    assert saved['revision']==draft['revision'] and len(saved['messages'])==1


def test_broad_geography_cannot_be_approved_as_an_airport(client):
    draft=client.post('/api/intents',json={'message':'nonstop under $300','mode':'offline'}).json()
    fields={key:None for key in client.get('/api/profiles/flight').json()['fields']}
    fields.update(max_total_cents=29999,origin_airports=['EWR'],destination_airports=['Florida'],departure_date='2026-11-12')
    response=client.post(f"/api/intents/{draft['id']}/answers",json={'revision':draft['revision'],'fields':fields,'unsupported':[],'confirmation':True})
    assert response.status_code==422
    saved=client.get(f"/api/intents/{draft['id']}").json()
    assert not saved['reviewed'] and not saved.get('approved')


def test_simultaneous_clarifications_call_provider_once(client,monkeypatch):
    from threading import Event
    from tests.test_conversation import fake
    monkeypatch.setattr('app.foundry_client.extract',fake)
    draft=client.post('/api/intents',json={'message':'Nonstop under $300','mode':'live'}).json()
    entered,release=Event(),Event()
    calls=[]
    def delayed(*args,**kwargs):
        calls.append(True);entered.set()
        assert release.wait(5)
        return fake(*args,**kwargs)
    monkeypatch.setattr('app.foundry_client.extract',delayed)
    path=f"/api/intents/{draft['id']}/clarify"
    body={'revision':draft['revision'],'message':'Depart from EWR'}
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(client.post,path,json=body)
        assert entered.wait(5)
        second=client.post(path,json=body)
        release.set()
        assert first.result().status_code==200
    assert second.status_code==409 and len(calls)==1


def test_failed_interpretation_releases_session_slot(client,monkeypatch,budget):
    def failed(*args,**kwargs):raise AIServiceError('ai_provider','Live AI unavailable.')
    monkeypatch.setattr('app.foundry_client.extract',failed)
    assert client.post('/api/intents',json={'message':'Florida under $300','mode':'live'}).status_code==503
    assert '_ai_pending' not in budget.read(client.cookies['ij_session'])
    assert client.post('/api/intents',json={'message':'nonstop under $300','mode':'offline'}).status_code==200
