"""Source-grounding tests for compressed hotel date ranges."""

import pytest


def _draft(fields, sources):
    return {
        "fields": fields,
        "sources": sources,
        "unsupported": [],
        "clarifications": [],
        "explanation": "Review the captured stay dates.",
    }


def test_whole_shared_year_range_supports_both_hotel_endpoints():
    from app.ai_grounding import validate_extraction

    message = "Book a hotel in Boston for November 2–4, 2026."
    range_quote = "November 2–4, 2026"
    result = validate_extraction(
        "hotel",
        message,
        _draft(
            {
                "checkin_date": "2026-11-02",
                "checkout_date": "2026-11-04",
            },
            {
                "checkin_date": range_quote,
                "checkout_date": range_quote,
            },
        ),
    )
    assert result["fields"] == {
        "checkin_date": "2026-11-02",
        "checkout_date": "2026-11-04",
    }


@pytest.mark.parametrize(
    ("message", "checkin", "checkout"),
    [
        ("Book a hotel in Boston for November 4–2, 2026.", "2026-11-04", "2026-11-02"),
        ("Book a hotel in Boston for November 2–December 4, 2026.", "2026-11-02", "2026-12-04"),
        ("Book a hotel in Boston for November 31–4, 2026.", "2026-11-31", "2026-11-04"),
    ],
)
def test_invalid_or_cross_month_shared_range_is_rejected(message, checkin, checkout):
    from app.ai_grounding import validate_extraction

    quote = message.split("for ", 1)[1].rstrip(".")
    with pytest.raises(ValueError):
        validate_extraction(
            "hotel",
            message,
            _draft(
                {"checkin_date": checkin, "checkout_date": checkout},
                {"checkin_date": quote, "checkout_date": quote},
            ),
        )


def test_shared_range_cannot_swap_checkin_and_checkout_endpoints():
    from app.ai_grounding import validate_extraction

    message = "Book a hotel in Boston for November 2–4, 2026."
    quote = "November 2–4, 2026"
    with pytest.raises(ValueError):
        validate_extraction(
            "hotel",
            message,
            _draft(
                {"checkin_date": "2026-11-04", "checkout_date": "2026-11-02"},
                {"checkin_date": quote, "checkout_date": quote},
            ),
        )


def test_flight_date_grounding_does_not_use_hotel_shared_range_rule():
    from app.ai_grounding import validate_extraction

    message = "Fly on November 2, 2026."
    result = validate_extraction(
        "flight",
        message,
        _draft(
            {"departure_date": "2026-11-02"},
            {"departure_date": "November 2, 2026"},
        ),
    )
    assert result["fields"]["departure_date"] == "2026-11-02"
