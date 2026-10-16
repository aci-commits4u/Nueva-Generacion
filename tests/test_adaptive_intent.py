"""Provider-free tests for the model-directed adaptive contract."""

from copy import deepcopy

import pytest


def envelope(*, fields=None, sources=None, unsupported=None, explanation="Review the request."):
    return {
        "fields": fields or {},
        "sources": sources or {},
        "unsupported": unsupported or [],
        "clarifications": [],
        "explanation": explanation,
    }


def plan(*, action="ask_user", question=None, criteria=None, **draft):
    return {
        "action": action,
        "assistant_message": "I need one useful detail before continuing.",
        "question": question,
        "criteria": criteria or [],
        "offer_observations": [],
        **envelope(**draft),
    }


def test_generic_criteria_can_drive_a_generated_question_without_profile_field():
    from app.adaptive_intent import normalize_plan

    raw = plan(
        criteria=[{
            "key": "quiet_cabin",
            "field": None,
            "text": "a quiet cabin",
            "source_quote": "a quiet cabin",
            "kind": "requirement",
            "verification": "unsupported",
        }],
        unsupported=["a quiet cabin"],
        question={
            "criterion_key": "quiet_cabin",
            "field": None,
            "text": "When you say quiet, should I treat that as a strict requirement?",
            "why": "The available offer facts do not define quietness, so I need your boundary before review.",
            "answer_kind": "boolean",
            "answer_semantics": "requirement_boolean",
            "options": ["Yes, strict", "No, preference"],
        },
    )
    result = normalize_plan(raw, domain="general", source_text="Find a quiet cabin")
    assert result["action"] == "ask_user"
    assert result["question"]["field"] is None
    assert result["question"]["answer_kind"] == "boolean"
    assert result["question"]["answer_semantics"] == "requirement_boolean"
    assert result["criteria"][0]["verification"] == "unsupported"


def _date_question_case(domain, quote, *, field="departure_date", source_messages=None):
    raw = plan(
        criteria=[{
            "key": field,
            "field": field,
            "text": quote,
            "source_quote": quote,
            "kind": "ambiguity",
            "status": "needs_clarification",
        }],
        question={
            "criterion_key": field,
            "field": field,
            "text": "What date should I use?",
            "why": "I need the date before I can search.",
            "answer_kind": "date_choice",
            "answer_semantics": None,
            "options": [],
        },
    )
    from app.adaptive_intent import normalize_plan
    normalized = normalize_plan(
        raw,
        domain=domain,
        source_text=quote,
        source_messages=source_messages,
    )
    return raw, normalized


def test_resolvable_question_feedback_flags_exact_explicit_date_without_mutating_draft():
    from app.adaptive_intent import resolvable_question_feedback

    quote = "Depart from YYZ or YHM, arrive at LHR or LGW, on November 12, 2026."
    raw, normalized = _date_question_case("flight", quote)
    feedback = resolvable_question_feedback(raw, normalized, "flight", quote, [])
    assert feedback == {
        "codes": ["question_answer_already_resolvable"],
        "field": "departure_date",
        "source_quote": quote,
        "value": "2026-11-12",
    }
    assert "departure_date" not in raw["fields"]
    assert "departure_date" not in normalized["draft"]["fields"]


@pytest.mark.parametrize("quote", [
    "I can travel November 12 or November 14, 2026.",
    "Preferably November 12, 2026.",
    "Not November 12, 2026.",
    "November 12",
])
def test_resolvable_question_feedback_stays_silent_for_ambiguous_or_unsafe_dates(quote):
    from app.adaptive_intent import resolvable_question_feedback

    raw, normalized = _date_question_case("flight", quote)
    assert resolvable_question_feedback(raw, normalized, "flight", quote, []) is None


def test_resolvable_question_feedback_rejects_past_booking_date_with_trusted_reference():
    from app.adaptive_intent import resolvable_question_feedback

    quote = "Book the flight for November 12, 2025."
    messages = [{
        "role": "user",
        "content": quote,
        "timestamp": "2026-10-16T16:15:42Z",
        "reference_date": "2026-10-16",
    }]
    raw, normalized = _date_question_case("flight", quote, source_messages=messages)
    assert resolvable_question_feedback(
        raw, normalized, "flight", quote, messages,
    ) is None


def test_resolvable_question_feedback_does_not_assign_hotel_role_to_date_range():
    from app.adaptive_intent import resolvable_question_feedback

    quote = "Stay from November 12 through November 14, 2026."
    raw, normalized = _date_question_case(
        "hotel", quote, field="checkin_date",
    )
    assert resolvable_question_feedback(raw, normalized, "hotel", quote, []) is None


def test_generic_criterion_status_is_preserved_as_descriptive_metadata():
    from app.adaptive_intent import normalize_plan

    raw = plan(
        criteria=[{
            "key": "arrival_deadline",
            "field": None,
            "text": "arrive before my work trip",
            "source_quote": "arrive before my work trip",
            "kind": "ambiguity",
            "status": "needs_clarification",
            "verification": "supported",
        }],
        question={
            "criterion_key": "arrival_deadline",
            "field": None,
            "text": "What date and time does the trip begin?",
            "why": "The deadline changes which offers can satisfy the request.",
            "answer_kind": "date_choice",
        },
    )
    result = normalize_plan(raw, domain="general", source_text="arrive before my work trip")
    assert result["criteria"][0]["status"] == "needs_clarification"
    assert result["criteria"][0]["verification"] == "unsupported"


def test_declined_criterion_cannot_reopen_as_a_question():
    from app.adaptive_intent import normalize_plan

    raw = plan(
        criteria=[{
            "key": "refundable",
            "field": None,
            "text": "refundable",
            "source_quote": "refundable",
            "kind": "preference",
            "status": "declined",
        }],
        question={
            "criterion_key": "refundable",
            "field": None,
            "text": "Do you require refundable?",
            "why": "This changes the offer set.",
            "answer_kind": "boolean",
            "answer_semantics": "requirement_boolean",
        },
    )
    result = normalize_plan(raw, domain="general", source_text="I don't care about refundable")
    assert result["action"] == "review_required"
    assert result["question"] is None


def test_known_profile_ambiguity_stays_supported_while_unresolved():
    from app.adaptive_intent import normalize_plan

    raw = plan(
        criteria=[{
            "key": "departure_date",
            "field": "departure_date",
            "text": "sometime next week",
            "source_quote": "sometime next week",
            "kind": "ambiguity",
            "status": "needs_clarification",
            "verification": "unsupported",
        }],
        question={
            "criterion_key": "departure_date",
            "field": "departure_date",
            "text": "What exact date should I use?",
            "why": "The search needs a concrete departure date.",
            "answer_kind": "date_choice",
        },
    )
    result = normalize_plan(raw, domain="flight", source_text="sometime next week")
    assert result["criteria"][0]["verification"] == "supported"
    assert result["criteria"][0]["status"] == "needs_clarification"


def test_adaptive_compiler_replays_generic_clarification_and_preserves_other_facts(monkeypatch):
    from app.ai_pipeline import run_pipeline

    source = (
        "Find a quiet, sustainably made lamp that can arrive before my work trip under $120"
    )
    criterion = {
        "key": "arrival_deadline",
        "field": None,
        "text": "arrive before my work trip",
        "source_quote": "arrive before my work trip",
        "kind": "ambiguity",
        "status": "needs_clarification",
    }
    question = {
        "criterion_key": "arrival_deadline",
        "field": None,
        # Deliberately repeats the source criterion; assistant_message carries
        # the actual model-generated customer-facing question.
        "text": "arrive before my work trip",
        "why": "The deadline changes which offers can satisfy the request.",
        "answer_kind": "date_choice",
    }
    first = plan(
        action="ask_user",
        criteria=[criterion],
        question=question,
        fields={"max_total_cents": 12000},
        sources={"max_total_cents": "under $120"},
        unsupported=["quiet", "sustainably made"],
    )
    first["assistant_message"] = "Could you tell me the date of your work trip?"
    first["clarifications"] = [{
        "field": None,
        "source_quote": "arrive before my work trip",
        "reason": "ambiguity",
    }]
    second = deepcopy(first)

    monkeypatch.setenv("MOCK_LLM", "0")
    monkeypatch.setattr("app.ai_pipeline.reserve_ai_calls", lambda *args, **kwargs: 2)
    monkeypatch.setattr("app.ai_pipeline.call_json", lambda stage, *args, **kwargs: (
        deepcopy(first if stage == "adaptive_plan" else second),
        {"stage": stage, "tokens": {}},
    ))
    result = run_pipeline("general", source, "session", variant="adaptive")
    assert result["fields"]["max_total_cents"] == 11999
    assert "arrive before my work trip" in result["unsupported"]
    assert result["adaptive_plan"]["question"]["text"] == (
        "Could you tell me the date of your work trip?"
    )


def test_merchant_text_cannot_become_customer_criterion_or_question_target():
    from app.adaptive_intent import normalize_plan

    raw = plan(
        criteria=[{
            "key": "free_breakfast",
            "field": "breakfast",
            "text": "free breakfast",
            "source_quote": "free breakfast from the merchant",
            "kind": "requirement",
            "verification": "supported",
        }],
        question={
            "criterion_key": "free_breakfast",
            "field": "breakfast",
            "text": "Do you require breakfast?",
            "why": "A merchant offer mentions it.",
            "answer_kind": "boolean",
        },
    )
    result = normalize_plan(raw, domain="hotel", source_text="Book a room in Orlando")
    assert result["criteria"] == []
    assert result["action"] == "review_required"
    assert result["question"] is None


def test_inspect_offers_requires_grounded_search_facts_and_runs_only_read_only_tool():
    from app.adaptive_intent import execute_tool

    seen = []

    def fake(domain, fields):
        seen.append((domain, deepcopy(fields)))
        return {"tool": "inspect_offers", "status": "ok", "read_only": True, "offers": []}

    blocked = execute_tool(
        "inspect_offers", domain="flight", fields={"max_total_cents": 29999},
        tool_overrides={"inspect_offers": fake},
    )
    assert blocked["status"] == "blocked_missing_search_facts"
    assert seen == []

    result = execute_tool(
        "inspect_offers", domain="flight",
        fields={
            "origin_airports": ["EWR"],
            "destination_airports": ["MCO", "MIA"],
            "departure_date": "2026-11-12",
        },
        tool_overrides={"inspect_offers": fake},
    )
    assert result["read_only"] is True
    assert seen == [("flight", {
        "origin_airports": ["EWR"],
        "destination_airports": ["MCO", "MIA"],
        "departure_date": "2026-11-12",
    })]


def test_missing_or_malformed_question_fails_closed_without_fixed_fallback():
    from app.adaptive_intent import normalize_plan

    raw = plan(
        criteria=[{
            "key": "destination",
            "field": None,
            "text": "Florida",
            "source_quote": "Florida",
            "kind": "ambiguity",
            "verification": "unsupported",
        }],
        question={"criterion_key": "not-in-criteria", "text": "Choose", "why": "Why", "answer_kind": "text"},
    )
    result = normalize_plan(raw, domain="flight", source_text="Find a flight to Florida")
    assert result["action"] == "review_required"
    assert result["question"] is None
    assert "fixed" not in result["assistant_message"].lower()


def test_unknown_action_cannot_keep_a_ready_message():
    from app.adaptive_intent import normalize_plan

    raw = plan(action="approve_purchase")
    result = normalize_plan(raw, domain="general", source_text="Find something under $100")
    assert result["action"] == "review_required"
    assert "could not safely determine" in result["assistant_message"]


def test_required_profile_gap_can_be_asked_without_fabricated_customer_quote():
    from app.adaptive_intent import normalize_plan

    raw = plan(
        criteria=[],
        question={
            "criterion_key": "origin_airports",
            "field": "origin_airports",
            "text": "Which departure airport should I search from?",
            "why": "The route cannot be searched until I know the departure airport.",
            "answer_kind": "multi",
            "options": [{"label": "Newark (EWR)", "value": "EWR"}],
        },
    )
    result = normalize_plan(raw, domain="flight", source_text="Find me a flight under $300")
    assert result["action"] == "ask_user"
    assert result["question"]["field"] == "origin_airports"
    assert result["criteria"][0]["source_quote"] is None
    assert result["criteria"][0]["status"] == "needs_clarification"


def test_policy_tool_is_allowlisted_and_does_not_run_for_ready_action():
    from app.adaptive_intent import execute_tool

    assert execute_tool("ready_for_review", domain="flight", fields={}) is None
    result = execute_tool("retrieve_policy", domain="flight", fields={})
    assert result["tool"] == "retrieve_policy"
    assert result["status"] == "ok"
    assert result["read_only"] is True
    assert result["provenance"] == "synthetic merchant context; informational only"


def test_malformed_offer_tool_payload_cannot_become_observations():
    from app.adaptive_intent import normalize_plan

    raw = plan(
        action="inspect_offers",
        fields={"max_total_cents": 9999},
        sources={"max_total_cents": "under $100"},
    )
    malformed = {
        "tool": "inspect_offers",
        "status": "ok",
        "read_only": True,
        "offers": [{
            "id": "offer-1",
            "offer_hash": "",
            "facts": {"total_cents": 9000},
            "signed": True,
            # Missing the required merchant checkout provenance.
        }],
    }
    result = normalize_plan(
        raw, domain="general", source_text="under $100", tool_result=malformed
    )
    assert result["offer_observations"] == []


def test_general_domain_cannot_inspect_without_a_search_adapter():
    from app.adaptive_intent import execute_tool

    result = execute_tool("inspect_offers", domain="general", fields={})
    assert result["status"] == "blocked_missing_search_facts"
    assert result["read_only"] is True


def test_adaptive_pipeline_executes_one_model_selected_tool_and_returns_plan(monkeypatch):
    from app.ai_pipeline import run_pipeline

    calls = []
    tools = []
    candidate = plan(
        action="retrieve_policy",
        fields={"nonstop": True, "max_total_cents": 29999},
        sources={"nonstop": "nonstop", "max_total_cents": "under $300"},
    )

    def fake_call(stage, *args, **kwargs):
        calls.append((stage, kwargs.get("tool_result")))
        return deepcopy(candidate), {"stage": stage, "model": "test", "tokens": {}}

    def fake_tool(action, *, domain, fields):
        tools.append((action, domain, fields))
        return {"tool": action, "status": "ok", "read_only": True, "offers": []}

    monkeypatch.setenv("MOCK_LLM", "0")
    monkeypatch.setattr("app.ai_pipeline.reserve_ai_calls", lambda *args, **kwargs: 2)
    monkeypatch.setattr("app.ai_pipeline.call_json", fake_call)
    monkeypatch.setattr("app.ai_pipeline.execute_tool", fake_tool)

    result = run_pipeline("flight", "nonstop under $300", "session", variant="adaptive")
    assert [stage for stage, _ in calls] == ["adaptive_plan", "adaptive_review"]
    assert calls[0][1] is None
    assert calls[1][1]["tool"] == "retrieve_policy"
    assert tools == [("retrieve_policy", "flight", {"nonstop": True, "max_total_cents": 29999})]
    assert result["pipeline"] == "adaptive"
    assert result["next_step"] == "retrieve_policy"
    assert result["merchant_context_used"] is True
    assert result["fields"]["nonstop"] is True


def test_ready_grounded_search_gets_harness_offer_lookup_before_review(monkeypatch):
    from app.ai_pipeline import run_pipeline

    candidate = plan(
        action="ready_for_review",
        fields={
            "origin_airports": ["EWR"],
            "destination_airports": ["MCO"],
            "departure_date": "2026-11-12",
            "max_total_cents": 29999,
        },
        sources={
            "origin_airports": "EWR",
            "destination_airports": "MCO",
            "departure_date": "2026-11-12",
            "max_total_cents": "under $300",
        },
    )
    calls = []

    def fake_call(stage, *args, **kwargs):
        return deepcopy(candidate), {"stage": stage, "tokens": {}}

    def fake_tool(action, *, domain, fields):
        calls.append((action, domain, deepcopy(fields)))
        return {
            "tool": "inspect_offers",
            "status": "ok",
            "read_only": True,
            "offers": [],
            "count": 0,
        }

    monkeypatch.setenv("MOCK_LLM", "0")
    monkeypatch.setattr("app.ai_pipeline.reserve_ai_calls", lambda *args, **kwargs: 2)
    monkeypatch.setattr("app.ai_pipeline.call_json", fake_call)
    monkeypatch.setattr("app.ai_pipeline.execute_tool", fake_tool)
    result = run_pipeline("flight", "EWR to MCO on 2026-11-12 under $300", "session", variant="adaptive")
    assert calls and calls[0][0] == "inspect_offers"
    assert result["model_action"] == "ready_for_review"
    assert result["tool_selection_origin"] == "pre_review_requirement"
    assert result["read_only_tool_log"]["tool"] == "inspect_offers"


def test_adaptive_recovers_route_and_compiled_date_before_tool_selection(monkeypatch):
    from app.ai_pipeline import run_pipeline

    source = "Fly from Newark to Orlando on Nov 12, 2026 under $300"
    candidate = plan(
        action="inspect_offers",
        fields={
            "max_total_cents": 29999,
            "origin_airports": ["EWR"],
            "destination_airports": ["MCO"],
            # Deliberately wrong typed date; the quote is authoritative.
            "departure_date": "2026-11-13",
        },
        sources={
            "max_total_cents": "under $300",
            "origin_airports": "Newark",
            "destination_airports": "Orlando",
            "departure_date": "Nov 12, 2026",
        },
    )
    final = deepcopy(candidate)
    final["action"] = "ready_for_review"
    final["fields"]["departure_date"] = "2026-11-12"
    calls = []
    tool_calls = []

    def fake_call(stage, *args, **kwargs):
        calls.append(stage)
        return deepcopy(candidate if stage == "adaptive_plan" else final), {"stage": stage, "tokens": {}}

    def fake_tool(action, *, domain, fields):
        tool_calls.append((action, deepcopy(fields)))
        return {"tool": action, "status": "ok", "read_only": True, "offers": []}

    monkeypatch.setenv("MOCK_LLM", "0")
    monkeypatch.setattr("app.ai_pipeline.reserve_ai_calls", lambda *args, **kwargs: 2)
    monkeypatch.setattr("app.ai_pipeline.call_json", fake_call)
    monkeypatch.setattr("app.ai_pipeline.execute_tool", fake_tool)

    result = run_pipeline("flight", source, "session", variant="adaptive")
    assert calls == ["adaptive_plan", "adaptive_review"]
    assert tool_calls == [("inspect_offers", {
        "max_total_cents": 29999,
        "origin_airports": ["EWR"],
        "destination_airports": ["MCO"],
        "departure_date": "2026-11-12",
    })]
    assert result["fields"]["departure_date"] == "2026-11-12"
    assert result["read_only_tool_log"]["status"] == "ok"


def test_source_backed_generic_criterion_becomes_an_unsupported_review_flag(monkeypatch):
    from app.ai_pipeline import run_pipeline

    source = "Find a product under $100 and arrive before work trip"
    generic = [{
        "key": "work_timing",
        "field": None,
        "text": "arrive before work trip",
        "source_quote": "arrive before work trip",
        "kind": "requirement",
        "verification": "unsupported",
    }]
    raw = plan(
        action="ready_for_review",
        criteria=generic,
        fields={"max_total_cents": 9999},
        sources={"max_total_cents": "under $100"},
    )
    monkeypatch.setenv("MOCK_LLM", "0")
    monkeypatch.setattr("app.ai_pipeline.reserve_ai_calls", lambda *args, **kwargs: 2)
    monkeypatch.setattr("app.ai_pipeline.call_json", lambda stage, *args, **kwargs: (
        deepcopy(raw), {"stage": stage, "tokens": {}}
    ))
    result = run_pipeline("general", source, "session", variant="adaptive")
    assert "arrive before work trip" in result["unsupported"]
    assert any(item.get("source_quote") == "arrive before work trip"
               for item in result["criteria"])


def test_final_planner_criteria_uses_compiled_price_not_raw_model_value(monkeypatch):
    from app.ai_pipeline import run_pipeline

    source = "under $120"
    raw = plan(
        action="ready_for_review",
        fields={"max_total_cents": 12000},
        sources={"max_total_cents": "under $120"},
    )
    monkeypatch.setenv("MOCK_LLM", "0")
    monkeypatch.setattr("app.ai_pipeline.reserve_ai_calls", lambda *args, **kwargs: 2)
    monkeypatch.setattr("app.ai_pipeline.call_json", lambda stage, *args, **kwargs: (
        deepcopy(raw), {"stage": stage, "tokens": {}}
    ))
    result = run_pipeline("general", source, "session", variant="adaptive")
    assert result["fields"]["max_total_cents"] == 11999
    assert any(item["field"] == "max_total_cents" and "11999" in item["text"]
               for item in result["criteria"])


def test_reviewer_cannot_claim_an_unexecuted_tool_action(monkeypatch):
    from app.ai_pipeline import run_pipeline

    source = "under $100"
    stage1 = plan(action="ready_for_review", fields={"max_total_cents": 9999}, sources={"max_total_cents": "under $100"})
    stage2 = deepcopy(stage1)
    stage2["action"] = "inspect_offers"
    monkeypatch.setenv("MOCK_LLM", "0")
    monkeypatch.setattr("app.ai_pipeline.reserve_ai_calls", lambda *args, **kwargs: 2)
    monkeypatch.setattr("app.ai_pipeline.call_json", lambda stage, *args, **kwargs: (
        deepcopy(stage1 if stage == "adaptive_plan" else stage2), {"stage": stage, "tokens": {}}
    ))
    result = run_pipeline("general", source, "session", variant="adaptive")
    assert result["next_step"] == "review_required"
    assert "not claim" in result["adaptive_plan"]["assistant_message"]


def test_independent_review_preserves_pending_model_question_without_new_answer(monkeypatch):
    from app.ai_pipeline import run_pipeline

    source = "Find a quiet, sustainably made lamp that can arrive before my work trip under $120"
    pending = plan(
        action="ask_user",
        criteria=[{
            "key": "arrival_deadline",
            "field": None,
            "text": "arrive before my work trip",
            "source_quote": "arrive before my work trip",
            "kind": "ambiguity",
            "status": "needs_clarification",
        }],
        question={
            "criterion_key": "arrival_deadline",
            "field": None,
            "text": "What date and time does the work trip begin?",
            "why": "The deadline changes which offers can satisfy the request.",
            "answer_kind": "date_choice",
        },
        unsupported=["quiet", "sustainably made", "arrive before my work trip"],
        fields={"max_total_cents": 11999},
        sources={"max_total_cents": "under $120"},
    )
    reviewed = plan(
        action="ready_for_review",
        fields={"max_total_cents": 11999},
        sources={"max_total_cents": "under $120"},
        unsupported=["quiet", "sustainably made", "arrive before my work trip"],
    )
    monkeypatch.setenv("MOCK_LLM", "0")
    monkeypatch.setattr("app.ai_pipeline.reserve_ai_calls", lambda *args, **kwargs: 2)
    monkeypatch.setattr("app.ai_pipeline.call_json", lambda stage, *args, **kwargs: (
        deepcopy(pending if stage == "adaptive_plan" else reviewed),
        {"stage": stage, "tokens": {}},
    ))
    result = run_pipeline("general", source, "session", variant="adaptive")
    assert result["adaptive_plan"]["action"] == "ask_user"
    assert result["adaptive_plan"]["question"]["criterion_key"] == "arrival_deadline"

