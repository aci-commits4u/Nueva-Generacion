"""Deterministic regressions for the live proposal grounding boundary."""

import pytest

from app.ai_grounding import GroundingFailure, validate_extraction
from app.profile_registry import get_profile


def envelope(fields, sources, *, unsupported=None):
    return {
        "fields": fields,
        "sources": sources,
        "unsupported": [] if unsupported is None else unsupported,
        "explanation": "Review the proposed requirements.",
    }


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
    with pytest.raises(ValueError):
        validate_extraction(
            "flight", "arrive in the morning under $300",
            envelope5(
                {"max_total_cents": 29999}, {"max_total_cents": "under $300"},
                clarifications=[{"field": "arrival_window", "source_quote": "morning", "reason": "ambiguous"}],
                unsupported=["arrive in the morning"],
            ),
        )


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
    with pytest.raises(GroundingFailure):
        validate_extraction(
            "flight",
            "under $300\nNo",
            envelope(
                {"nonstop": True, "max_total_cents": 29999},
                {"nonstop": "No", "max_total_cents": "under $300"},
            ),
            source_messages=[
                {"role": "user", "content": "under $300"},
                {"role": "user", "content": "No", "reply_to": {"field": "nonstop", "question": question}},
            ],
        )
    with pytest.raises(GroundingFailure):
        validate_extraction(
            "flight",
            "under $300\nNo",
            envelope(
                {"nonstop": False, "max_total_cents": 29999},
                {"nonstop": "No", "max_total_cents": "under $300"},
            ),
            source_messages=[
                {"role": "user", "content": "under $300"},
                {"role": "user", "content": "No", "reply_to": {"field": "nonstop", "question": question}},
            ],
        )
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
    with pytest.raises(GroundingFailure):
        validate_extraction(
            "flight",
            "Leave in the morning under $300",
            envelope(
                {"departure_window": ["09:00", "12:00"], "max_total_cents": 29999},
                {"departure_window": "morning", "max_total_cents": "under $300"},
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
