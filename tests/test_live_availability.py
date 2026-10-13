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
