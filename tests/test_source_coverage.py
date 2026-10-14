"""Offline tests for latest-turn literal coverage retention."""

from copy import deepcopy

import pytest


def _criterion(key, quote, *, field=None, kind="requirement", verification="supported"):
    return {
        "key": key,
        "field": field,
        "text": quote,
        "source_quote": quote,
        "kind": kind,
        "status": "captured" if field else "needs_clarification",
        "verification": verification,
    }


def _adaptive_response(*, criteria, source_text):
    return {
        "action": "ask_user",
        "assistant_message": "I need one useful detail before continuing.",
        "question": {
            "criterion_key": "max_total_cents",
            "field": "max_total_cents",
            "text": "What all-in USD total should I use for the stay?",
            "why": "The total changes which offers can satisfy the request.",
            "answer_kind": "number",
            "options": [],
        },
        "criteria": criteria,
        "offer_observations": [],
        "fields": {
            "city": "Tbilisi",
            "checkin_date": "2027-04-03",
            "checkout_date": "2027-04-07",
        },
        "sources": {
            "city": "Tbilisi",
            "checkin_date": "check in on April 3, 2027",
            "checkout_date": "check out April 7, 2027",
        },
        "unsupported": [],
        "clarifications": [],
        "explanation": "Review the captured requirements.",
    }


def _coverage(latest, final, *, current=None, source_text=None):
    from app.source_coverage import audit_latest_turn

    source_text = source_text or latest
    return audit_latest_turn(
        latest,
        source_text=source_text,
        source_messages=[{"role": "user", "content": latest}],
        current_draft=current or {},
        candidate=final,
        final=final,
        final_raw=final,
    )


def test_both_model_roles_omit_new_cap_and_extension_but_flags_are_held(
    monkeypatch,
):
    from app.ai_pipeline import run_pipeline

    monkeypatch.setenv("MOCK_LLM", "0")
    latest = (
        "Set check in on April 3, 2027 and check out April 7, 2027. "
        "Keep a separate $175 USD all-in nightly cap including taxes and fees "
        "for enforcement, with the option to extend to April 8 for five nights."
    )
    criteria = [
        _criterion("city", "Tbilisi", field="city"),
        _criterion("checkin_date", "check in on April 3, 2027", field="checkin_date"),
        _criterion("checkout_date", "check out April 7, 2027", field="checkout_date"),
    ]
    candidate = _adaptive_response(criteria=criteria, source_text=latest)
    reviewed = deepcopy(candidate)
    calls = []

    monkeypatch.setattr("app.ai_pipeline.reserve_ai_calls", lambda *args, **kwargs: 2)

    def fake_call(stage, *args, **kwargs):
        calls.append(stage)
        return deepcopy(candidate if stage == "adaptive_plan" else reviewed), {"stage": stage}

    monkeypatch.setattr("app.ai_pipeline.call_json", fake_call)
    result = run_pipeline(
        "hotel", latest, "literal-coverage-session", variant="adaptive",
        source_text=latest,
        source_messages=[{"role": "user", "content": latest}],
        current_draft={"latest_customer_turn": {"content": latest}},
    )

    assert calls == ["adaptive_plan", "adaptive_review"]
    assert "Keep a separate $175 USD all-in nightly cap including taxes and fees for enforcement" in result["unsupported"]
    assert "with the option to extend to April 8 for five nights" in result["unsupported"]
    assert result["fields"]["checkin_date"] == "2027-04-03"
    assert result["fields"]["checkout_date"] == "2027-04-07"
    assert result["trace"][1]["latest_turn_coverage"]["codes"] == [
        "latest_turn_unrepresented_money",
        "latest_turn_unrepresented_date",
    ]


def test_covered_date_answer_and_airport_correction_do_not_add_flags():
    latest = "Change departure to April 8, 2027 instead of April 7; depart from LCY or LHR."
    final = {
        "fields": {
            "departure_date": "2027-04-08",
            "origin_airports": ["LCY", "LHR"],
        },
        "sources": {
            "departure_date": "April 8, 2027 instead of April 7",
            "origin_airports": "depart from LCY or LHR",
        },
        "unsupported": [],
        "clarifications": [],
        "criteria": [],
    }

    result = _coverage(latest, final)

    assert result["flags"] == []
    assert result["diagnostics"]["unrepresented_dates"] == 0


def test_date_correction_with_only_new_date_source_has_no_false_optional_flag():
    latest = "Use April 8, 2027 instead of April 7."
    final = {
        "fields": {"departure_date": "2027-04-08"},
        "sources": {"departure_date": "April 8, 2027"},
        "unsupported": [],
        "clarifications": [],
        "criteria": [],
    }

    assert _coverage(latest, final)["flags"] == []


def test_correction_verb_from_to_suppresses_old_date():
    latest = "Change the stay from April 7 to April 8, 2027."
    final = {
        "fields": {"departure_date": "2027-04-08"},
        "sources": {"departure_date": "April 8, 2027"},
        "unsupported": [],
        "clarifications": [],
        "criteria": [],
    }

    assert _coverage(latest, final)["flags"] == []


def test_ordinary_from_to_range_keeps_old_date_literal():
    latest = "Stay from April 7 to April 8, 2027."
    final = {
        "fields": {"departure_date": "2027-04-08"},
        "sources": {"departure_date": "April 8, 2027"},
        "unsupported": [],
        "clarifications": [],
        "criteria": [],
    }

    result = _coverage(latest, final)
    assert result["diagnostics"]["unrepresented_dates"] == 1
    assert result["flags"] == ["Stay from April 7 to April 8, 2027"]


def test_rejected_raw_profile_date_criterion_cannot_cover_latest_extension():
    from app.source_coverage import audit_latest_turn

    latest = "Keep check out April 7, 2027, with the option to extend to April 8."
    grounded_final = {
        "fields": {"checkout_date": "2027-04-07"},
        "sources": {"checkout_date": "check out April 7, 2027"},
        "unsupported": [],
        "clarifications": [],
        "criteria": [],
    }
    rejected_raw = {
        "criteria": [_criterion(
            "checkout_date", "April 8", field="checkout_date",
        )],
    }

    result = audit_latest_turn(
        latest,
        source_text=latest,
        source_messages=[{"role": "user", "content": latest}],
        current_draft={}, candidate=rejected_raw, final=grounded_final,
        final_raw=rejected_raw,
    )

    assert result["flags"] == ["with the option to extend to April 8"]


def test_money_identity_keeps_currency_and_unit_distinct():
    latest = "Use USD $300 total and USD $300 per night."
    final = {
        "fields": {},
        "sources": {},
        "unsupported": ["USD $300 total"],
        "clarifications": [],
        "criteria": [],
    }

    result = _coverage(latest, final)

    assert result["flags"] == ["USD $300 per night"]
    assert result["diagnostics"]["unrepresented_money"] == 1
    assert _coverage(
        "Use EUR 140 per night.",
        {**final, "unsupported": ["USD 140 per night"]},
    )["flags"] == ["Use EUR 140 per night"]


def test_adjacent_literals_keep_local_optional_and_unit_context():
    from app.source_coverage import extract_literals

    latest = (
        "April 3, 2027 and April 7, 2027 with the option to extend to April 8. "
        "Keep USD $700 total and USD $175 per night."
    )
    literals = extract_literals(latest)
    dates = [item for item in literals if item["kind"] == "date"]
    money = [item for item in literals if item["kind"] == "money"]

    assert [(item["day"], item["optional"]) for item in dates] == [
        (3, False), (7, False), (8, True),
    ]
    assert [(item["amount"], item["unit"]) for item in money] == [
        ("700", "total"), ("175", "nightly"),
    ]


def test_three_adjacent_money_units_do_not_share_context():
    from app.source_coverage import extract_literals

    literals = extract_literals(
        "Use $100 per item and $200 total and $300 nightly."
    )

    assert [(item["amount"], item["unit"]) for item in literals] == [
        ("100", "item"), ("200", "total"), ("300", "nightly"),
    ]


def test_generic_iso_date_and_arbitrary_city_are_covered_without_guessing():
    latest = "Find a stay in Nuku'alofa for 2027-04-08."
    final = {
        "fields": {},
        "sources": {},
        "unsupported": [],
        "clarifications": [],
        "criteria": [_criterion("event_date", "2027-04-08", verification="unsupported")],
    }

    assert _coverage(latest, final)["flags"] == []
    assert _coverage(
        "Find a stay in Nuku'alofa.",
        {**final, "criteria": [], "unsupported": []},
    )["flags"] == []


def test_merchant_only_literal_cannot_cover_customer_literal():
    latest = "Keep a $175 nightly cap."
    final = {
        "fields": {},
        "sources": {},
        "unsupported": ["Merchant says a $175 nightly cap is available."],
        "clarifications": [],
        "criteria": [{
            **_criterion("merchant_cap", "Merchant says a $175 nightly cap is available.", verification="unsupported"),
        }],
    }

    result = _coverage(latest, final)

    assert result["flags"] == ["Keep a $175 nightly cap"]


def test_money_clause_retains_semantic_operator():
    result = _coverage(
        "Do not exceed $175 per night.",
        {
            "fields": {},
            "sources": {},
            "unsupported": [],
            "clarifications": [],
            "criteria": [],
        },
    )

    assert result["flags"] == ["Do not exceed $175 per night"]


def test_literal_coverage_overflow_fails_without_truncating_flags():
    from app.source_coverage import audit_latest_turn

    latest = " ".join(f"Keep ${index} per night." for index in range(1, 22))
    with pytest.raises(ValueError, match="Too many latest-turn literal coverage flags"):
        audit_latest_turn(
            latest,
            source_text=latest,
            source_messages=[{"role": "user", "content": latest}],
            current_draft={}, candidate={}, final={}, final_raw={},
        )
