import pytest
from app.ai_grounding import GroundingFailure, validate_extraction


def envelope(fields=None, sources=None, unsupported=None, clarifications=None):
    return {'fields': fields or {}, 'sources': sources or {},
            'unsupported': unsupported or [], 'clarifications': clarifications or [],
            'explanation': 'Review the choices you requested.'}


def test_original_relative_window_is_supported_and_florida_needs_airports():
    text = 'I need a nonstop flight to FL under $200 thats within the next week'
    messages = [{'role': 'user', 'content': text,
                 'timestamp': '2026-10-14T00:15:00+00:00', 'reference_date': '2026-10-13'}]
    result = validate_extraction('flight', text, envelope(
        {'max_total_cents': 19999, 'nonstop': True},
        {'max_total_cents': 'under $200', 'nonstop': 'nonstop'},
        ['to FL', 'within the next week']), source_messages=messages)
    assert result['fields']['departure_date'] == {'start': '2026-10-14', 'end': '2026-10-20'}
    assert result['unsupported'] == []
    assert result['clarifications'] == [{'field': 'destination_airports', 'source_quote': 'to FL', 'reason': 'ambiguous'}]


def test_airport_and_date_answers_resolve_prior_markers_without_losing_bags():
    original = 'To FL within the next week with a checked bag.'
    latest = 'Oct 14th through oct 21st'
    text = original + '\nArrive at MCO or MIA.\n' + latest
    messages = [
        {'role': 'user', 'content': original, 'timestamp': '2026-10-14T00:15:00Z', 'reference_date': '2026-10-13'},
        {'role': 'user', 'content': 'Arrive at MCO or MIA.', 'timestamp': '2026-10-14T00:16:00Z',
         'reference_date': '2026-10-13', 'reply_to': {'field': 'destination_airports'}},
        {'role': 'user', 'content': latest, 'timestamp': '2026-10-14T00:17:00Z',
         'reference_date': '2026-10-13', 'reply_to': {'field': 'departure_date'}},
    ]
    result = validate_extraction('flight', text, envelope(
        {'destination_airports': ['MCO', 'MIA'], 'departure_date': '2026-10-14'},
        {'destination_airports': 'Arrive at MCO or MIA.', 'departure_date': 'Oct 14th'},
        ['To FL', 'FL', 'within the next week', latest, 'checked bag']), source_messages=messages)
    assert result['fields']['departure_date'] == {'start': '2026-10-14', 'end': '2026-10-21'}
    assert result['unsupported'] == ['checked bag']
    assert result['clarifications'] == []
    assert result['sources']['departure_date'] == latest


def test_complete_customer_airport_selection_survives_partial_model_proposal():
    text = 'Arrive at MCO or MIA.'
    messages = [{'role': 'user', 'content': text, 'reply_to': {'field': 'destination_airports'}}]
    result = validate_extraction('flight', text, envelope(
        {'destination_airports': ['MCO']}, {'destination_airports': 'MCO'}), source_messages=messages)
    assert result['fields']['destination_airports'] == ['MCO', 'MIA']
    assert result['sources']['destination_airports'] == text


def test_geographic_mismatch_and_qualified_date_conditions_remain_visible():
    text = 'To FL; arrive at LAX. Oct 14 through Oct 21 with a checked bag.'
    result = validate_extraction('flight', text, envelope(
        {'destination_airports': ['LAX']}, {'destination_airports': 'LAX'},
        ['To FL', 'Oct 14 through Oct 21 with a checked bag']))
    assert result['unsupported'] == ['To FL', 'Oct 14 through Oct 21 with a checked bag']


def test_trusted_hotel_clock_resolves_year_without_inventing_a_stay():
    text = 'One room from November 20 through November 22.'
    messages = [{'role': 'user', 'content': text, 'timestamp': '2026-10-14T00:15:00Z', 'reference_date': '2026-10-13'}]
    result = validate_extraction('hotel', text, envelope(
        {'checkin_date': '2026-11-20', 'checkout_date': '2026-11-22'},
        {'checkin_date': 'November 20', 'checkout_date': 'November 22'}), source_messages=messages)
    assert result['fields'] == {'checkin_date': '2026-11-20', 'checkout_date': '2026-11-22'}


def test_initial_request_preserves_the_full_range_when_model_quotes_first_day():
    text = 'Book a nonstop flight from EWR to MCO under $200 from Oct 14th through Oct 21st.'
    messages = [{'role': 'user', 'content': text, 'timestamp': '2026-10-14T00:15:00Z', 'reference_date': '2026-10-13'}]
    result = validate_extraction('flight', text, envelope(
        {'departure_date': '2026-10-14'}, {'departure_date': 'Oct 14th'}), source_messages=messages)
    assert result['fields']['departure_date'] == {'start': '2026-10-14', 'end': '2026-10-21'}
    assert result['sources']['departure_date'] == 'Oct 14th through Oct 21st'


def test_short_location_quote_is_not_restored_to_a_subword():
    text = 'A flight to FL.'
    result = validate_extraction('flight', text, envelope(
        clarifications=[{'field': 'destination_airports', 'source_quote': 'FL', 'reason': 'ambiguous'}]))
    assert result['clarifications'][0]['source_quote'] == 'FL'
    with pytest.raises(GroundingFailure):
        validate_extraction('flight', 'I want to relax.', envelope(
            {'destination_airports': ['LAX']}, {'destination_airports': 'lax'}))


def test_short_boolean_quote_cannot_hide_customer_negation():
    with pytest.raises(GroundingFailure):
        validate_extraction('flight', 'A non-refundable flight.', envelope(
            {'refundable': True}, {'refundable': 'refundable'}))
    result = validate_extraction('flight', 'A non-refundable flight.', envelope(
        {'refundable': False}, {'refundable': 'refundable'}))
    assert result['fields']['refundable'] is False
    assert result['sources']['refundable'] == 'non-refundable'
    for text, field, quote in [
        ("I don't require nonstop.", 'nonstop', 'nonstop'),
        ('I do not need refundable fees.', 'refundable', 'refundable'),
    ]:
        result = validate_extraction('flight', text, envelope({field: True}, {field: quote}))
        assert field not in result['fields']


def test_negation_of_one_amenity_does_not_change_another():
    text = 'No refundable fare, but breakfast is required.'
    result = validate_extraction('hotel', text, envelope({'breakfast': True}, {'breakfast': 'breakfast'}))
    assert result['fields']['breakfast'] is True


def test_flight_location_phrase_is_resolved_by_customer_selected_florida_airports():
    text='I need a flight to Florida with a checked bag.\nArrive at MCO or MIA.'
    result=validate_extraction('flight',text,envelope(
        {'destination_airports':['MCO','MIA']},
        {'destination_airports':'Arrive at MCO or MIA.'},
        ['flight to Florida','checked bag']))
    assert result['unsupported']==['checked bag']
    assert result['fields']['destination_airports']==['MCO','MIA']


def test_qualified_flight_location_phrase_and_mismatched_airport_remain_held():
    text='A flight to Florida with a checked bag.\nArrive at LAX.'
    result=validate_extraction('flight',text,envelope(
        {'destination_airports':['LAX']},{'destination_airports':'Arrive at LAX.'},
        ['flight to Florida','flight to Florida with a checked bag']))
    assert result['unsupported']==['flight to Florida','flight to Florida with a checked bag']


def test_dotted_clock_window_and_unimplemented_flight_conditions_survive_model_omissions():
    text='A flight for one adult on any date from May 5 through May 9, 2027, with May 7 preferred. Depart between 8 a.m. and 8 p.m.'
    result=validate_extraction('flight',text,envelope(
        {'departure_date':{'start':'2027-05-05','end':'2027-05-09'},'departure_window':['08:00','20:00']},
        {'departure_date':'May 5 through May 9, 2027','departure_window':'between 8 a.m. and 8 p.m.'}))
    assert result['fields']['departure_window']==['08:00','20:00']
    assert result['fields']['departure_date']=={'start':'2027-05-05','end':'2027-05-09'}
    assert result['unsupported']==['for one adult','May 7 preferred']
    with pytest.raises(GroundingFailure):
        validate_extraction('flight','Between 8 am and 8 pm.',envelope(
            {'departure_window':['08:07','20:00']},{'departure_window':'Between 8 am and 8 pm.'}))


def test_explicit_dotted_times_resolve_vague_period_and_keep_correct_meridiem():
    text='Depart in the morning, specifically between 8 a.m. and 11 a.m.'
    result=validate_extraction('flight',text,envelope(
        {'departure_window':['08:00','11:00']},{'departure_window':text}))
    assert result['fields']['departure_window']==['08:00','11:00']
    assert result['clarifications']==[]
    text='Depart between 8:00 p.m. and 9:00 p.m.'
    result=validate_extraction('flight',text,envelope(
        {'departure_window':['20:00','21:00']},{'departure_window':text}))
    assert result['fields']['departure_window']==['20:00','21:00']
    with pytest.raises(GroundingFailure):
        validate_extraction('flight',text,envelope(
            {'departure_window':['08:00','09:00']},{'departure_window':text}))
