"""Deterministic regressions for the live proposal grounding boundary."""

from copy import deepcopy

import pytest

import app.ai_grounding as grounding
from app.ai_grounding import GroundingFailure, validate_extraction
from app.profile_registry import get_profile


def envelope(fields, sources, *, unsupported=None):
    return {
        "fields": fields,
        "sources": sources,
        "unsupported": [] if unsupported is None else unsupported,
        "explanation": "Review the proposed requirements.",
    }


def test_airport_code_cannot_be_grounded_in_an_unrelated_word():
    with pytest.raises(GroundingFailure):
        validate_extraction('flight','A place to relax under $300',
                            envelope({'destination_airports':['LAX']},{'destination_airports':'relax'}))


def envelope5(fields, sources, *, clarifications=None, unsupported=None):
    result = envelope(fields, sources, unsupported=unsupported)
    result["clarifications"] = [] if clarifications is None else clarifications
    return result


def test_broad_state_is_a_clarification_need_not_an_airport():
    result = validate_extraction(
        "flight",
        "I need to get to Florida under $300",
        envelope(
            {"destination_airports": ["Florida"], "max_total_cents": 29999},
            {"destination_airports": "Florida", "max_total_cents": "under $300"},
        ),
    )

    assert "destination_airports" not in result["fields"]
    assert "Florida" in result["explanation"]
    assert result["fields"]["max_total_cents"] == 29999
    assert not any("unspecified" in item.casefold() for item in result["unsupported"])
    assert result["clarifications"] == [{"field": "destination_airports", "source_quote": "Florida", "reason": "ambiguous"}]


def test_florida_reconciliation_accepts_catalogue_airport_beyond_demo_four():
    data = envelope5(
        {"destination_airports": ["RSW"]},
        {"destination_airports": "RSW"},
        clarifications=[{
            "field": "destination_airports",
            "source_quote": "Florida",
            "reason": "ambiguous",
        }],
    )
    reconciled = grounding.reconcile_supported_conditions(
        data,
        "flight",
        "Fly to Florida, specifically RSW.",
    )
    assert reconciled["fields"]["destination_airports"] == ["RSW"]
    assert reconciled["clarifications"] == []


def test_structured_clarifications_cover_florida_and_soft_preferences():
    florida = validate_extraction(
        "flight",
        "I need a flight to Florida under $300",
        envelope5(
            {"max_total_cents": 29999},
            {"max_total_cents": "under $300"},
            clarifications=[{"field": "destination_airports", "source_quote": "Florida", "reason": "ambiguous"}],
        ),
    )
    preference = validate_extraction(
        "flight",
        "Preferably nonstop under $300",
        envelope5(
            {"max_total_cents": 29999},
            {"max_total_cents": "under $300"},
            clarifications=[{"field": "nonstop", "source_quote": "Preferably nonstop", "reason": "preference"}],
        ),
    )
    assert florida["unsupported"] == []
    assert florida["clarifications"][0]["field"] == "destination_airports"
    assert preference["clarifications"][0]["reason"] == "preference"


def test_clarification_source_and_profile_field_are_checked():
    with pytest.raises((GroundingFailure, ValueError)):
        validate_extraction(
            "flight", "Florida under $300",
            envelope5(
                {"max_total_cents": 29999}, {"max_total_cents": "under $300"},
                clarifications=[{"field": "destination_airports", "source_quote": "Texas", "reason": "ambiguous"}],
            ),
        )

    result = validate_extraction(
        "flight", "arrive in the morning under $300",
        envelope5(
            {"max_total_cents": 29999}, {"max_total_cents": "under $300"},
            clarifications=[{"field": "arrival_window", "source_quote": "morning", "reason": "ambiguous"}],
            unsupported=["arrive in the morning"],
        ),
    )
    assert result["clarifications"] == []
    assert result["unsupported"] == ["arrive in the morning"]


def test_typographic_source_variants_restore_the_exact_customer_spans():
    message = "I’m visiting Tampa on Nov 7–10; keep it under\u00a0$300."
    result = validate_extraction(
        "flight",
        message,
        envelope5(
            {"max_total_cents": 29999},
            {"max_total_cents": "under $300"},
            clarifications=[{
                "field": "departure_date",
                "source_quote": "Nov 7‑10",
                "reason": "ambiguous",
            }],
        ),
    )

    assert result["sources"]["max_total_cents"] == "under\u00a0$300"
    assert result["clarifications"] == [{
        "field": "departure_date",
        "source_quote": "Nov 7–10",
        "reason": "ambiguous",
    }]


def test_grounded_unknown_clarification_fields_become_unsupported_conditions():
    result = validate_extraction(
        "flight",
        "Fly from Newark to Tampa under $300; arrive before dinner and return Nov 10.",
        envelope5(
            {
                "origin_airports": ["EWR"],
                "destination_airports": ["TPA"],
                "max_total_cents": 29999,
            },
            {
                "origin_airports": "Newark",
                "destination_airports": "Tampa",
                "max_total_cents": "under $300",
            },
            clarifications=[
                {"field": "arrival_window", "source_quote": "arrive before dinner", "reason": "preference"},
                {"field": "return_date", "source_quote": "return Nov 10", "reason": "ambiguous"},
            ],
        ),
    )

    assert result["fields"] == {
        "origin_airports": ["EWR"],
        "destination_airports": ["TPA"],
        "max_total_cents": 29999,
    }
    assert result["clarifications"] == []
    assert result["unsupported"] == ["arrive before dinner", "return Nov 10"]


@pytest.mark.parametrize("clarification", [
    {"field": "arrival_window", "source_quote": "not in the request", "reason": "ambiguous"},
    {"field": "arrival_window", "source_quote": "arrive before dinner", "reason": "unsupported"},
    {"field": "", "source_quote": "arrive before dinner", "reason": "ambiguous"},
    {"field": "arrival_window", "source_quote": "arrive before dinner", "reason": 1},
])
def test_unknown_clarification_requires_grounded_well_formed_evidence(clarification):
    with pytest.raises(ValueError):
        validate_extraction(
            "flight",
            "Fly from Newark to Tampa under $300; arrive before dinner.",
            envelope5(
                {
                    "origin_airports": ["EWR"],
                    "destination_airports": ["TPA"],
                    "max_total_cents": 29999,
                },
                {
                    "origin_airports": "Newark",
                    "destination_airports": "Tampa",
                    "max_total_cents": "under $300",
                },
                clarifications=[clarification],
            ),
        )


@pytest.mark.parametrize("quote", [
    "the first week of November, Nov 7‑10",  # changed word
    "early November",                         # paraphrase
    "I do want an overnight itinerary",       # changed negation
])
def test_source_restoration_rejects_words_paraphrases_and_negation_changes(quote):
    with pytest.raises(GroundingFailure):
        validate_extraction(
            "flight",
            "I don’t want an overnight itinerary on Nov 7–10 under $300.",
            envelope5(
                {"max_total_cents": 29999},
                {"max_total_cents": "under $300"},
                clarifications=[{
                    "field": "departure_date",
                    "source_quote": quote,
                    "reason": "ambiguous",
                }],
            ),
        )


def test_arrival_and_overnight_clarifications_become_unsupported_conditions():
    result = validate_extraction(
        "flight",
        "I’d prefer to land before dinner, and I don’t want an overnight itinerary.",
        envelope5(
            {},
            {},
            clarifications=[
                {"field": "departure_window", "source_quote": "I’d prefer to land before dinner", "reason": "preference"},
                {"field": "max_duration_minutes", "source_quote": "I don’t want an overnight itinerary", "reason": "ambiguous"},
            ],
        ),
    )

    assert result["clarifications"] == []
    assert result["unsupported"] == [
        "I’d prefer to land before dinner",
        "I don’t want an overnight itinerary",
    ]


def test_supported_clarification_does_not_launder_unavailable_requirement():
    result = validate_extraction(
        "flight", "I want to arrive in the morning under $300",
        envelope5(
            {"max_total_cents": 29999}, {"max_total_cents": "under $300"},
            unsupported=["arrive in the morning"],
        ),
    )
    assert result["unsupported"] == ["arrive in the morning"]
    assert result["clarifications"] == []


def test_typed_missing_airport_marker_is_not_a_permanent_unsupported_condition():
    result = validate_extraction(
        "flight",
        "I need to get to Florida under $300",
        envelope(
            {"max_total_cents": 29999},
            {"max_total_cents": "under $300"},
            unsupported=["destination unspecified (Florida)", "round trip"],
        ),
    )
    assert result["unsupported"] == ["round trip"]
    assert "Please specify a destination airport for Florida." in result["explanation"]


def test_specific_city_is_normalized_to_a_known_airport():
    result = validate_extraction(
        "flight",
        "Fly from Newark to Tampa for under $300",
        envelope(
            {
                "origin_airports": ["Newark"],
                "destination_airports": ["Tampa"],
                "max_total_cents": 29999,
            },
            {
                "origin_airports": "Newark",
                "destination_airports": "Tampa",
                "max_total_cents": "under $300",
            },
        ),
    )

    assert result["fields"]["origin_airports"] == ["EWR"]
    assert result["fields"]["destination_airports"] == ["TPA"]


@pytest.mark.parametrize(
    ("place", "code"),
    [("Lisbon", "LIS"), ("Heathrow", "LHR")],
)
def test_catalogue_places_resolve_without_a_local_alias(place, code):
    result = validate_extraction(
        "flight",
        f"Fly to {place} under $300",
        envelope(
            {"destination_airports": [place], "max_total_cents": 29999},
            {"destination_airports": place, "max_total_cents": "under $300"},
        ),
    )
    assert result["fields"]["destination_airports"] == [code]


def test_multi_airport_city_stays_ambiguous_without_explicit_alternatives():
    result = validate_extraction(
        "flight",
        "Fly to Tokyo under $300",
        envelope(
            {"destination_airports": ["Tokyo"], "max_total_cents": 29999},
            {"destination_airports": "Tokyo", "max_total_cents": "under $300"},
        ),
    )
    assert "destination_airports" not in result["fields"]
    assert result["clarifications"] == [{
        "field": "destination_airports", "source_quote": "Tokyo", "reason": "ambiguous",
    }]


def test_multi_airport_city_accepts_explicit_positive_same_city_alternatives():
    result = validate_extraction(
        "flight",
        "Fly to Tokyo, either HND or NRT, under $300",
        envelope(
            {"destination_airports": ["Tokyo"], "max_total_cents": 29999},
            {
                "destination_airports": "Tokyo, either HND or NRT",
                "max_total_cents": "under $300",
            },
        ),
    )
    assert result["fields"]["destination_airports"] == ["HND", "NRT"]


def test_catalogue_rejects_unknown_explicit_iata_code():
    with pytest.raises(GroundingFailure):
        validate_extraction(
            "flight",
            "Fly to XYZ under $300",
            envelope(
                {"destination_airports": ["XYZ"], "max_total_cents": 29999},
                {"destination_airports": "XYZ", "max_total_cents": "under $300"},
            ),
        )


@pytest.mark.parametrize("message", [
    "Arrive at MCO, but avoid MIA.",
    "Arrive at MCO, but not MIA.",
    "Arrive at MCO, except MIA.",
])
def test_airport_polarity_rejects_excluded_option_even_when_model_quotes_only_code(message):
    with pytest.raises(GroundingFailure):
        validate_extraction(
            "flight",
            message,
            envelope(
                {"destination_airports": ["MIA"]},
                {"destination_airports": "MIA"},
            ),
        )


def test_latest_bound_airport_reply_overrides_prior_negative_context():
    history = "I want to arrive in Florida, but avoid MIA."
    latest = "Arrive at MIA."
    result = validate_extraction(
        "flight",
        f"{history}\n{latest}",
        envelope(
            {"destination_airports": ["MIA"]},
            {"destination_airports": "MIA"},
        ),
        source_messages=[
            {"role": "user", "content": history},
            {
                "role": "user",
                "content": latest,
                "reply_to": {
                    "field": "destination_airports",
                    "question": "Which arrival airports are acceptable?",
                },
            },
        ],
    )
    assert result["fields"]["destination_airports"] == ["MIA"]


def test_latest_bound_origin_airport_reply_uses_origin_scope():
    history = "I want to depart from Florida, but avoid MIA."
    latest = "Depart from MIA."
    result = validate_extraction(
        "flight",
        f"{history}\n{latest}",
        envelope(
            {"origin_airports": ["MIA"]},
            {"origin_airports": "MIA"},
        ),
        source_messages=[
            {"role": "user", "content": history},
            {
                "role": "user",
                "content": latest,
                "reply_to": {
                    "field": "origin_airports",
                    "question": "Which departure airports are acceptable?",
                },
            },
        ],
    )
    assert result["fields"]["origin_airports"] == ["MIA"]


def test_unbound_tiny_airport_quote_remains_conservative_with_history():
    history = "I want to arrive in Florida, but avoid MIA."
    with pytest.raises(GroundingFailure):
        validate_extraction(
            "flight",
            history,
            envelope(
                {"destination_airports": ["MIA"]},
                {"destination_airports": "MIA"},
            ),
            source_messages=[{"role": "user", "content": history}],
        )


def test_airport_polarity_accepts_positive_multiple_explicit_options():
    message = "Arrive at MCO or MIA."
    result = validate_extraction(
        "flight",
        message,
        envelope(
            {"destination_airports": ["MCO", "MIA"]},
            {"destination_airports": "MCO or MIA"},
        ),
    )
    assert result["fields"]["destination_airports"] == ["MCO", "MIA"]


def test_cabin_is_canonicalized_while_source_quote_stays_exact():
    result = validate_extraction(
        "flight",
        "Economy is fine under $300.",
        envelope5(
            {"cabin": "Economy", "max_total_cents": 29999},
            {"cabin": "Economy", "max_total_cents": "under $300"},
        ),
    )

    assert result["fields"]["cabin"] == "economy"
    assert result["sources"]["cabin"] == "Economy"


@pytest.mark.parametrize("message", [
    "I do not want economy.",
    "I don’t want economy.",
    "Premium economy is preferred.",
])
def test_cabin_economy_does_not_match_specific_or_negated_categories(message):
    with pytest.raises(GroundingFailure):
        validate_extraction(
            "flight",
            message,
            envelope5({"cabin": "economy"}, {"cabin": message}),
        )


def test_cabin_positive_category_survives_unrelated_no_preference():
    result = validate_extraction(
        "flight",
        "Economy is fine; I have no preference on departure time or refundability.",
        envelope5({"cabin": "Economy"}, {"cabin": "Economy"}),
    )
    assert result["fields"]["cabin"] == "economy"


def test_one_way_trip_type_requires_explicit_source_and_reconciles_only_duplicate_marker(monkeypatch):
    original_get_profile = grounding.get_profile

    def profile_with_trip_type(domain):
        profile = deepcopy(original_get_profile(domain))
        if domain == "flight":
            profile["fields"]["trip_type"] = {
                "type": "string", "op": "eq", "fact": "trip_type",
                "label": "Trip type", "question": "One way or round trip?",
            }
        return profile

    monkeypatch.setattr(grounding, "get_profile", profile_with_trip_type)
    result = validate_extraction(
        "flight",
        "I only need the outbound this time; under $300; round trip is unsupported.",
        envelope5(
            {"trip_type": "ONE-WAY", "max_total_cents": 29999},
            {"trip_type": "only need the outbound", "max_total_cents": "under $300"},
            unsupported=["only need the outbound", "round trip"],
        ),
    )

    assert result["fields"]["trip_type"] == "one_way"
    assert result["unsupported"] == ["round trip"]


@pytest.mark.parametrize("message", [
    "I do not want a one-way flight.",
    "I don’t want a one-way flight.",
    "I have no preference on one-way.",
])
def test_negated_one_way_phrase_cannot_set_trip_type(message):
    with pytest.raises(GroundingFailure):
        validate_extraction(
            "flight",
            message,
            envelope5({"trip_type": "one_way"}, {"trip_type": message}),
        )


def test_one_way_phrase_survives_unrelated_refundability_no_preference():
    result = validate_extraction(
        "flight",
        "I need a one-way flight; I have no preference on refundability.",
        envelope5({"trip_type": "one_way"}, {"trip_type": "one-way"}),
    )
    assert result["fields"]["trip_type"] == "one_way"


def test_one_way_cannot_be_inferred_from_unrelated_outbound_word(monkeypatch):
    original_get_profile = grounding.get_profile

    def profile_with_trip_type(domain):
        profile = deepcopy(original_get_profile(domain))
        if domain == "flight":
            profile["fields"]["trip_type"] = {"type": "string", "op": "eq", "fact": "trip_type"}
        return profile

    monkeypatch.setattr(grounding, "get_profile", profile_with_trip_type)
    with pytest.raises(GroundingFailure):
        validate_extraction(
            "flight",
            "Outbound flight under $300.",
            envelope5(
                {"trip_type": "one_way", "max_total_cents": 29999},
                {"trip_type": "outbound", "max_total_cents": "under $300"},
            ),
        )


def test_explicit_iata_code_is_accepted_when_customer_said_it():
    result = validate_extraction(
        "flight",
        "Fly from LHR to CDG under $300",
        envelope(
            {"origin_airports": ["LHR"], "destination_airports": ["CDG"], "max_total_cents": 29999},
            {"origin_airports": "LHR", "destination_airports": "CDG", "max_total_cents": "under $300"},
        ),
    )
    assert result["fields"]["origin_airports"] == ["LHR"]
    assert result["fields"]["destination_airports"] == ["CDG"]


@pytest.mark.parametrize("token", ["NYC", "CHI", "USA"])
def test_broad_three_letter_location_tokens_are_not_airports(token):
    result = validate_extraction(
        "flight",
        f"Fly to {token} under $300",
        envelope(
            {"destination_airports": [token], "max_total_cents": 29999},
            {"destination_airports": token, "max_total_cents": "under $300"},
        ),
    )
    assert "destination_airports" not in result["fields"]
    assert result["clarifications"][0]["source_quote"] == token


def test_unknown_city_becomes_a_clarification_need():
    result = validate_extraction(
        "flight",
        "Fly to Atlantis under $300",
        envelope(
            {"destination_airports": ["Atlantis"], "max_total_cents": 29999},
            {"destination_airports": "Atlantis", "max_total_cents": "under $300"},
        ),
    )
    assert "destination_airports" not in result["fields"]
    assert "Atlantis" in result["explanation"]


def test_invented_broad_location_quote_is_rejected():
    with pytest.raises(GroundingFailure):
        validate_extraction(
            "flight",
            "Fly to Florida under $300",
            envelope(
                {"destination_airports": ["Florida"], "max_total_cents": 29999},
                {"destination_airports": "somewhere else", "max_total_cents": "under $300"},
            ),
        )


def test_nonstop_requires_a_nonstop_source_quote():
    with pytest.raises(GroundingFailure):
        validate_extraction(
            "flight",
            "Find me a flight under $300",
            envelope(
                {"nonstop": True, "max_total_cents": 29999},
                {"nonstop": "flight", "max_total_cents": "under $300"},
            ),
        )


def test_no_connections_supports_required_nonstop():
    result = validate_extraction(
        "flight",
        "I need no connections under $300",
        envelope(
            {"nonstop": True, "max_total_cents": 29999},
            {"nonstop": "no connections", "max_total_cents": "under $300"},
        ),
    )
    assert result["fields"]["nonstop"] is True


def test_without_any_connections_supports_required_nonstop():
    result = validate_extraction(
        "flight",
        "I need a flight without any connections under $300",
        envelope(
            {"nonstop": True, "max_total_cents": 29999},
            {"nonstop": "without any connections", "max_total_cents": "under $300"},
        ),
    )
    assert result["fields"]["nonstop"] is True


def test_preferably_nonstop_is_not_a_hard_boolean():
    with pytest.raises(GroundingFailure):
        validate_extraction(
            "flight",
            "Preferably nonstop under $300",
            envelope(
                {"nonstop": True, "max_total_cents": 29999},
                {"nonstop": "Preferably nonstop", "max_total_cents": "under $300"},
            ),
        )


def test_yes_binds_only_to_the_trusted_profile_question():
    question = get_profile("flight")["fields"]["nonstop"]["question"]
    result = validate_extraction(
        "flight",
        "under $300\nYes",
        envelope(
            {"nonstop": True, "max_total_cents": 29999},
            {"nonstop": "Yes", "max_total_cents": "under $300"},
        ),
        source_messages=[
            {"role": "user", "content": "under $300"},
            {"role": "user", "content": "Yes", "reply_to": {"field": "nonstop", "question": question}},
        ],
    )
    assert result["fields"]["nonstop"] is True


def test_no_to_a_boolean_question_is_not_false_and_misbinding_is_rejected():
    question = get_profile("flight")["fields"]["nonstop"]["question"]
    for value in (True, False):
        result = validate_extraction(
            "flight",
            "under $300\nNo",
            envelope(
                {"nonstop": value, "max_total_cents": 29999},
                {"nonstop": "No", "max_total_cents": "under $300"},
            ),
            source_messages=[
                {"role": "user", "content": "under $300"},
                {"role": "user", "content": "No", "reply_to": {"field": "nonstop", "question": question}},
            ],
        )
        assert "nonstop" not in result["fields"]
    with pytest.raises(GroundingFailure):
        validate_extraction(
            "flight",
            "under $300\nYes",
            envelope(
                {"nonstop": True, "max_total_cents": 29999},
                {"nonstop": "Yes", "max_total_cents": "under $300"},
            ),
            source_messages=[
                {"role": "user", "content": "under $300"},
                {"role": "user", "content": "Yes", "reply_to": {"field": "refundable", "question": "Must the fare be refundable?"}},
            ],
        )


@pytest.mark.parametrize("phrase", [
    "no need for breakfast",
    "no preference for breakfast",
    "without caring about breakfast",
])
def test_unpreferred_boolean_phrases_omit_the_field_instead_of_grounding_false(phrase):
    result = validate_extraction(
        "hotel",
        f"Tampa under $300 {phrase}",
        envelope(
            {"breakfast": False, "max_total_cents": 29999},
            {"breakfast": phrase, "max_total_cents": "under $300"},
        ),
    )
    assert "breakfast" not in result["fields"]


@pytest.mark.parametrize("phrase", [
    "the reservation must be freely cancellable",
    "the reservation must be free cancelable",
    "the reservation can be canceled free",
    "the reservation can be cancelled freely",
    "free cancellation is required",
])
def test_refundable_accepts_customer_cancellation_synonyms(phrase):
    result = validate_extraction(
        "hotel",
        phrase,
        envelope({"refundable": True}, {"refundable": phrase}),
    )
    assert result["fields"]["refundable"] is True


@pytest.mark.parametrize("phrase", [
    "I don't want free cancellation",
    "no refundable fees",
])
def test_refundable_negation_or_fee_language_cannot_ground_true(phrase):
    with pytest.raises(GroundingFailure):
        validate_extraction(
            "hotel",
            phrase,
            envelope({"refundable": True}, {"refundable": phrase}),
        )


def test_refundable_no_requirement_is_omitted_even_with_curly_apostrophe():
    phrase = "I don’t require refundable fees"
    result = validate_extraction(
        "hotel", phrase,
        envelope({"refundable": True}, {"refundable": phrase}),
    )
    assert "refundable" not in result["fields"]


@pytest.mark.parametrize("phrase", ["non-refundable", "non refundable"])
def test_non_refundable_is_not_positive_refundable_evidence(phrase):
    with pytest.raises(GroundingFailure):
        validate_extraction(
            "hotel", phrase,
            envelope({"refundable": True}, {"refundable": phrase}),
        )
    result = validate_extraction(
        "hotel", phrase,
        envelope({"refundable": False}, {"refundable": phrase}),
    )
    assert result["fields"]["refundable"] is False


def test_refundable_is_scoped_past_unrelated_no_preference_clause():
    phrase = "I have no preference on departure time; refundable is fine"
    result = validate_extraction(
        "hotel", phrase,
        envelope({"refundable": True}, {"refundable": phrase}),
    )
    assert result["fields"]["refundable"] is True


def test_preferably_refundable_remains_a_soft_preference():
    phrase = "Preferably refundable"
    with pytest.raises(GroundingFailure):
        validate_extraction(
            "hotel", phrase,
            envelope({"refundable": True}, {"refundable": phrase}),
        )


def test_no_accessibility_requirement_is_omitted_instead_of_false_preference():
    phrase = "No accessibility requirement; a standard room is fine."
    result = validate_extraction(
        "hotel", phrase,
        envelope({"accessible": False}, {"accessible": "No accessibility requirement"}),
    )
    assert "accessible" not in result["fields"]


def test_hotel_same_month_shared_year_proves_yearless_checkin_only():
    message = (
        "One room for two adults from November 20 through November 22, 2026, "
        "under $350."
    )
    result = validate_extraction(
        "hotel",
        message,
        envelope5(
            {
                "max_total_cents": 34999,
                "checkin_date": "2026-11-20",
                "checkout_date": "2026-11-22",
                "rooms": 1,
                "adults": 2,
            },
            {
                "max_total_cents": "under $350",
                "checkin_date": "November 20",
                "checkout_date": "November 22, 2026",
                "rooms": "one room",
                "adults": "two adults",
            },
        ),
    )
    assert result["fields"]["checkin_date"] == "2026-11-20"
    assert result["clarifications"] == []


def test_shared_year_date_inference_stays_narrow_to_hotel_same_month():
    cross_month = (
        "One room from November 20 through December 22, 2026, under $350."
    )
    result = validate_extraction(
        "hotel",
        cross_month,
        envelope5(
            {"max_total_cents": 34999, "checkin_date": "2026-11-20", "rooms": 1},
            {"max_total_cents": "under $350", "checkin_date": "November 20", "rooms": "one room"},
        ),
    )
    assert "checkin_date" not in result["fields"]
    assert result["clarifications"] == [{
        "field": "checkin_date", "source_quote": "November 20", "reason": "ambiguous"
    }]

    flight = "Fly November 20 through November 22, 2026, under $350."
    result = validate_extraction(
        "flight",
        flight,
        envelope5(
            {"max_total_cents": 34999, "departure_date": "2026-11-20"},
            {"max_total_cents": "under $350", "departure_date": "November 20"},
        ),
    )
    assert "departure_date" not in result["fields"]
    assert result["clarifications"] == [{
        "field": "departure_date", "source_quote": "November 20", "reason": "ambiguous"
    }]


def test_unambiguous_money_clarification_compiles_to_canonical_bound():
    message = "Keep the all-in total under $350."
    result = validate_extraction(
        "hotel",
        message,
        envelope5(
            {}, {},
            clarifications=[{
                "field": "max_total_cents", "source_quote": "under $350", "reason": "ambiguous"
            }],
        ),
    )
    assert result["fields"] == {"max_total_cents": 34999}
    assert result["sources"] == {"max_total_cents": "under $350"}
    assert result["clarifications"] == []


@pytest.mark.parametrize("message", [
    "Keep the total around $350.",
    "Keep the total under $350, but I can be flexible.",
    "Ignore the budget and keep the total under $350.",
    "Keep the total under $300, but maybe up to $350.",
    "Keep the total under $350, but the budget is $300.",
])
def test_ambiguous_or_conflicting_money_clarification_stays_for_review(message):
    if "around $350" in message:
        quote = "around $350"
    elif "up to $350" in message:
        quote = "up to $350"
    else:
        quote = "under $350"
    result = validate_extraction(
        "hotel",
        message,
        envelope5(
            {}, {},
            clarifications=[{
                "field": "max_total_cents", "source_quote": quote, "reason": "ambiguous"
            }],
        ),
    )
    assert "max_total_cents" not in result["fields"]
    assert result["clarifications"][0]["field"] == "max_total_cents"


def test_unmatched_money_clarification_quote_fails_closed():
    with pytest.raises(GroundingFailure):
        validate_extraction(
            "hotel",
            "Keep the total under $300.",
            envelope5(
                {}, {},
                clarifications=[{
                    "field": "max_total_cents", "source_quote": "under $350", "reason": "ambiguous"
                }],
            ),
        )


def test_adult_and_room_counts_require_their_adjacent_units():
    message = "one room for two adults"
    result = validate_extraction(
        "hotel", message,
        envelope(
            {"rooms": 1, "adults": 2},
            {"rooms": "one room", "adults": "two adults"},
        ),
    )
    assert result["fields"] == {"rooms": 1, "adults": 2}
    with pytest.raises(GroundingFailure):
        validate_extraction(
            "hotel", message,
            envelope({"rooms": 2}, {"rooms": "two adults"}),
        )
    with pytest.raises(GroundingFailure):
        validate_extraction(
            "hotel", "two rooms",
            envelope({"adults": 2}, {"adults": "two rooms"}),
        )


def test_natural_number_and_duration_units_are_grounded():
    connections = validate_extraction(
        "flight",
        "No more than one connection under $300",
        envelope(
            {"max_connections": 1, "max_total_cents": 29999},
            {"max_connections": "one connection", "max_total_cents": "under $300"},
        ),
    )
    duration = validate_extraction(
        "flight",
        "Trip under 2 hours for $300",
        envelope(
            {"max_duration_minutes": 120, "max_total_cents": 30000},
            {"max_duration_minutes": "2 hours", "max_total_cents": "$300"},
        ),
    )
    assert connections["fields"]["max_connections"] == 1
    assert duration["fields"]["max_duration_minutes"] == 120


def test_explicit_am_pm_window_is_normalized_without_treating_morning_as_a_time():
    result = validate_extraction(
        "flight",
        "Leave between 9:30 AM and 11 PM under $300",
        envelope(
            {"departure_window": ["09:30", "23:00"], "max_total_cents": 29999},
            {"departure_window": "9:30 AM and 11 PM", "max_total_cents": "under $300"},
        ),
    )
    assert result["fields"]["departure_window"] == ["09:30", "23:00"]
    morning = validate_extraction(
        "flight",
        "Leave in the morning under $300",
        envelope(
            {"departure_window": ["09:00", "12:00"], "max_total_cents": 29999},
            {"departure_window": "morning", "max_total_cents": "under $300"},
        ),
    )
    assert "departure_window" not in morning["fields"]
    assert morning["clarifications"] == [{
        "field": "departure_window", "source_quote": "morning", "reason": "ambiguous"
    }]
    date_like = validate_extraction(
        "flight",
        "Leave in the morning on Nov 7 under $300",
        envelope5(
            {"departure_window": ["09:00", "12:00"], "max_total_cents": 29999},
            {"departure_window": "morning on Nov 7", "max_total_cents": "under $300"},
        ),
    )
    assert date_like["clarifications"] == [{
        "field": "departure_window", "source_quote": "morning on Nov 7", "reason": "ambiguous"
    }]


@pytest.mark.parametrize("clarifications", [
    ["bad"],
    [{"field": "departure_window", "source_quote": None, "reason": "ambiguous"}],
    [{"field": "departure_window", "source_quote": "morning", "reason": "bad"}],
])
def test_malformed_clarification_records_fail_as_typed_validation_errors(clarifications):
    with pytest.raises(ValueError):
        validate_extraction(
            "flight",
            "Leave in the morning under $300",
            envelope5(
                {"max_total_cents": 29999},
                {"max_total_cents": "under $300"},
                clarifications=clarifications,
            ),
        )


def test_yearless_date_range_becomes_a_source_linked_clarification():
    result = validate_extraction(
        "flight",
        "I'm visiting Tampa from Newark the first weekend of November, Nov 7–10. "
        "Keep the round trip under $300 total; one connection is okay, but I don't want an overnight itinerary.",
        envelope5(
            {
                "origin_airports": ["EWR"],
                "destination_airports": ["TPA"],
                "departure_date": "2026-11-07",
                "max_total_cents": 29999,
                "max_connections": 1,
            },
            {
                "origin_airports": "Newark",
                "destination_airports": "Tampa",
                "departure_date": "Nov 7–10",
                "max_total_cents": "under $300",
                "max_connections": "one connection",
            },
            unsupported=["round trip"],
        ),
    )
    assert result["fields"]["origin_airports"] == ["EWR"]
    assert result["fields"]["destination_airports"] == ["TPA"]
    assert result["fields"]["max_connections"] == 1
    assert "departure_date" not in result["fields"]
    assert result["clarifications"] == [{
        "field": "departure_date", "source_quote": "Nov 7–10", "reason": "ambiguous"
    }]
    assert result["unsupported"] == ["round trip"]


def test_uncheckable_overnight_condition_is_preserved_without_false_nonstop():
    result = validate_extraction(
        "flight",
        "under $300 and I don't want an overnight itinerary",
        envelope(
            {"nonstop": False, "max_total_cents": 29999},
            {"nonstop": "I don't want an overnight itinerary", "max_total_cents": "under $300"},
        ),
    )
    assert "nonstop" not in result["fields"]
    assert result["unsupported"] == ["I don't want an overnight itinerary"]


def test_unavailable_arrival_window_is_unsupported_not_a_departure_requirement():
    result = validate_extraction(
        "flight",
        "I want to land before dinner under $300",
        envelope5(
            {"arrival_window": ["00:00", "18:00"], "max_total_cents": 29999},
            {"arrival_window": "land before dinner", "max_total_cents": "under $300"},
        ),
    )
    assert "arrival_window" not in result["fields"]
    assert result["unsupported"] == ["land before dinner"]


def test_yearless_recovery_does_not_accept_an_unrelated_source_quote():
    with pytest.raises(GroundingFailure):
        validate_extraction(
            "flight",
            "under $300",
            envelope5(
                {"departure_date": "2026-11-07", "max_total_cents": 29999},
                {"departure_date": "under $300", "max_total_cents": "under $300"},
            ),
        )


def test_invalid_explicit_money_value_is_not_recovered_as_uncertainty():
    with pytest.raises(GroundingFailure):
        validate_extraction(
            "flight",
            "under $300",
            envelope5(
                {"max_total_cents": 30000},
                {"max_total_cents": "under $300"},
            ),
        )


def test_under_and_at_most_have_different_money_bounds():
    under = validate_extraction(
        "flight",
        "under $300",
        envelope({"max_total_cents": 29999}, {"max_total_cents": "under $300"}),
    )
    at_most = validate_extraction(
        "flight",
        "at most $300",
        envelope({"max_total_cents": 30000}, {"max_total_cents": "at most $300"}),
    )

    assert under["fields"]["max_total_cents"] == 29999
    assert at_most["fields"]["max_total_cents"] == 30000
