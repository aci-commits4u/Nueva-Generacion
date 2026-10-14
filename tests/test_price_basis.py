"""Regression coverage for unit-priced amounts versus all-in totals."""

import pytest


def _draft(*, fields=None, sources=None, unsupported=None, clarifications=None):
    return {
        "fields": fields or {},
        "sources": sources or {},
        "unsupported": unsupported or [],
        "clarifications": clarifications or [],
        "explanation": "Review the captured requirements.",
    }


@pytest.mark.parametrize("basis", ["per night", "per person", "per room", "per unit"])
def test_unit_price_never_becomes_all_in_total(basis):
    from app.ai_grounding import validate_extraction

    message = f"Book a hotel in Boston under $220 {basis}."
    result = validate_extraction(
        "hotel",
        message,
        _draft(
            fields={"max_total_cents": 21999},
            sources={"max_total_cents": f"under $220 {basis}"},
        ),
    )
    assert "max_total_cents" not in result["fields"]
    assert any(basis in item for item in result["unsupported"])


def test_omitted_unit_suffix_is_recovered_from_customer_source_context():
    from app.ai_grounding import validate_extraction

    message = "Book a quiet hotel in Boston under $220 per night."
    result = validate_extraction(
        "hotel",
        message,
        _draft(
            fields={"max_total_cents": 21999},
            sources={"max_total_cents": "under $220"},
        ),
    )
    assert "max_total_cents" not in result["fields"]
    assert "under $220 per night" in result["unsupported"]


@pytest.mark.parametrize(
    ("message", "quote", "expected"),
    [
        (
            "Book a hotel in Boston nightly under $220.",
            "under $220",
            "nightly under $220",
        ),
        (
            "Book a hotel in Boston at a nightly rate under$220.",
            "under$220",
            "nightly rate under$220",
        ),
        (
            "Book a hotel in Boston under$220 for each night.",
            "under$220",
            "under$220 for each night",
        ),
        (
            "Book a hotel in Boston nightly, under $220.",
            "under $220",
            "nightly, under $220",
        ),
        (
            "Book a hotel in Boston nightly: under$220.",
            "under$220",
            "nightly: under$220",
        ),
        (
            "Book a hotel in Boston at a nightly rate, under$220.",
            "under$220",
            "nightly rate, under$220",
        ),
        (
            "Book a hotel in Boston under$220 a night.",
            "under$220",
            "under$220 a night",
        ),
        (
            "Book a hotel in Boston nightly maximum under$220.",
            "under$220",
            "nightly maximum under$220",
        ),
    ],
)
def test_unit_price_adjacent_prefix_or_suffix_is_not_an_all_in_total(
    message, quote, expected
):
    from app.ai_grounding import validate_extraction

    result = validate_extraction(
        "hotel",
        message,
        _draft(
            fields={"max_total_cents": 21999},
            sources={"max_total_cents": quote},
        ),
    )
    assert "max_total_cents" not in result["fields"]
    assert expected in result["unsupported"]


def test_separate_explicit_all_in_total_is_not_cross_bound_to_nightly_price():
    from app.ai_grounding import validate_extraction

    message = (
        "Book a hotel nightly under $220, but keep the full stay under $440 all in."
    )
    result = validate_extraction(
        "hotel",
        message,
        _draft(
            fields={"max_total_cents": 43999},
            sources={"max_total_cents": "under $440"},
        ),
    )
    assert result["fields"]["max_total_cents"] == 43999
    assert result["unsupported"] == []


def test_offline_parser_cannot_bypass_unit_price_guard():
    from app.intent_service import offline_extract

    result = offline_extract("hotel", "Book a hotel in Boston nightly under $220.")
    assert "max_total_cents" not in result["fields"]
    assert "nightly under $220" in result["unsupported"]


def test_adaptive_criterion_does_not_call_unit_price_supported():
    from app.adaptive_intent import normalize_plan

    message = "Book a hotel in Boston under $220 per night."
    plan = normalize_plan(
        {
            "action": "ask_user",
            "assistant_message": "What all-in total should apply to the full stay?",
            "question": {
                "criterion_key": "max_total_cents",
                "field": "max_total_cents",
                "text": "What all-in total should apply to the full stay?",
                "why": "The nightly amount is not an all-in total.",
                "answer_kind": "number",
            },
            "criteria": [{
                "key": "max_total_cents",
                "field": "max_total_cents",
                "text": "under $220 per night",
                "source_quote": "under $220 per night",
                "kind": "requirement",
                "status": "captured",
                "verification": "supported",
            }],
            "fields": {"max_total_cents": 21999},
            "sources": {"max_total_cents": "under $220 per night"},
            "unsupported": [],
            "clarifications": [],
            "explanation": "Review the captured requirements.",
        },
        domain="hotel",
        source_text=message,
    )
    criterion = next(item for item in plan["criteria"] if item["key"] == "max_total_cents")
    assert criterion["verification"] == "unsupported"
    assert criterion["status"] == "needs_clarification"
    assert criterion["field"] is None
    assert plan["question"]["field"] == "max_total_cents"


def test_all_in_stay_total_remains_a_grounded_total():
    from app.ai_grounding import validate_extraction

    result = validate_extraction(
        "hotel",
        "Book a hotel in Boston for the full stay under $440 all in.",
        _draft(
            fields={"max_total_cents": 43999},
            sources={"max_total_cents": "under $440"},
        ),
    )
    assert result["fields"]["max_total_cents"] == 43999
    assert result["unsupported"] == []


def test_unit_price_clarification_is_not_promoted_or_multiplied():
    from app.ai_grounding import validate_extraction

    quote = "under $220 per night"
    result = validate_extraction(
        "hotel",
        "Book a hotel in Boston under $220 per night.",
        _draft(
            clarifications=[{
                "field": "max_total_cents",
                "source_quote": quote,
                "reason": "ambiguous",
            }],
        ),
    )
    assert "max_total_cents" not in result["fields"]
    assert result["clarifications"] == [{
        "field": "max_total_cents",
        "source_quote": quote,
        "reason": "ambiguous",
    }]
    assert quote in result["unsupported"]


def test_hotel_context_exposes_all_in_price_basis():
    from app.adaptive_intent import merchant_context, prompt_context

    context = merchant_context("hotel")
    assert "all-in total" in context["policies"]["price_basis"]
    assert any("all-in total" in rule for rule in prompt_context("hotel")["interpretation_rules"])
