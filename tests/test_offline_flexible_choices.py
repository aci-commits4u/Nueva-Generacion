"""Offline typed widget choices retain every explicitly selected option."""

from app.intent_service import offline_extract


def test_departure_widget_keeps_all_trusted_airports_and_exact_source():
    result = offline_extract("flight", "Depart from EWR or JFK.")

    assert result["fields"]["origin_airports"] == ["EWR", "JFK"]
    assert result["sources"]["origin_airports"] == "Depart from EWR or JFK."
    assert result["unsupported"] == []


def test_arrival_widget_keeps_all_trusted_airports_and_exact_source():
    result = offline_extract("flight", "Arrive at MCO or MIA.")

    assert result["fields"]["destination_airports"] == ["MCO", "MIA"]
    assert result["sources"]["destination_airports"] == "Arrive at MCO or MIA."
    assert result["unsupported"] == []


def test_travel_between_widget_preserves_the_full_inclusive_range():
    result = offline_extract(
        "flight", "Travel between 2026-11-12 and 2026-11-14, inclusive."
    )

    assert result["fields"]["departure_date"] == {
        "start": "2026-11-12", "end": "2026-11-14"
    }
    assert result["sources"]["departure_date"] == (
        "Travel between 2026-11-12 and 2026-11-14, inclusive."
    )
    assert result["unsupported"] == []


def test_travel_or_widget_preserves_discrete_date_alternatives():
    result = offline_extract("flight", "Travel 2026-11-12 or 2026-11-14.")

    assert result["fields"]["departure_date"] == {
        "dates": ["2026-11-12", "2026-11-14"]
    }
    assert result["sources"]["departure_date"] == "Travel 2026-11-12 or 2026-11-14."
    assert result["unsupported"] == []


def test_latest_typed_corrections_replace_prior_choices_but_unknown_text_stays_held():
    message = (
        "Depart from EWR.\n"
        "Depart from EWR or JFK.\n"
        "Travel between 2026-11-12 and 2026-11-14, inclusive.\n"
        "Travel 2026-11-13 or 2026-11-15.\n"
        "with a checked bag"
    )
    result = offline_extract("flight", message)

    assert result["fields"]["origin_airports"] == ["EWR", "JFK"]
    assert result["sources"]["origin_airports"] == "Depart from EWR or JFK."
    assert result["fields"]["departure_date"] == {
        "dates": ["2026-11-13", "2026-11-15"]
    }
    assert result["sources"]["departure_date"] == "Travel 2026-11-13 or 2026-11-15."
    assert result["unsupported"] == [message]


def test_unknown_or_oversized_typed_choice_does_not_fall_back_to_first_value():
    result = offline_extract("flight", "Depart from EWR or USA.")

    assert "origin_airports" not in result["fields"]
    assert result["unsupported"] == ["Depart from EWR or USA."]

