"""Exercise adaptive interpretation through real approval and purchase gates."""
from copy import deepcopy

from tests.test_enforcement import client


def proposal():
    return {
        'fields': {'max_total_cents': 30000},
        'sources': {'max_total_cents': 'up to $300'},
        'unsupported': [], 'clarifications': [],
        'explanation': 'Review the captured conditions.',
        'mode': 'live', 'model': 'test', 'pipeline': 'adaptive', 'trace': [],
        'criteria': [{'key': 'quiet', 'field': None, 'text': 'quiet',
                      'source_quote': 'quiet', 'kind': 'requirement',
                      'verification': 'unsupported'}],
        'adaptive_plan': {
            'action': 'ask_user', 'assistant_message': 'I need to understand quiet.',
            'question': {'criterion_key': 'quiet', 'field': None,
                         'question': 'What does quiet mean for this purchase?',
                         'why': 'A measurable condition would help evaluate an offer.',
                         'answer_kind': 'text', 'options': []},
        }, 'agent_tools': [],
    }


def test_generic_ai_question_reaches_ui_and_unknown_criterion_holds_purchase(client, monkeypatch):
    monkeypatch.setattr('app.foundry_client.extract', lambda *a, **k: proposal())
    response = client.post('/api/intents', json={
        'domain': 'general', 'mode': 'live', 'message': 'Find a quiet lamp for up to $300.'})
    assert response.status_code == 200, response.text
    draft = response.json()
    assert draft['questions'][0]['question'] == 'What does quiet mean for this purchase?'
    assert draft['questions'][0]['origin'] == 'ai'
    assert draft['unsupported'] == ['quiet']
    fields = {'max_total_cents': 30000}
    path = f"/api/intents/{draft['id']}"
    assert client.post(path+'/answers', json={
        'revision': 1, 'fields': fields, 'unsupported': [], 'confirmation': True}).status_code == 409
    reviewed = client.post(path+'/answers', json={
        'revision': 1, 'fields': fields, 'unsupported': ['quiet'], 'confirmation': True}).json()
    authorized = client.post(path+'/approve', json={
        'revision': reviewed['revision'], 'digest': reviewed['digest'], 'confirmation': True})
    assert authorized.status_code == 200, authorized.text
    for offer in authorized.json()['offers']:
        decision = client.post('/api/check', json={'intent_id': draft['id'], 'offer_id': offer['id']}).json()
        assert decision['status'] == 'HOLD'
        assert client.post('/api/purchase', json={
            'decision_id': decision['id'], 'idempotency_key': 'generic-condition-hold'}).status_code == 409


def test_generic_answer_uses_stored_question_and_is_never_a_client_supplied_contract(client, monkeypatch):
    captured = []
    def extract(*args, **kwargs):
        captured.append(kwargs)
        return deepcopy(proposal())
    monkeypatch.setattr('app.foundry_client.extract', extract)
    draft = client.post('/api/intents', json={
        'domain': 'general', 'mode': 'live', 'message': 'Find a quiet lamp for up to $300.'}).json()
    path = f"/api/intents/{draft['id']}/clarify"
    bad = client.post(path, json={'revision': 1, 'message': 'Below 30 decibels.',
                                  'reply_to': {'field': 'max_total_cents'}})
    assert bad.status_code == 422
    result = client.post(path, json={'revision': 1, 'message': 'Below 30 decibels.'})
    assert result.status_code == 200, result.text
    assert captured[-1]['source_messages'][-1]['reply_to']['question_id'] == draft['questions'][0]['question_id']
    assert 'What does quiet mean' not in captured[-1]['source_text']
    assert result.json()['unsupported'] == ['quiet']


def test_customer_review_can_recover_a_condition_both_model_roles_omitted(client, monkeypatch):
    """Source grounding is not proof of complete extraction; review can repair it."""
    omitted = proposal()
    omitted['criteria'] = []
    omitted['adaptive_plan'] = {'action': 'ready_for_review', 'question': None,
                                'assistant_message': 'Please compare this draft with your request.'}
    monkeypatch.setattr('app.foundry_client.extract', lambda *a, **k: deepcopy(omitted))
    draft = client.post('/api/intents', json={
        'domain': 'general', 'mode': 'live', 'message': 'Find a quiet lamp for up to $300.'}).json()
    assert 'quiet' in draft['message']
    path = f"/api/intents/{draft['id']}"
    reviewed = client.post(path+'/answers', json={
        'revision': 1, 'fields': {'max_total_cents': 30000},
        'unsupported': ['quiet'], 'confirmation': True}).json()
    authorized = client.post(path+'/approve', json={
        'revision': reviewed['revision'], 'digest': reviewed['digest'], 'confirmation': True}).json()
    decision = client.post('/api/check', json={
        'intent_id': draft['id'], 'offer_id': authorized['offers'][0]['id']}).json()
    assert decision['status'] == 'HOLD'
    assert any(check['check_id'].startswith('unsupported_') for check in decision['checks'])
    assert client.post('/api/purchase', json={
        'decision_id': decision['id'], 'idempotency_key': 'recovered-customer-criterion'}).status_code == 409
