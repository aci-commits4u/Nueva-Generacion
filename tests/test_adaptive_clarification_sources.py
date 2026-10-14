"""Fail-closed adaptive envelope repairs for source-backed clarifications."""

import pytest


def _hotel_envelope(*, source_quote="under $220 per night", clarification_quote=None):
    clarification_quote = clarification_quote or source_quote
    return {
        "fields": {
            "city": "Boston",
            "checkin_date": "2026-11-12",
            "checkout_date": "2026-11-14",
        },
        "sources": {
            "city": "Boston",
            "checkin_date": "November 12, 2026",
            "checkout_date": "November 14, 2026",
            "max_total_cents": source_quote,
        },
        "unsupported": [],
        "clarifications": [{
            "field": "max_total_cents",
            "source_quote": clarification_quote,
            "reason": "ambiguity",
        }],
        "explanation": "Review the stay price basis.",
        "action": "ask_user",
        "assistant_message": "What all-in total should apply to the stay?",
        "question": {
            "criterion_key": "max_total_cents",
            "field": "max_total_cents",
            "text": "What all-in total should apply to the stay?",
            "why": "The customer supplied a nightly amount.",
            "answer_kind": "text",
        },
        "criteria": [{
            "key": "max_total_cents",
            "field": None,
            "text": "under $220 per night",
            "source_quote": source_quote,
            "kind": "ambiguity",
            "status": "needs_clarification",
            "verification": "unsupported",
        }],
    }


def test_orphan_source_is_removed_only_for_matching_grounded_clarification():
    from app.ai_pipeline import _compile_adaptive_draft_contract
    from app.adaptive_intent import strip_plan_metadata

    message = "Book a hotel in Boston for November 12 through November 14 under $220 per night."
    result = _compile_adaptive_draft_contract(
        _hotel_envelope(), domain="hotel", source_text=message,
    )

    assert "max_total_cents" not in result["sources"]
    assert result["clarifications"] == [{
        "field": "max_total_cents",
        "source_quote": "under $220 per night",
        "reason": "ambiguous",
    }]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda draft: draft["clarifications"].__setitem__(
            0, {**draft["clarifications"][0], "source_quote": "under $180 per night"}
        ),
        lambda draft: draft["clarifications"].__setitem__(
            0, {**draft["clarifications"][0], "field": "city"}
        ),
        lambda draft: draft["clarifications"].__setitem__(
            0, {**draft["clarifications"][0], "source_quote": "merchant says $220"}
        ),
    ],
)
def test_mismatched_or_untrusted_orphan_source_remains_fail_closed(mutate):
    from app.ai_pipeline import _compile_adaptive_draft_contract
    from app.adaptive_intent import strip_plan_metadata
    from app.ai_grounding import validate_extraction

    message = "Book a hotel in Boston for November 12 through November 14 under $220 per night."
    draft = _hotel_envelope()
    mutate(draft)
    result = _compile_adaptive_draft_contract(
        draft, domain="hotel", source_text=message,
    )

    assert result["sources"]["max_total_cents"] == "under $220 per night"
    with pytest.raises(ValueError):
        validate_extraction("hotel", message, strip_plan_metadata(result))


def test_unknown_orphan_key_is_never_laundered_by_a_generic_clarification():
    from app.ai_pipeline import _compile_adaptive_draft_contract
    from app.adaptive_intent import strip_plan_metadata
    from app.ai_grounding import validate_extraction

    message = "Book a hotel in Boston for November 12 through November 14 under $220 per night."
    draft = _hotel_envelope()
    draft["sources"]["price_limit_basis"] = "under $220 per night"
    draft["clarifications"][0]["field"] = "price_limit_basis"
    result = _compile_adaptive_draft_contract(
        draft, domain="hotel", source_text=message,
    )

    assert result["sources"]["price_limit_basis"] == "under $220 per night"
    with pytest.raises(ValueError):
        validate_extraction("hotel", message, strip_plan_metadata(result))


def test_structured_question_rejects_unregistered_price_basis_alias():
    from app.structured_intent import build_source_catalog, hydrate_response

    catalog = build_source_catalog("A hotel under $220 per night.")
    wire = {
        "supported_claims": [], "unsupported": [], "clarifications": [],
        "criteria": [], "action": "ask_user", "assistant_message": "What total?",
        "explanation": "Review the budget.", "offer_observations": [],
        "question": {
            "criterion_key": "price_limit_basis",
            "text": "What all-in total should I use?", "why": "The total is missing.",
            "answer_kind": "number", "answer_semantics": None, "options": [],
        },
    }
    with pytest.raises(ValueError, match="out of scope"):
        hydrate_response(wire, domain="hotel", catalog=catalog, require_wire=True)


def test_structured_shared_range_source_grounds_both_hotel_endpoints():
    from app.ai_grounding import validate_extraction
    from app.adaptive_intent import strip_plan_metadata
    from app.structured_intent import build_source_catalog, hydrate_response

    message = "A hotel in Boston for November 2–4, 2026."
    catalog = build_source_catalog(message)
    reference = next(item["id"] for item in catalog if item["text"] == message)
    wire = {
        "supported_claims": [
            {"field": "city", "value": "Boston", "source_ref": reference},
            {"field": "checkin_date", "value": "2026-11-02", "source_ref": reference},
            {"field": "checkout_date", "value": "2026-11-04", "source_ref": reference},
        ],
        "unsupported": [], "clarifications": [], "criteria": [],
        "action": "review_required", "assistant_message": "Review the dates.",
        "question": None, "explanation": "Review the captured requirements.",
        "offer_observations": [],
    }
    result = hydrate_response(wire, domain="hotel", catalog=catalog, require_wire=True)
    checked = validate_extraction("hotel", message, strip_plan_metadata(result))
    assert checked["fields"]["checkin_date"] == "2026-11-02"
    assert checked["fields"]["checkout_date"] == "2026-11-04"
    assert checked["sources"]["checkin_date"] == message
    assert checked["sources"]["checkout_date"] == message

