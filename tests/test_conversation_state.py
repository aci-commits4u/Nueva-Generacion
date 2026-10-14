from copy import deepcopy
import time

import pytest
from pydantic import ValidationError

from app.conversation import merge_revision_state, merge_unsupported, questions
from app.models import IntentRequest
from app.store import get_store
from tests.test_enforcement import client


def _message(content, *, reply_to=None):
    message = {'role': 'user', 'content': content}
    if reply_to is not None:
        message['reply_to'] = reply_to
    return message


def _live_result():
    return {
        'fields': {'max_total_cents': 29999},
        'sources': {'max_total_cents': 'under $300'},
        'unsupported': [],
        'clarifications': [],
        'explanation': 'Review the captured requirements.',
        'mode': 'live',
        'model': 'test-model',
        'pipeline': 'audited',
        'trace': [],
    }


def _mark_stale(client, intent_id, *, profile_digest='previous-profile-digest'):
    sid=client.cookies['ij_session']
    get_store().mutate(sid,lambda state: state['drafts'][intent_id].update(profile_digest=profile_digest))


def test_questions_are_bounded_and_source_backed():
    planned = questions(
        'flight',
        {'nonstop': True},
        clarifications=[
            {'field': 'max_connections', 'source_quote': 'a few layovers', 'reason': 'ambiguous'},
            {'field': 'departure_window', 'source_quote': 'in the morning', 'reason': 'ambiguous'},
        ],
    )
    fields = {item['field'] for item in planned}

    assert fields == {
        'max_total_cents', 'origin_airports', 'destination_airports', 'departure_date',
        'departure_window',
    }
    assert 'max_connections' not in fields
    assert next(item for item in planned if item['field'] == 'departure_window')['response_type'] == 'time_range'


def test_required_clarification_does_not_duplicate_required_question():
    planned = questions(
        'flight', {},
        clarifications=[
            {'field': 'destination_airports', 'source_quote': 'Florida', 'reason': 'ambiguous'},
        ],
    )
    destination_questions = [item for item in planned if item['field'] == 'destination_airports']
    assert len(destination_questions) == 1
    assert destination_questions[0]['required'] is True


def test_multi_choice_question_contract_is_stable():
    first = questions('flight', {}, clarifications=[
        {'field': 'origin_airports', 'source_quote': 'Newark or JFK', 'reason': 'ambiguous'},
    ])
    second = questions('flight', {}, clarifications=[
        {'field': 'origin_airports', 'source_quote': 'Newark or JFK', 'reason': 'ambiguous'},
    ])
    left = next(item for item in first if item['field'] == 'origin_airports')
    right = next(item for item in second if item['field'] == 'origin_airports')

    assert left['response_type'] == 'multi'
    assert left['allow_multiple'] is True
    assert left['id'] == left['question_id'] == right['id']


def test_date_clarification_is_replaced_by_customer_grounded_range():
    current = {
        'fields': {
            'max_total_cents': 29999,
            'origin_airports': ['EWR'],
            'destination_airports': ['MCO'],
        },
        'sources': {
            'max_total_cents': 'under $300',
            'origin_airports': 'Newark',
            'destination_airports': 'Orlando',
        },
        'clarifications': [
            {'field': 'departure_date', 'source_quote': 'within the next week', 'reason': 'ambiguous'},
        ],
    }
    proposed = {
        'fields': {'departure_date': {'start': '2026-10-14', 'end': '2026-10-21'}},
        'sources': {'departure_date': 'Oct 14th through Oct 21st'},
        'clarifications': [],
    }

    merged = merge_revision_state(
        'flight', current, proposed, 'Oct 14th through Oct 21st',
        [_message('Book it within the next week'), _message('Oct 14th through Oct 21st')],
    )

    assert merged['fields']['departure_date'] == {'start': '2026-10-14', 'end': '2026-10-21'}
    assert not merged['clarifications']
    assert merged['fields']['origin_airports'] == ['EWR']


def test_old_value_cannot_overwrite_when_its_quote_is_not_in_latest_turn():
    current = {
        'fields': {'departure_date': '2026-10-14'},
        'sources': {'departure_date': 'Oct 14th'},
        'clarifications': [],
    }
    proposed = {
        'fields': {'departure_date': '2026-10-21'},
        'sources': {'departure_date': 'Oct 21st'},
        'clarifications': [],
    }

    merged = merge_revision_state(
        'flight', current, proposed, 'No preference on cabin.',
        [_message('Oct 14th'), _message('No preference on cabin.')],
    )

    assert merged['fields']['departure_date'] == '2026-10-14'
    assert merged['sources']['departure_date'] == 'Oct 14th'


def test_missed_original_criterion_can_be_rediscovered_on_later_turn():
    current = {'fields': {'max_total_cents': 29999},
               'sources': {'max_total_cents': 'under $300'},
               'clarifications': []}
    proposed = {
        'fields': {'cabin': 'economy'},
        'sources': {'cabin': 'Economy is fine'},
        'clarifications': [],
    }

    merged = merge_revision_state(
        'flight', current, proposed, 'Use November 7, 2026.',
        [_message('Economy is fine under $300.'), _message('Use November 7, 2026.')],
    )

    assert merged['fields']['cabin'] == 'economy'
    assert merged['sources']['cabin'] == 'Economy is fine'


def test_missed_original_criterion_does_not_resurrect_after_decline():
    current = {'fields': {'max_total_cents': 29999},
               'sources': {'max_total_cents': 'under $300'},
               'clarifications': []}
    proposed = {
        'fields': {'cabin': 'economy'},
        'sources': {'cabin': 'Economy is fine'},
        'clarifications': [],
    }

    merged = merge_revision_state(
        'flight', current, proposed, 'Use November 7, 2026.',
        [_message('Economy is fine under $300.'),
         _message("I don't require a cabin preference."),
         _message('Use November 7, 2026.')],
    )

    assert 'cabin' not in merged['fields']


def test_later_correction_is_retained_and_unrelated_state_survives():
    current = {
        'fields': {'max_total_cents': 29999, 'origin_airports': ['EWR']},
        'sources': {'max_total_cents': 'under $300', 'origin_airports': 'Newark'},
        'clarifications': [],
    }
    proposed = {
        'fields': {'max_total_cents': 35000},
        'sources': {'max_total_cents': 'up to $350'},
        'clarifications': [],
    }

    merged = merge_revision_state(
        'flight', current, proposed, 'Actually, up to $350 works.',
        [_message('under $300 from Newark'), _message('Actually, up to $350 works.')],
    )

    assert merged['fields']['max_total_cents'] == 35000
    assert merged['sources']['max_total_cents'] == 'up to $350'
    assert merged['fields']['origin_airports'] == ['EWR']


def test_latest_budget_clarification_reopens_existing_value_as_pending():
    current = {
        'fields': {'max_total_cents': 29999},
        'sources': {'max_total_cents': 'under $300'},
        'clarifications': [],
    }
    proposed = {
        'fields': {'max_total_cents': 29999},
        'sources': {'max_total_cents': 'under $300'},
        'clarifications': [
            {'field': 'max_total_cents', 'source_quote': 'budget flexible', 'reason': 'ambiguous'},
        ],
    }
    latest = 'Actually, budget flexible works.'

    merged = merge_revision_state(
        'flight', current, proposed, latest,
        [_message('Book a flight under $300.'), _message(latest)],
    )

    assert 'max_total_cents' not in merged['fields']
    assert 'max_total_cents' not in merged['sources']
    assert merged['clarifications'] == proposed['clarifications']
    change = merged['changes'][-1]
    assert change['kind'] == 'clarified'
    assert change['old_value'] == 29999
    assert change['old_source_quote'] == 'under $300'
    assert change['new_clarification']['source_quote'] == 'budget flexible'


def test_latest_airport_alternatives_reopen_existing_airport_value():
    current = {
        'fields': {'destination_airports': ['MCO']},
        'sources': {'destination_airports': 'Orlando'},
        'clarifications': [],
    }
    proposed = {
        'fields': {'destination_airports': ['MCO']},
        'sources': {'destination_airports': 'Orlando'},
        'clarifications': [
            {'field': 'destination_airports', 'source_quote': 'Orlando or Miami both fine', 'reason': 'ambiguous'},
        ],
    }
    latest = 'Orlando or Miami both fine.'

    merged = merge_revision_state(
        'flight', current, proposed, latest,
        [_message('Fly to Orlando.'), _message(latest)],
    )

    assert merged['fields'] == {}
    assert merged['sources'] == {}
    assert merged['clarifications'][0]['field'] == 'destination_airports'
    assert merged['changes'][-1]['old_value'] == ['MCO']


def test_historical_clarification_cannot_erase_newer_captured_airport():
    current = {
        'fields': {'destination_airports': ['MCO']},
        'sources': {'destination_airports': 'Orlando'},
        'clarifications': [
            {'field': 'destination_airports', 'source_quote': 'Florida', 'reason': 'ambiguous'},
        ],
    }
    proposed = {
        'fields': {'destination_airports': ['MCO']},
        'sources': {'destination_airports': 'Orlando'},
        'clarifications': [
            {'field': 'destination_airports', 'source_quote': 'Florida', 'reason': 'ambiguous'},
        ],
    }
    latest = 'Use the date I gave you.'

    merged = merge_revision_state(
        'flight', current, proposed, latest,
        [_message('Florida, then choose Orlando.'), _message(latest)],
    )

    assert merged['fields']['destination_airports'] == ['MCO']
    assert merged['sources']['destination_airports'] == 'Orlando'
    assert not merged['clarifications']
    assert not any(change['kind'] == 'clarified' for change in merged['changes'])


def test_unrelated_latest_clarification_cannot_reopen_price_with_airport_code():
    current = {
        'fields': {'max_total_cents': 29999},
        'sources': {'max_total_cents': 'under $300'},
        'clarifications': [],
    }
    proposed = {
        'fields': {'max_total_cents': 29999},
        'sources': {'max_total_cents': 'under $300'},
        'clarifications': [
            {'field': 'max_total_cents', 'source_quote': 'MIA', 'reason': 'ambiguous'},
        ],
    }
    latest = 'MIA is fine.'

    merged = merge_revision_state(
        'flight', current, proposed, latest,
        [_message('Book under $300.'), _message(latest)],
    )

    assert merged['fields']['max_total_cents'] == 29999
    assert merged['sources']['max_total_cents'] == 'under $300'
    assert not merged['clarifications']


def test_unknown_unsupported_conditions_are_never_deleted_by_omission():
    assert merge_unsupported(['round trip', 'two passengers'], []) == ['round trip', 'two passengers']
    assert merge_unsupported(['round trip'], ['two passengers']) == ['round trip', 'two passengers']


def test_explicit_latest_no_preference_clears_only_optional_field():
    current = {
        'fields': {'nonstop': True},
        'sources': {'nonstop': 'nonstop'},
        'clarifications': [],
    }

    merged = merge_revision_state(
        'flight', current, {'fields': {}, 'sources': {}, 'clarifications': []},
        "I don't require nonstop.",
        [_message('nonstop'), _message("I don't require nonstop.")],
    )

    assert 'nonstop' not in merged['fields']
    assert 'nonstop' not in merged['sources']
    assert any(item['kind'] == 'declined' for item in merged['changes'])


def test_intake_timezone_is_validated_and_preserves_iana_name():
    request = IntentRequest(message='Find a flight under $300', time_zone='America/New_York')
    assert request.time_zone == 'America/New_York'

    with pytest.raises(ValidationError):
        IntentRequest(message='Find a flight under $300', time_zone='Not/A_Timezone')


def test_profile_refresh_replays_all_customer_messages_and_records_clock_upgrade(client,monkeypatch):
    calls=[]

    def extraction(domain,message,session,**kwargs):
        calls.append((message,kwargs))
        return _live_result()

    monkeypatch.setattr('app.foundry_client.extract',extraction)
    draft=client.post('/api/intents',json={
        'mode':'live','message':'Nonstop under $300','time_zone':'UTC',
    }).json()
    sid=client.cookies['ij_session']
    old_messages=[
        {'role':'user','content':'Nonstop under $300','timestamp':'2026-10-14T00:15:00+00:00'},
        {'role':'user','content':'From EWR to MCO on 2026-11-12','timestamp':'2026-10-14T00:16:00+00:00'},
    ]
    get_store().mutate(sid,lambda state: state['drafts'][draft['id']].update(
        profile_digest='previous-profile-digest',messages=old_messages,revision=3,
    ))
    before=get_store().read(sid)
    old_events=deepcopy(before['events'])
    old_runs=deepcopy(before['drafts'][draft['id']]['ai_runs'])

    response=client.post(f"/api/intents/{draft['id']}/refresh-profile",json={
        'revision':3,'time_zone':'America/New_York',
    })
    assert response.status_code==200,response.text
    refreshed=response.json()
    replayed=calls[-1][1]['source_messages']
    assert len(calls)==2
    assert calls[-1][1]['source_text']=='Nonstop under $300\nFrom EWR to MCO on 2026-11-12'
    assert [m['content'] for m in replayed]==[m['content'] for m in old_messages]
    assert [m['timestamp'] for m in replayed]==[m['timestamp'] for m in old_messages]
    assert [m['reference_date'] for m in replayed]==['2026-10-13','2026-10-13']
    assert refreshed['profile_current'] is True
    assert refreshed['revision']==4 and refreshed['reviewed'] is False
    assert refreshed['time_zone']=='America/New_York'
    assert refreshed['ai_runs'][:len(old_runs)]==old_runs
    assert refreshed['messages'][0]['content']==old_messages[0]['content']
    assert refreshed['messages'][0]['timestamp']==old_messages[0]['timestamp']
    assert not refreshed.get('approved') and not refreshed.get('offer_views')
    events=get_store().read(sid)['events']
    assert events[:len(old_events)]==old_events
    upgrade=events[-1]
    assert upgrade['kind']=='profile_reinterpreted'
    assert upgrade['data']['old_profile_digest']=='previous-profile-digest'
    assert upgrade['data']['new_profile_digest']==refreshed['profile_digest']
    assert upgrade['data']['unapproved'] is True
    assert len(upgrade['data']['clock_provenance']['reference_dates_added'])==2


def test_profile_refresh_provider_rejection_leaves_history_unchanged(client,monkeypatch):
    def extraction(*args,**kwargs):
        return _live_result()

    monkeypatch.setattr('app.foundry_client.extract',extraction)
    draft=client.post('/api/intents',json={'mode':'live','message':'Nonstop under $300'}).json()
    _mark_stale(client,draft['id'])
    sid=client.cookies['ij_session']
    before=get_store().read(sid)
    before_draft=deepcopy(before['drafts'][draft['id']])
    before_events=deepcopy(before['events'])

    def rejected(*args,**kwargs):
        raise ValueError('provider rejected the reinterpretation')

    monkeypatch.setattr('app.foundry_client.extract',rejected)
    response=client.post(f"/api/intents/{draft['id']}/refresh-profile",json={
        'revision':draft['revision'],'time_zone':'UTC',
    })
    assert response.status_code==503
    after=get_store().read(sid)
    after_draft=after['drafts'][draft['id']]
    assert after_draft==before_draft
    assert after['events']==before_events


def test_profile_refresh_current_draft_rejects_without_provider_call(client,monkeypatch):
    calls=[]
    monkeypatch.setattr('app.foundry_client.extract',lambda *args,**kwargs: calls.append(True) or _live_result())
    draft=client.post('/api/intents',json={'mode':'offline','message':'Find a flight under $300'}).json()
    response=client.post(f"/api/intents/{draft['id']}/refresh-profile",json={
        'revision':draft['revision'],'time_zone':'America/New_York',
    })
    assert response.status_code==409
    assert calls==[]


def test_profile_refresh_lease_rejects_before_provider_call(client,monkeypatch):
    calls=[]
    monkeypatch.setattr('app.foundry_client.extract',lambda *args,**kwargs: calls.append(True) or _live_result())
    draft=client.post('/api/intents',json={'mode':'offline','message':'Find a flight under $300'}).json()
    _mark_stale(client,draft['id'])
    sid=client.cookies['ij_session']
    get_store().mutate(sid,lambda state: state.update(
        _ai_pending={'kind':'interpretation','intent_id':draft['id'],'started_at':time.time()}
    ))
    response=client.post(f"/api/intents/{draft['id']}/refresh-profile",json={
        'revision':draft['revision'],'time_zone':'UTC',
    })
    assert response.status_code==409
    assert calls==[]


def test_profile_refresh_completed_receipt_is_immutable_and_skips_provider(client,monkeypatch):
    from tests.test_enforcement import decision,prepare

    draft,offers=prepare(client)
    checked=decision(client,draft,offers[0])
    receipt=client.post('/api/purchase',json={
        'decision_id':checked['id'],'idempotency_key':'refresh-profile-receipt',
    }).json()
    _mark_stale(client,draft['id'])
    calls=[]
    monkeypatch.setattr('app.foundry_client.extract',lambda *args,**kwargs: calls.append(True) or pytest.fail('provider must not run'))
    response=client.post(f"/api/intents/{draft['id']}/refresh-profile",json={
        'revision':draft['revision'],'time_zone':'UTC',
    })
    assert response.status_code==409
    assert calls==[]
    assert client.get(f"/api/purchases/{receipt['id']}/evidence").json()['purchase']['id']==receipt['id']

