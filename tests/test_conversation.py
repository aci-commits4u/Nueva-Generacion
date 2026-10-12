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
