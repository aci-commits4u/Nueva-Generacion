"""Flight date approvals accept one date or a bounded inclusive date window."""

import pytest

from app.profile_registry import get_profile, validate_fields
from app.rules_engine import evaluate
from app.vi_adapter import read_signed
from demo.fixtures import offers_for


def date_rule(requirement, fact):
    return evaluate(
        get_profile("flight"),
        {"departure_date": requirement},
        {"departure_date": fact},
    )


def test_existing_exact_iso_date_remains_supported():
    result = date_rule("2026-10-14", "2026-10-14")
    assert result["status"] == "PASS"


@pytest.mark.parametrize(
    ("fact", "status"),
    [
        ("2026-10-14", "PASS"),  # inclusive start
        ("2026-10-21", "PASS"),  # inclusive end
        ("2026-10-22", "HOLD"),
    ],
)
def test_date_range_is_inclusive_and_holds_outside_fact(fact, status):
    result = date_rule({"start": "2026-10-14", "end": "2026-10-21"}, fact)
    assert result["status"] == status


@pytest.mark.parametrize(
    ("fact", "status"),
    [("2026-10-14", "PASS"), ("2026-10-21", "PASS"), ("2026-10-15", "HOLD")],
)
def test_discrete_date_alternatives_do_not_create_a_continuous_window(fact, status):
    result = date_rule({"dates": ["2026-10-14", "2026-10-21"]}, fact)
    assert result["status"] == status


@pytest.mark.parametrize("fact", [None, "October 14, 2026", "2026-10-14T09:00:00"])
def test_missing_or_invalid_merchant_date_never_passes(fact):
    result = date_rule({"start": "2026-10-14", "end": "2026-10-21"}, fact)
    assert result["status"] == "HOLD"
    assert result["checks"][0]["status"] == "missing"


@pytest.mark.parametrize(
    "value",
    [
        {"start": "2026-10-21", "end": "2026-10-14"},
        {"start": "2026-01-01", "end": "2027-01-03"},
        {"start": "2026-10-14", "end": "2026-10-21", "timezone": "local"},
        {"dates": ["2026-10-14", "2026-10-14"]},
        {"dates": ["2026-10-14"], "extra": True},
        {"dates": [["2026-10-14"]]},
        {"start": "2026-10-14"},
        {"start": "2026-10-14", "end": True},
        True,
    ],
)
def test_date_choice_approval_is_strict(value):
    with pytest.raises(ValueError):
        validate_fields(get_profile("flight"), {"departure_date": value})


def test_range_maximum_span_is_366_days():
    validate_fields(
        get_profile("flight"),
        {"departure_date": {"start": "2026-01-01", "end": "2027-01-02"}},
    )
    with pytest.raises(ValueError):
        validate_fields(
            get_profile("flight"),
            {"departure_date": {"start": "2026-01-01", "end": "2027-01-03"}},
        )


def test_synthetic_match_offer_uses_range_start_date():
    approved = {
        "id": "date-window-demo",
        "domain": "flight",
        "fields": {
            "departure_date": {"start": "2026-10-14", "end": "2026-10-21"},
        },
    }
    offer = read_signed(offers_for(approved)[0]["checkout_jwt"], "merchant", "intent-judge-checkout+jwt")
    assert offer["segments"][0]["departure"].startswith("2026-10-14T")
