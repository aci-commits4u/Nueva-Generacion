"""Reference catalogue behavior: exact, bounded, and ambiguity-preserving."""

import pytest

from app.airport_reference import (
    AIRPORTS_DATA_LICENSE,
    AIRPORTS_DATA_SOURCE_URL,
    AIRPORTS_DATA_VERSION,
    airport_context,
    airport_record,
    airport_records,
    airport_reference_metadata,
    codes_for_place,
    quote_supports_airport,
    search_airports,
)


def test_catalogue_has_identity_records_from_pinned_package():
    records = airport_records()
    assert records["EWR"] == {
        "code": "EWR",
        "name": "Newark Liberty International Airport",
        "city": "Newark",
        "region": "New Jersey",
        "country": "US",
    }
    assert all(len(code) == 3 and code.isupper() for code in records)
    assert all(set(record) == {"code", "name", "city", "region", "country"} for record in records.values())
    assert airport_record("ewr") == records["EWR"]
    assert airport_record("unknown") is None


def test_exact_city_and_airport_names_return_codes_without_fuzzy_guessing():
    assert {"CDG", "ORY"}.issubset(codes_for_place("Paris"))
    assert codes_for_place("London Heathrow Airport") == ["LHR"]
    assert codes_for_place("Heathrow") == ["LHR"]
    assert codes_for_place("Charles de Gaulle International Airport") == ["CDG"]
    assert codes_for_place("not a real place") == []


def test_diacritics_and_balanced_parenthetical_qualifier_are_normalized():
    assert codes_for_place("Bíldudalur") == codes_for_place("Bildudalur") == ["BIU"]
    assert codes_for_place("Paris (France)") == codes_for_place("Paris")
    assert codes_for_place("Paris (France") == []


def test_multi_airport_cities_remain_ambiguous():
    tokyo = codes_for_place("Tokyo")
    assert {"HND", "NRT"}.issubset(tokyo)
    assert len(tokyo) > 1
    assert {"JFK", "LGA"}.issubset(codes_for_place("New York"))


def test_quote_support_requires_code_or_trusted_literal_phrase():
    assert quote_supports_airport("LAX", "Fly to LAX tomorrow")
    assert quote_supports_airport("LAX", "Fly to Los Angeles tomorrow")
    assert quote_supports_airport("LHR", "London Heathrow is acceptable")
    assert quote_supports_airport("LHR", "Heathrow is acceptable")
    assert not quote_supports_airport("LAX", "The fare is relaxingly cheap")
    assert not quote_supports_airport("MCO", "I want an airport in Florida")
    assert not quote_supports_airport("ZZZ", "ZZZ")


def test_search_is_bounded_and_prioritizes_exact_code():
    assert search_airports("LAX", limit=1)[0]["code"] == "LAX"
    assert search_airports("Florida", limit=12)
    assert len(search_airports("airport", limit=25)) <= 25
    with pytest.raises(ValueError):
        search_airports("Tokyo", limit=26)


def test_context_uses_explicit_codes_city_phrases_and_bounded_region_hints():
    context = airport_context("Fly from Newark to Tokyo, or maybe HND; Florida is also okay.")
    codes = [record["code"] for record in context]
    assert codes[0] == "HND"
    assert "EWR" in codes
    assert "HND" in codes
    assert "NRT" in codes
    assert {"MCO", "MIA", "TPA", "FLL"}.issubset(codes)
    assert len(codes) <= 30


def test_date_word_does_not_ground_friday_harbor_but_full_place_does():
    assert "FRD" not in [record["code"] for record in airport_context("next Friday")]
    assert "FRD" in [record["code"] for record in airport_context("Friday Harbor")]


def test_region_context_never_becomes_a_single_airport_and_limit_is_strict():
    context = airport_context("Florida", limit=2)
    assert [record["code"] for record in context] == ["MCO", "MIA"]
    assert len(airport_context("Florida", limit=30)) == 4
    with pytest.raises(ValueError):
        airport_context("Florida", limit=31)


def test_metadata_records_public_provenance():
    metadata = airport_reference_metadata()
    assert metadata["package"] == "airportsdata"
    assert metadata["version"] == AIRPORTS_DATA_VERSION == "20260905"
    assert metadata["source"] == AIRPORTS_DATA_SOURCE_URL
    assert metadata["license"] == AIRPORTS_DATA_LICENSE == "MIT"

