"""Route-aware airport identity and source-grounding regressions."""

import pytest

from app.ai_grounding import GroundingFailure, validate_extraction
from app.airport_reference import (
    airport_context,
    airport_context_for_field,
    airport_field_scope,
    codes_for_place,
)


def envelope(fields=None, sources=None):
    return {
        "fields": fields or {},
        "sources": sources or {},
        "unsupported": [],
        "clarifications": [],
        "explanation": "Review the captured request.",
    }


def test_pronoun_does_not_create_a_maine_region_context():
    text = "Book me a nonstop flight from london to toronto on 2026-11-12 under $300."
    codes = {item["code"] for item in airport_context(text)}
    assert not codes & {"AUG", "BGR", "BHB", "CAR"}
    assert {"YTZ", "YYZ"} <= codes


def test_city_name_in_airport_name_is_identity_evidence():
    assert {"YTZ", "YYZ"} <= set(codes_for_place("Toronto"))


def test_field_context_scopes_london_to_dominant_uk_group_and_toronto_to_canada():
    text = "Book me a nonstop flight from london to toronto on 2026-11-12 under $300."
    assert airport_field_scope(text, "origin_airports") == "london"
    assert airport_field_scope(text, "destination_airports") == "toronto"

    origin = airport_context_for_field(text, "origin_airports")
    destination = airport_context_for_field(text, "destination_airports")
    assert origin
    assert destination
    assert {item["country"] for item in origin} == {"GB"}
    assert {item["country"] for item in destination} == {"CA"}
    assert {item["code"] for item in origin} >= {"LHR", "LGW"}
    assert {item["code"] for item in destination} == {"YTZ", "YYZ"}


@pytest.mark.parametrize(
    ("text", "field", "expected_country", "expected_codes"),
    [
        (
            "Fly from London, Ontario to Toronto.",
            "origin_airports",
            "CA",
            {"YXU"},
        ),
        (
            "Fly from Paris, France to Rome, Italy.",
            "origin_airports",
            "FR",
            {"CDG", "ORY", "LBG"},
        ),
        (
            "Fly from Paris, France to Rome, Italy.",
            "destination_airports",
            "IT",
            {"FCO"},
        ),
        (
            "Fly from Melbourne, Australia to Auckland, New Zealand.",
            "origin_airports",
            "AU",
            {"MEL", "AVV"},
        ),
        (
            "Fly from Melbourne, Australia to Auckland, New Zealand.",
            "destination_airports",
            "NZ",
            {"AKL"},
        ),
        (
            "Fly from Tokyo, Japan to Seoul, South Korea.",
            "origin_airports",
            "JP",
            {"HND", "NRT"},
        ),
        (
            "Fly from Tokyo, Japan to Seoul, South Korea.",
            "destination_airports",
            "KR",
            {"GMP", "ICN"},
        ),
    ],
)
def test_explicit_country_qualifiers_filter_catalog_without_city_allowlists(
    text, field, expected_country, expected_codes
):
    result = airport_context_for_field(text, field)
    assert result
    assert {item["country"] for item in result} == {expected_country}
    assert expected_codes <= {item["code"] for item in result}


def test_unresolved_qualifier_stays_ambiguous_instead_of_using_dominant_country():
    result = airport_context_for_field("Fly from Rome, Atlantis to Paris.", "origin_airports")
    codes = {item["code"] for item in result}
    assert {"FCO", "REO", "RME", "RMG"} <= codes


def test_field_context_does_not_reuse_the_other_endpoint():
    assert airport_context_for_field("Arrive at MCO or MIA.", "origin_airports") == []
    assert [item["code"] for item in airport_context_for_field(
        "Depart from EWR or JFK.", "destination_airports"
    )] == []


def test_latest_departure_correction_updates_origin_and_preserves_arrival():
    text = "Fly from London to Toronto.\nActually depart from Tokyo."
    assert airport_field_scope(text, "origin_airports") == "Tokyo"
    assert airport_field_scope(text, "destination_airports") == "Toronto"
    assert {item["code"] for item in airport_context_for_field(text, "origin_airports")} == {"HND", "NRT"}
    assert {item["code"] for item in airport_context_for_field(text, "destination_airports")} == {"YTZ", "YYZ"}


def test_latest_arrival_correction_updates_destination_and_preserves_departure():
    text = "Fly from London to Toronto.\nActually arrive at Ottawa."
    assert airport_field_scope(text, "origin_airports") == "London"
    assert airport_field_scope(text, "destination_airports") == "Ottawa"
    assert {item["code"] for item in airport_context_for_field(text, "origin_airports")} >= {"LHR", "LGW"}
    assert {item["code"] for item in airport_context_for_field(text, "destination_airports")} >= {"YOW"}


def test_casual_reference_to_an_earlier_airport_does_not_change_the_other_endpoint():
    text = "Arrive at YYZ.\nI already gave airport from Toronto."
    assert airport_context_for_field(text, "destination_airports")[0]["code"] == "YYZ"
    assert airport_context_for_field(text, "origin_airports") == []


def test_route_grounding_rejects_cross_endpoint_airports():
    text = "Book me a nonstop flight from london to toronto on 2026-11-12 under $300."
    with pytest.raises(GroundingFailure):
        validate_extraction(
            "flight",
            text,
            envelope(
                {"origin_airports": ["LHR", "YYZ"]},
                {"origin_airports": text},
            ),
        )
    with pytest.raises(GroundingFailure):
        validate_extraction(
            "flight",
            text,
            envelope(
                {"destination_airports": ["YTZ", "LHR"]},
                {"destination_airports": text},
            ),
        )


def test_route_grounding_preserves_explicit_multi_airport_choices():
    text = "Depart from EWR or JFK; arrive at MCO or MIA."
    result = validate_extraction(
        "flight",
        text,
        envelope(
            {"origin_airports": ["EWR", "JFK"], "destination_airports": ["MCO", "MIA"]},
            {"origin_airports": text, "destination_airports": text},
        ),
    )
    assert result["fields"] == {
        "origin_airports": ["EWR", "JFK"],
        "destination_airports": ["MCO", "MIA"],
    }


def test_compact_route_scope_supports_explicit_iata_codes():
    text = "EWR to MCO under $300"
    result = validate_extraction(
        "flight",
        text,
        envelope(
            {"origin_airports": ["EWR"], "destination_airports": ["MCO"]},
            {"origin_airports": text, "destination_airports": text},
        ),
    )
    assert result["fields"] == {
        "origin_airports": ["EWR"],
        "destination_airports": ["MCO"],
    }


@pytest.mark.parametrize(
    "text",
    [
        "I want to go to Toronto from London",
        "Depart London, arrive Toronto.",
        "leaving London and arriving Toronto",
        "London → Toronto",
    ],
)
def test_common_route_phrasings_keep_origin_and_destination_scoped(text):
    origin = airport_context_for_field(text, "origin_airports")
    destination = airport_context_for_field(text, "destination_airports")
    assert origin and destination
    assert {item["country"] for item in origin} == {"GB"}
    assert {item["country"] for item in destination} == {"CA"}
    assert {item["code"] for item in destination} == {"YTZ", "YYZ"}


@pytest.mark.parametrize(
    ("text", "field", "wrong_code"),
    [
        ("I want to go to Toronto from London", "origin_airports", "YYZ"),
        ("I want to go to Toronto from London", "destination_airports", "LHR"),
        ("Depart London, arrive Toronto.", "origin_airports", "YYZ"),
        ("Depart London, arrive Toronto.", "destination_airports", "LHR"),
        ("leaving London and arriving Toronto", "origin_airports", "YYZ"),
        ("leaving London and arriving Toronto", "destination_airports", "LHR"),
        ("London → Toronto", "origin_airports", "YYZ"),
        ("London → Toronto", "destination_airports", "LHR"),
    ],
)
def test_route_grounding_rejects_cross_endpoint_candidates(text, field, wrong_code):
    with pytest.raises(GroundingFailure):
        validate_extraction(
            "flight",
            text,
            envelope({field: [wrong_code]}, {field: text}),
        )


@pytest.mark.parametrize(
    ("text", "field", "code", "place"),
    [
        ("Book a flight from London to Toronto.", "origin_airports", "LHR", "London"),
        ("Book a flight from London to Toronto.", "destination_airports", "YYZ", "Toronto"),
    ],
)
def test_city_quote_does_not_authorize_model_selected_airport(text, field, code, place):
    result = validate_extraction(
        "flight",
        text,
        envelope({field: [code]}, {field: place}),
    )
    assert field not in result["fields"]
    assert any(item["field"] == field and item["reason"] == "ambiguous"
               for item in result["clarifications"])


def test_explicit_airport_name_and_code_remain_grounded():
    text = "Book a flight from London Heathrow (LHR) to Toronto."
    result = validate_extraction(
        "flight",
        text,
        envelope(
            {"origin_airports": ["LHR"]},
            {"origin_airports": "London Heathrow (LHR)"},
        ),
    )
    assert result["fields"]["origin_airports"] == ["LHR"]


def test_city_quote_does_not_authorize_complete_inferred_london_set():
    text = "Book a flight from London to Toronto."
    codes = [item["code"] for item in airport_context_for_field("London", "origin_airports")]
    result = validate_extraction(
        "flight",
        text,
        envelope({"origin_airports": codes}, {"origin_airports": "London"}),
    )
    assert "origin_airports" not in result["fields"]
    assert result["clarifications"] == [{
        "field": "origin_airports",
        "source_quote": "London",
        "reason": "ambiguous",
    }]


def test_city_quote_does_not_authorize_complete_inferred_toronto_set():
    text = "Book a flight from London to Toronto."
    result = validate_extraction(
        "flight",
        text,
        envelope(
            {"destination_airports": ["YYZ", "YTZ"]},
            {"destination_airports": "Toronto"},
        ),
    )
    assert "destination_airports" not in result["fields"]
    assert result["clarifications"] == [{
        "field": "destination_airports",
        "source_quote": "Toronto",
        "reason": "ambiguous",
    }]


def test_explicit_code_mixed_with_city_does_not_narrow_the_city_silently():
    text = "Book a flight from LCY or London to Toronto."
    result = validate_extraction(
        "flight",
        text,
        envelope(
            {"origin_airports": ["LCY", "LHR"]},
            {"origin_airports": "LCY or London"},
        ),
    )
    assert "origin_airports" not in result["fields"]
    assert result["clarifications"] == [{
        "field": "origin_airports",
        "source_quote": "LCY or London",
        "reason": "ambiguous",
    }]
