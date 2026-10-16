"""Small regressions for answered intent grounding and planner memory."""

from copy import deepcopy

import pytest

from app.ai_grounding import GroundingFailure, validate_extraction
from app.conversation import apply_adaptive_plan, merge_revision_state, questions


def _envelope(fields, sources, *, unsupported=None):
    return {
        "fields": fields,
        "sources": sources,
        "unsupported": unsupported or [],
        "clarifications": [],
        "explanation": "Review the captured requirements.",
    }


def _adaptive_draft(**overrides):
    draft = {
        "domain": "flight",
        "mode": "live",
        "pipeline": "adaptive",
        "fields": {
            "origin_airports": ["YYZ"],
            "destination_airports": ["LHR"],
            "departure_date": "2026-11-12",
            "max_total_cents": 79999,
        },
        "sources": {
            "origin_airports": "Toronto",
            "destination_airports": "London",
            "departure_date": "Nov 12, 2026",
            "max_total_cents": "less than 800 $",
        },
        "clarifications": [],
        "unsupported": [],
        "messages": [{
            "role": "user",
            "content": "Find a flight from Toronto to London on Nov 12, 2026 less than 800 $.",
        }],
    }
    draft.update(overrides)
    return draft


def _adaptive_extraction(*, question, criteria, draft, pipeline="adaptive"):
    return {
        "mode": "live",
        "pipeline": pipeline,
        "model": "test",
        "fields": deepcopy(draft["fields"]),
        "sources": deepcopy(draft["sources"]),
        "unsupported": list(draft.get("unsupported") or []),
        "clarifications": list(draft.get("clarifications") or []),
        "explanation": "Review the captured requirements.",
        "adaptive_plan": {
            "action": "ask_user",
            "assistant_message": "I need one decision before review.",
            "question": question,
            "criteria": criteria,
            "offer_observations": [],
        },
        "agent_tools": [],
    }


def test_literal_less_than_trailing_dollar_compiles_to_strict_integer_cents():
    result = validate_extraction(
        "general",
        "Keep the total less than 800 $.",
        _envelope(
            {"max_total_cents": 79999},
            {"max_total_cents": "less than 800 $"},
        ),
    )
    assert result["fields"]["max_total_cents"] == 79999


def test_no_layovers_is_a_zero_connection_bound_and_not_a_nonstop_inference():
    result = validate_extraction(
        "flight",
        "Find a flight also no layovers and less than 800 $.",
        _envelope(
            {"max_connections": 0, "max_total_cents": 79999},
            {
                "max_connections": "also no layovers",
                "max_total_cents": "less than 800 $",
            },
            unsupported=["also no layovers"],
        ),
    )
    assert result["fields"]["max_connections"] == 0
    assert "nonstop" not in result["fields"]
    assert result["unsupported"] == []


def test_foreign_currency_does_not_bypass_usd_grounding():
    with pytest.raises(GroundingFailure):
        validate_extraction(
            "general",
            "Keep it under €120 or under $120.",
            _envelope(
                {"max_total_cents": 11999},
                {"max_total_cents": "under $120"},
            ),
        )


def test_adaptive_nonstop_question_is_suppressed_by_same_source_zero_bound():
    draft = _adaptive_draft(
        fields={
            **_adaptive_draft()["fields"],
            "max_connections": 0,
        },
        sources={
            **_adaptive_draft()["sources"],
            "max_connections": "also no layovers",
        },
    )
    question = {
        "criterion_key": "nonstop",
        "field": "nonstop",
        "question": "Do you require a nonstop flight?",
        "why": "This changes which offers are acceptable.",
        "answer_kind": "boolean",
        "answer_semantics": "requirement_boolean",
        "options": ["Yes", "No"],
    }
    criterion = {
        "key": "nonstop",
        "field": "nonstop",
        "text": "no layovers",
        "source_quote": "also no layovers",
        "kind": "requirement",
        "verification": "supported",
        "status": "needs_clarification",
    }
    result = apply_adaptive_plan(
        draft,
        _adaptive_extraction(question=question, criteria=[criterion], draft=draft),
    )
    assert result["questions"] == []
    assert "nonstop" not in result["fields"]
    assert result["fields"]["max_connections"] == 0


def test_generic_requirement_boolean_is_downgraded_without_a_typed_field():
    draft = _adaptive_draft()
    question = {
        "criterion_key": "unknown_policy",
        "field": None,
        "question": "Do you require this merchant policy?",
        "why": "The policy changes which offers are acceptable.",
        "answer_kind": "boolean",
        "answer_semantics": "requirement_boolean",
        "options": ["Yes", "No"],
    }
    criterion = {
        "key": "unknown_policy",
        "field": None,
        "text": "merchant policy",
        "source_quote": "merchant policy",
        "kind": "requirement",
        "verification": "unsupported",
        "status": "needs_clarification",
    }
    result = apply_adaptive_plan(
        draft,
        _adaptive_extraction(question=question, criteria=[criterion], draft=draft),
    )
    shown = result["questions"][0]
    assert shown["field"] is None
    assert shown["answer_semantics"] is None
    assert shown["answer_kind"] == "single"


def test_same_source_generic_question_is_not_repeated_after_clear_answer():
    draft = _adaptive_draft()
    first_question = {
        "criterion_key": "merchant_policy",
        "field": None,
        "question": "What should happen with this merchant policy?",
        "why": "The policy changes which offers are acceptable.",
        "answer_kind": "text",
        "answer_semantics": None,
        "options": [],
    }
    first_criterion = {
        "key": "merchant_policy",
        "field": None,
        "text": "merchant policy",
        "source_quote": "merchant policy",
        "kind": "requirement",
        "verification": "unsupported",
        "status": "needs_clarification",
    }
    first = apply_adaptive_plan(
        draft,
        _adaptive_extraction(
            question=first_question,
            criteria=[first_criterion],
            draft=draft,
        ),
    )
    answered = deepcopy(first)
    answered["messages"].append({
        "role": "user",
        "content": "No, leave that policy alone.",
        "reply_to": first["questions"][0],
    })
    second_question = {
        "criterion_key": "merchant_policy_followup",
        "field": None,
        "question": "Should this merchant policy apply?",
        "why": "The policy changes which offers are acceptable.",
        "answer_kind": "text",
        "answer_semantics": None,
        "options": [],
    }
    second_criterion = {
        **first_criterion,
        "key": "merchant_policy_followup",
    }
    result = apply_adaptive_plan(
        answered,
        _adaptive_extraction(
            question=second_question,
            criteria=[second_criterion],
            draft=answered,
        ),
    )
    assert result["questions"] == []


def test_broad_source_overlap_does_not_hide_a_different_generic_condition():
    draft = _adaptive_draft(
        fields={
            **_adaptive_draft()["fields"],
            "max_connections": 0,
        },
        sources={
            **_adaptive_draft()["sources"],
            "max_connections": "no layovers and after 9am",
        },
    )
    question = {
        "criterion_key": "departure_window",
        "field": None,
        "question": "What departure time should apply?",
        "why": "The time changes which offers are acceptable.",
        "answer_kind": "text",
        "answer_semantics": None,
        "options": [],
    }
    criterion = {
        "key": "departure_window",
        "field": None,
        "text": "after 9am",
        "source_quote": "no layovers and after 9am",
        "kind": "requirement",
        "verification": "unsupported",
        "status": "needs_clarification",
    }
    result = apply_adaptive_plan(
        draft,
        _adaptive_extraction(question=question, criteria=[criterion], draft=draft),
    )
    assert len(result["questions"]) == 1
    assert result["questions"][0]["criterion_key"] == "departure_window"


def test_broad_source_overlap_does_not_hide_when_typed_record_copies_whole_turn():
    draft = _adaptive_draft(
        fields={
            **_adaptive_draft()["fields"],
            "max_connections": 0,
        },
        sources={
            **_adaptive_draft()["sources"],
            "max_connections": "no layovers and after 9am",
        },
        generic_criteria=[{
            "key": "max_connections",
            "field": "max_connections",
            "text": "no layovers and after 9am",
            "source_quote": "no layovers and after 9am",
            "kind": "requirement",
            "verification": "supported",
            "status": "captured",
        }],
    )
    question = {
        "criterion_key": "departure_window",
        "field": None,
        "question": "What departure time should apply?",
        "why": "The time changes which offers are acceptable.",
        "answer_kind": "text",
        "answer_semantics": None,
        "options": [],
    }
    criterion = {
        "key": "departure_window",
        "field": None,
        "text": "after 9am",
        "source_quote": "no layovers and after 9am",
        "kind": "requirement",
        "verification": "unsupported",
        "status": "needs_clarification",
    }
    result = apply_adaptive_plan(
        draft,
        _adaptive_extraction(
            question=question,
            criteria=[criterion],
            draft=draft,
        ),
    )
    assert len(result["questions"]) == 1
    assert result["questions"][0]["criterion_key"] == "departure_window"


def test_fresh_correction_reopens_same_source_generic_question():
    draft = _adaptive_draft()
    question = {
        "criterion_key": "route_policy",
        "field": None,
        "question": "How should I treat the route policy?",
        "why": "The policy changes which offers are acceptable.",
        "answer_kind": "text",
        "answer_semantics": None,
        "options": [],
    }
    criterion = {
        "key": "route_policy",
        "field": None,
        "text": "no layovers",
        "source_quote": "no layovers",
        "kind": "requirement",
        "verification": "unsupported",
        "status": "needs_clarification",
    }
    first = apply_adaptive_plan(
        draft,
        _adaptive_extraction(question=question, criteria=[criterion], draft=draft),
    )
    corrected = deepcopy(first)
    corrected["messages"].append({
        "role": "user",
        "content": "Actually, I changed my mind about no layovers.",
    })
    followup = {
        **question,
        "criterion_key": "route_policy_followup",
    }
    followup_criterion = {**criterion, "key": "route_policy_followup"}
    result = apply_adaptive_plan(
        corrected,
        _adaptive_extraction(
            question=followup,
            criteria=[followup_criterion],
            draft=corrected,
        ),
    )
    assert len(result["questions"]) == 1


def test_static_questions_do_not_reask_nonstop_for_zero_connections():
    fields = {
        "origin_airports": ["YYZ"],
        "destination_airports": ["LHR"],
        "departure_date": "2026-11-12",
        "max_total_cents": 79999,
        "max_connections": 0,
    }
    assert questions(
        "flight",
        fields,
        clarifications=[{
            "field": "nonstop",
            "source_quote": "no layovers",
            "reason": "ambiguous",
        }],
        messages=[],
    ) == []


def test_later_unrelated_turn_preserves_canonical_hotel_fields():
    current = {
        "fields": {
            "city": "Boston",
            "checkin_date": "2026-11-12",
            "checkout_date": "2026-11-14",
            "max_total_cents": 21999,
        },
        "sources": {
            "city": "Boston",
            "checkin_date": "Nov 12, 2026",
            "checkout_date": "Nov 14, 2026",
            "max_total_cents": "under $220",
        },
        "clarifications": [],
    }
    proposed = {
        "fields": {"max_total_cents": 21999},
        "sources": {"max_total_cents": "under $220"},
        "clarifications": [],
    }
    result = merge_revision_state(
        "hotel",
        current,
        proposed,
        "Actually, breakfast is optional.",
        [{"role": "user", "content": "Actually, breakfast is optional."}],
    )
    assert result["fields"] == current["fields"]
    assert result["sources"] == current["sources"]
