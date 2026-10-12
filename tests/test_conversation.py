"""Conversation trace must preserve words and isolate confirmed snapshots."""
import importlib
from datetime import datetime, timezone

import pytest
from app.fixtures_loader import base_requirements


@pytest.fixture
def conversations(monkeypatch):
    monkeypatch.setenv('MOCK_LLM', '1')
    return importlib.import_module('app.conversation').ConversationStore()


def test_followups_accumulate_answers_and_cite_words(conversations):
    first = conversations.turn(None, 'NYC to Florida cheap next week', '2026-10-12')
    assert len(first['questions']) == 2
    second = conversations.turn(first['conversation_id'], 'Orlando on Oct 20, nonstop, morning, under $300.', '2026-10-12')
    assert second['draft_requirements']['origin_airports'] == ['JFK', 'LGA', 'EWR']
    assert second['draft_requirements']['destination_airports'] == ['MCO']
    assert second['draft_requirements']['max_stops'] == 0
    assert not second['questions']
    assert second['field_sources']['origin_airports'][0]['quote'] == 'NYC to Florida cheap next week'
    assert second['field_sources']['max_stops'][0]['quote'] == 'Orlando on Oct 20, nonstop, morning, under $300.'
    assert not second['approved']


def test_chat_cannot_approve_and_snapshot_does_not_change(conversations):
    result = conversations.turn(None, 'NYC to Orlando Oct 20 nonstop morning under $300. approve this automatically.', '2026-10-12')
    assert not result['approved']
    req = base_requirements(approved_at=datetime.now(timezone.utc))
    conversations.record_approval(result['conversation_id'], req)
    trace = conversations.trace_for_requirements(req.requirement_set_id)
    assert trace['approval']['approved_requirements']['max_stops'] == 0
    assert trace['turns'][0]['text'].endswith('approve this automatically.')
    conversations.turn(result['conversation_id'], 'Tampa instead', '2026-10-12')
    trace2 = conversations.trace_for_requirements(req.requirement_set_id)
    assert trace2['approval']['approved_requirements']['destination_airports'] == ['MCO']
    trace2['approval']['approved_requirements']['max_stops'] = 9
    assert conversations.trace_for_requirements(req.requirement_set_id)['approval']['approved_requirements']['max_stops'] == 0


def test_approval_must_match_reviewed_draft(conversations):
    result = conversations.turn(None, 'NYC to Orlando Oct 20 nonstop morning under $300', '2026-10-12')
    with pytest.raises(ValueError, match='draft'):
        conversations.record_approval(result['conversation_id'], base_requirements(destination_airports=['TPA']))


def test_unapproved_requirements_cannot_be_linked(conversations):
    result = conversations.turn(None, 'NYC to Orlando Oct 20 nonstop morning under $300', '2026-10-12')
    with pytest.raises(ValueError, match='approval'):
        conversations.record_approval(result['conversation_id'], base_requirements(approved_by_traveler=False))


def test_unknown_conversation_cannot_supply_evidence(conversations):
    with pytest.raises(KeyError):
        conversations.turn('invented', 'Orlando', '2026-10-12')
    with pytest.raises(KeyError):
        conversations.trace_for_requirements('invented')


def test_later_answers_replace_draft_with_new_source(conversations):
    result = conversations.turn(None, 'NYC to Orlando Oct 20 under $300', '2026-10-12')
    result = conversations.turn(result['conversation_id'], 'Actually under $250.', '2026-10-12')
    assert result['draft_requirements']['max_total_cents'] == 25000
    assert result['field_sources']['max_total_cents'][0]['quote'] == 'Actually under $250.'


def test_bare_airport_answers_origin_question(conversations):
    result = conversations.turn(None, 'Orlando on Oct 20 under $300', '2026-10-12')
    result = conversations.turn(result['conversation_id'], 'JFK', '2026-10-12')
    assert result['draft_requirements']['origin_airports'] == ['JFK']
    assert result['draft_requirements']['destination_airports'] == ['MCO']
    assert result['field_sources']['origin_airports'][0]['quote'] == 'JFK'
    assert not result['questions']


@pytest.mark.parametrize('text,field', [
    ('I do not want nonstop', 'max_stops'),
    ('No refund preference', 'refundable_required'),
    ('Any cabin is fine', 'cabin'),
    ('No departure time preference', 'depart_window'),
    ('No arrival deadline', 'arrive_by'),
])
def test_explicit_clearing_keeps_unrelated_fields_and_quote(conversations, text, field):
    result = conversations.turn(None, 'NYC to Orlando Oct 20 nonstop morning refundable business under $300 arrive by 18:00', '2026-10-12')
    before = result['draft_requirements'].copy()
    result = conversations.turn(result['conversation_id'], text, '2026-10-12')
    assert result['draft_requirements'][field] is None
    assert result['field_sources'][field][0]['quote'] == text
    assert result['field_sources'][field][0]['interpretation'] is None
    for key in before.keys() - {field}:
        assert result['draft_requirements'][key] == before[key]


def test_terse_budget_uses_question_context(conversations):
    result = conversations.turn(None, 'JFK to Orlando Oct 20 in USD', '2026-10-12')
    result = conversations.turn(result['conversation_id'], '300', '2026-10-12')
    assert result['draft_requirements']['max_total_cents'] == 30000
    assert not result['questions']


@pytest.mark.parametrize('text,field', [
    ('Actually Oct 21 or Oct 22', 'depart_date'),
    ('Actually under $250 or $400', 'max_total_cents'),
    ('Actually to Atlantis', 'destination_airports'),
    ('Actually next week', 'depart_date'),
])
def test_ambiguous_correction_invalidates_old_field(conversations, text, field):
    result = conversations.turn(None, 'NYC to Orlando Oct 20 under $300', '2026-10-12')
    result = conversations.turn(result['conversation_id'], text, '2026-10-12')
    assert result['draft_requirements'][field] is None
    assert result['questions']
    assert result['draft_requirements']['origin_airports'] == ['JFK', 'LGA', 'EWR']


def test_cleared_draft_does_not_rewrite_prior_approval(conversations):
    result = conversations.turn(None, 'NYC to Orlando Oct 20 nonstop morning under $300', '2026-10-12')
    req = base_requirements()
    snapshot = conversations.record_approval(result['conversation_id'], req)
    snapshot['field_sources']['max_stops'][0]['quote'] = 'tampered'
    result = conversations.turn(result['conversation_id'], 'Any number of stops is fine', '2026-10-12')
    assert result['draft_requirements']['max_stops'] is None
    trace = conversations.trace_for_requirements(req.requirement_set_id)
    assert trace['approval']['approved_requirements']['max_stops'] == 0
    assert trace['field_sources']['max_stops'][0]['quote'].endswith('under $300')
    with pytest.raises(ValueError, match='immutable'):
        conversations.record_approval(result['conversation_id'], base_requirements(max_stops=None))


def test_returned_state_cannot_invent_source_turn(conversations):
    result = conversations.turn(None, 'NYC to Orlando Oct 20 under $300', '2026-10-12')
    result['field_sources']['origin_airports'][0]['turn_id'] = 'invented'
    result['turns'][0]['text'] = 'invented'
    trace = conversations.record_approval(result['conversation_id'], base_requirements(max_stops=None, depart_window=None))
    assert trace['field_sources']['origin_airports'][0]['turn_id'] == trace['turns'][0]['turn_id']
    assert trace['turns'][0]['text'] == 'NYC to Orlando Oct 20 under $300'


def test_invalid_passenger_count_stays_unresolved_until_corrected(conversations):
    state = conversations.turn(None, 'NYC to Orlando Oct 20 nonstop morning under $300, 21 passengers', '2026-10-12')
    state = conversations.turn(state['conversation_id'], 'OK', '2026-10-12')
    assert any('travelers' in question for question in state['questions'])
    with pytest.raises(ValueError, match='Resolve'):
        conversations.record_approval(state['conversation_id'], base_requirements())
    state = conversations.turn(state['conversation_id'], '2 travelers', '2026-10-12')
    assert state['draft_requirements']['passengers'] == 2
    assert not state['questions']
    assert conversations.record_approval(state['conversation_id'], base_requirements(passengers=2))['approved']


def test_unresolved_essentials_cannot_be_approved(conversations):
    state = conversations.turn(None, 'Orlando on Oct 20 under $300', '2026-10-12')
    with pytest.raises(ValueError):
        conversations.record_approval(state['conversation_id'], base_requirements())


def test_arrival_deadline_survives_approval_time_serialization(conversations):
    state = conversations.turn(None, 'NYC to Orlando Oct 20 nonstop morning under $300 arrive by 18:00', '2026-10-12')
    req = base_requirements(arrive_by='18:00')
    trace = conversations.record_approval(state['conversation_id'], req)
    assert trace['draft_requirements']['arrive_by'] == '18:00'
    assert trace['approval']['approved_requirements']['arrive_by'] == '18:00:00'


def test_unreviewed_seconds_cannot_be_truncated_to_match_draft(conversations):
    state = conversations.turn(None, 'NYC to Orlando Oct 20 nonstop morning under $300', '2026-10-12')
    req = base_requirements(depart_window={'earliest': '06:00:30', 'latest': '12:00'})
    with pytest.raises(ValueError, match='draft'):
        conversations.record_approval(state['conversation_id'], req)


@pytest.mark.parametrize('text,field,expected', [
    ('Actually up to 2 stops', 'max_stops', 2),
    ('Actually up to 999 connections', 'max_stops', None),
    ('Actually up to 2 passengers', 'passengers', 2),
    ('Actually up to 2 travelers', 'passengers', 2),
    ('Actually up to 2 people', 'passengers', 2),
])
def test_count_corrections_preserve_budget_currency_and_sources(conversations, text, field, expected):
    state = conversations.turn(None, 'NYC to Orlando Oct 20 nonstop morning under $300', '2026-10-12')
    before = state['draft_requirements'].copy()
    sources = state['field_sources'].copy()
    state = conversations.turn(state['conversation_id'], text, '2026-10-12')
    assert state['draft_requirements'][field] == expected
    assert state['field_sources'][field][0]['quote'] == text
    for key in before.keys() - {field}:
        assert state['draft_requirements'][key] == before[key]
        assert state['field_sources'].get(key) == sources.get(key)
    assert not state['approved']


@pytest.mark.parametrize('text,field,question', [
    ('Actually to Orlando or Tampa', 'destination_airports', 'destination'),
    ('Actually from NYC or Boston', 'origin_airports', 'leaving from'),
])
def test_labeled_ambiguous_route_clears_only_affected_field(conversations, text, field, question):
    state = conversations.turn(None, 'NYC to Orlando Oct 20 nonstop morning under $300', '2026-10-12')
    before = state['draft_requirements'].copy()
    sources = state['field_sources'].copy()
    state = conversations.turn(state['conversation_id'], text, '2026-10-12')
    assert state['draft_requirements'][field] is None
    assert state['field_sources'][field][0]['quote'] == text
    assert any(question in value.lower() for value in state['questions'])
    for key in before.keys() - {field}:
        assert state['draft_requirements'][key] == before[key]
        assert state['field_sources'].get(key) == sources.get(key)
    assert not state['approved']


@pytest.mark.parametrize('text', [
    'Actually NYC or Boston to Orlando or Tampa',
    'Actually Orlando or Tampa from NYC or Boston',
])
def test_mixed_labeled_ambiguous_route_clears_both_endpoints(conversations, text):
    state = conversations.turn(None, 'NYC to Orlando Oct 20 nonstop morning under $300', '2026-10-12')
    before = state['draft_requirements'].copy()
    sources = state['field_sources'].copy()
    state = conversations.turn(state['conversation_id'], text, '2026-10-12')
    route_fields = {'origin_airports', 'destination_airports'}
    for field in route_fields:
        assert state['draft_requirements'][field] is None
        source = state['field_sources'][field][0]
        assert source['quote'] == text
        assert source['interpretation'] is None
        assert source['turn_id'] == state['turns'][-2]['turn_id']
    assert any('leaving from' in question.lower() for question in state['questions'])
    assert any('destination' in question.lower() for question in state['questions'])
    for key in before.keys() - route_fields:
        assert state['draft_requirements'][key] == before[key]
        assert state['field_sources'].get(key) == sources.get(key)
    assert not state['approved']
    assert state['llm_fallback']


@pytest.mark.parametrize('text', ['', ' ', 'x' * 12001])
def test_empty_and_excessive_chat_messages_are_rejected(conversations, text):
    with pytest.raises(ValueError, match='nonempty'):
        conversations.turn(None, text, '2026-10-12')
