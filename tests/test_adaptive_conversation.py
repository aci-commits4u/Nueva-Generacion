"""State and consent boundaries for the model-directed conversation layer."""

from copy import deepcopy

from app.ai_grounding import validate_extraction
from app.ai_grounding import recover_grounded_parts
from app.conversation import (
    adaptive_question_id,
    apply_adaptive_plan,
    context,
    declined_preferences,
    is_trusted_adaptive_question,
    provenance,
)


def _draft(**overrides):
    value = {
        "domain": "flight",
        "mode": "live",
        "pipeline": "adaptive",
        "fields": {
            "max_total_cents": 29999,
            "origin_airports": ["EWR"],
            "destination_airports": ["MCO"],
            "departure_date": "2026-11-12",
        },
        "sources": {
            "max_total_cents": "under $300",
            "origin_airports": "Newark",
            "destination_airports": "Orlando",
            "departure_date": "Nov 12, 2026",
        },
        "clarifications": [],
        "unsupported": [],
        "messages": [{"role": "user", "content": "Fly from Newark to Orlando on Nov 12, 2026 under $300."}],
    }
    value.update(overrides)
    return value


def _extraction(*, question=None, action="ask_user", criteria=None, **overrides):
    result = {
        "mode": "live",
        "pipeline": "adaptive",
        "model": "test",
        "fields": deepcopy(_draft()["fields"]),
        "sources": deepcopy(_draft()["sources"]),
        "clarifications": [],
        "unsupported": [],
        "explanation": "Review the captured request.",
        "adaptive_plan": {
            "action": action,
            "assistant_message": "I need one decision before I review offers.",
            "question": question,
            "criteria": criteria or [],
            "offer_observations": [],
        },
        "agent_tools": [],
    }
    result.update(overrides)
    return result


def _criterion(key="nonstop", field="nonstop", *, status="needs_clarification", verification="supported"):
    return {
        "key": key,
        "field": field,
        "text": "nonstop flight",
        "source_quote": "nonstop",
        "kind": "requirement",
        "verification": verification,
        "status": status,
    }


def _question(**overrides):
    result = {
        "criterion_key": "nonstop",
        "field": "nonstop",
        "text": "Do you require a nonstop flight?",
        "why": "This changes which offers are acceptable.",
        "answer_kind": "boolean",
        "answer_semantics": "requirement_boolean",
        "options": [{"label": "Yes", "value": "yes"}, {"label": "No", "value": "no"}],
    }
    result.update(overrides)
    return result


def _hotel_draft(**overrides):
    value = {
        "domain": "hotel",
        "mode": "live",
        "pipeline": "adaptive",
        "fields": {
            "max_total_cents": 29999,
            "city": "Orlando",
            "checkin_date": "2026-11-12",
            "checkout_date": "2026-11-14",
        },
        "sources": {
            "max_total_cents": "under $300",
            "city": "Orlando",
            "checkin_date": "Nov 12, 2026",
            "checkout_date": "Nov 14, 2026",
        },
        "clarifications": [],
        "unsupported": [],
        "messages": [{
            "role": "user",
            "content": "Find a hotel in Orlando from Nov 12 through Nov 14 under $300.",
        }],
    }
    value.update(overrides)
    return value


def test_adaptive_question_gets_stable_server_binding_and_context_metadata():
    extraction = _extraction(question=_question(), criteria=[_criterion()])
    first = apply_adaptive_plan(_draft(), extraction)
    second = apply_adaptive_plan(_draft(), extraction)
    question = first["questions"][0]

    assert question == second["questions"][0]
    assert question["origin"] == "ai"
    assert question["server_generated"] is True
    assert question["binding"] == "intent-judge-ai-question-v1"
    assert question["id"] == question["question_id"] == adaptive_question_id("flight", question)
    assert is_trusted_adaptive_question(question, "flight")
    encoded = context([{"role": "user", "content": "Yes", "reply_to": question}])
    assert "contract_digest" in encoded and "options" in encoded


def test_ambiguous_boolean_question_is_rejected_and_cannot_bind_yes():
    extraction = _extraction(
        question=_question(
            text="Is nonstop essential or merely preferred?",
            answer_semantics=None,
        ),
        criteria=[_criterion()],
    )
    draft = apply_adaptive_plan(_draft(), extraction)
    assert len(draft["questions"]) == 1
    assert draft["questions"][0]["response_type"] in {"single", "text"}
    assert draft["questions"][0]["answer_semantics"] is None

    arbitrary = deepcopy(_question())
    arbitrary["id"] = "q_attacker"
    arbitrary["question_id"] = "q_attacker"
    arbitrary["origin"] = "ai"
    message = [{"role": "user", "content": "Yes", "reply_to": arbitrary}]
    envelope = {
        "fields": {"nonstop": True},
        "sources": {"nonstop": "Yes"},
        "unsupported": [],
        "clarifications": [],
        "explanation": "Review.",
    }
    # The arbitrary reply object is not a trusted source binding.  It cannot
    # make a short Yes prove a boolean requirement.
    try:
        validate_extraction("flight", "Yes", envelope, source_messages=message)
    except Exception:
        pass
    else:
        raise AssertionError("arbitrary AI-looking reply_to must not bind Yes")


def test_answered_question_is_suppressed_without_erasing_flags_or_corrections():
    question = _question()
    first = apply_adaptive_plan(
        _draft(unsupported=["round trip"]),
        _extraction(question=question, criteria=[_criterion()]),
    )
    answered = deepcopy(first)
    answered["messages"].append({"role": "user", "content": "Yes", "reply_to": first["questions"][0]})
    answered["fields"]["max_total_cents"] = 35000
    answered["sources"]["max_total_cents"] = "up to $350"
    second = apply_adaptive_plan(
        answered,
        _extraction(
            question=question,
            criteria=[_criterion(key="nonstop", status="captured")],
            fields=deepcopy(answered["fields"]),
            sources=deepcopy(answered["sources"]),
            unsupported=["round trip"],
        ),
    )
    assert second["questions"] == []
    assert second["unsupported"] == ["round trip"]
    assert second["fields"]["max_total_cents"] == 35000


def test_trusted_ai_no_preference_is_recorded_only_for_optional_field():
    question = _question(
        field="refundable",
        criterion_key="refundable",
        text="Do you require a refundable fare?",
    )
    extraction = _extraction(question=question, criteria=[_criterion("refundable", "refundable")])
    draft = apply_adaptive_plan(_draft(), extraction)
    trusted = draft["questions"][0]
    messages = [{"role": "user", "content": "No preference", "reply_to": trusted}]
    assert declined_preferences("flight", messages) == {"refundable": "No preference"}

    forged = deepcopy(trusted)
    forged["question"] = "Do you require a nonstop flight?"
    forged["question_id"] = forged["id"]
    assert declined_preferences("flight", [{"role": "user", "content": "No preference", "reply_to": forged}]) == {}


def test_original_no_preference_clauses_fill_typed_none_and_skip_questions():
    draft = _hotel_draft(
        messages=[{
            "role": "user",
            "content": "Find a hotel in Orlando. I do not care about breakfast or cancellation.",
        }],
        clarifications=[
            {"field": "breakfast", "source_quote": "breakfast is unclear"},
            {"field": "city", "source_quote": "Orlando"},
        ],
        unsupported=["pets allowed"],
    )
    extraction = _extraction(
        question=_question(field="breakfast", criterion_key="breakfast",
                           text="Must breakfast be included?"),
        criteria=[
            _criterion("breakfast", "breakfast"),
            _criterion("refundable", "refundable"),
        ],
        fields=deepcopy(draft["fields"]), sources=deepcopy(draft["sources"]),
        unsupported=["pets allowed"],
    )
    result = apply_adaptive_plan(draft, extraction)

    assert result["fields"]["breakfast"] is None
    assert result["fields"]["refundable"] is None
    assert result["sources"]["breakfast"] == "I do not care about breakfast or cancellation"
    assert result["sources"]["refundable"] == "I do not care about breakfast or cancellation"
    assert {item["key"] for item in result["generic_criteria"] if item["status"] == "declined"} >= {
        "breakfast", "refundable",
    }
    assert result["questions"] == []
    assert result["unsupported"] == ["pets allowed"]
    assert all(item.get("field") != "breakfast" for item in result["clarifications"])
    assert any(item.get("field") == "city" for item in result["clarifications"])


def test_silence_does_not_compile_optional_none():
    draft = _hotel_draft()
    result = apply_adaptive_plan(
        draft,
        _extraction(
            question=None,
            criteria=[],
            action="review_required",
            domain="hotel",
            fields=deepcopy(draft["fields"]),
            sources=deepcopy(draft["sources"]),
        ),
    )
    assert "breakfast" not in result["fields"]
    assert "refundable" not in result["fields"]
    assert "breakfast" not in result["sources"]
    assert "refundable" not in result["sources"]


def test_later_positive_requirement_wins_over_historical_decline():
    draft = _hotel_draft(
        fields={**_hotel_draft()["fields"], "breakfast": True},
        sources={**_hotel_draft()["sources"], "breakfast": "Actually, I require breakfast."},
        messages=[
            {"role": "user", "content": "I do not care about breakfast or cancellation."},
            {"role": "user", "content": "Actually, I require breakfast."},
        ],
    )
    result = apply_adaptive_plan(
        draft,
        _extraction(
            question=None,
            criteria=[],
            action="review_required",
            domain="hotel",
            fields=deepcopy(draft["fields"]),
            sources=deepcopy(draft["sources"]),
        ),
    )
    assert result["fields"]["breakfast"] is True
    assert result["sources"]["breakfast"] == "Actually, I require breakfast."


def test_declined_optional_question_stays_suppressed_until_customer_reopens_it():
    question = _question(field="refundable", criterion_key="refundable",
                         text="Do you require a refundable fare?")
    extraction = _extraction(question=question,
                             criteria=[_criterion("refundable", "refundable")])
    first = apply_adaptive_plan(_draft(), extraction)
    declined = deepcopy(first)
    declined["messages"].append({
        "role": "user", "content": "No preference",
        "reply_to": first["questions"][0],
    })
    assert apply_adaptive_plan(declined, extraction)["questions"] == []

    reopened = deepcopy(declined)
    reopened["messages"].append({
        "role": "user", "content": "Actually, I require a refundable fare.",
    })
    reopened_result = apply_adaptive_plan(reopened, extraction)
    assert len(reopened_result["questions"]) == 1


def test_provenance_snapshots_adaptive_metadata_without_authorizing_it():
    extraction = _extraction(question=_question(), criteria=[_criterion()])
    record = provenance(extraction, 2, _draft()["messages"])
    assert record["adaptive_plan"]["action"] == "ask_user"
    assert record["generic_criteria"][0]["key"] == "nonstop"
    assert record["agent_tools"] == []
    assert "approved" not in record["adaptive_plan"]


def test_missing_required_field_can_get_ai_question_without_fabricated_source():
    draft = _draft(fields={"max_total_cents": 29999}, sources={"max_total_cents": "under $300"})
    extraction = _extraction(
        question=_question(
            criterion_key="origin_airports",
            field="origin_airports",
            text="Which departure airports work for you?",
            answer_kind="multi",
            answer_semantics=None,
            options=[{"label": "Newark · EWR", "value": "EWR"}],
        ),
        criteria=[],
        fields=deepcopy(draft["fields"]),
        sources=deepcopy(draft["sources"]),
    )
    result = apply_adaptive_plan(draft, extraction)
    assert result["questions"][0]["field"] == "origin_airports"
    assert any(item["key"] == "origin_airports" and item["source_quote"] is None
               for item in result["generic_criteria"])


def test_offline_draft_keeps_static_questions_and_no_adaptive_metadata():
    draft = _draft(
        mode="offline", pipeline="offline",
        fields={"max_total_cents": 29999},
        sources={"max_total_cents": "under $300"},
    )
    result = apply_adaptive_plan(
        draft,
        {
            "mode": "offline", "pipeline": "offline",
            "fields": deepcopy(draft["fields"]),
            "sources": deepcopy(draft["sources"]),
            "unsupported": [], "clarifications": [], "explanation": "Review.",
            "adaptive_plan": {"action": "review_required", "criteria": []},
        },
    )
    assert "adaptive_plan" not in result
    assert result["questions"]


def test_generic_boolean_question_stays_useful_but_yes_never_binds():
    extraction = _extraction(
        question=_question(
            criterion_key="comfort",
            field=None,
            text="Is comfort essential or merely preferred?",
            answer_semantics=None,
            options=[{"label": "I require it", "value": "required"},
                     {"label": "It is a preference", "value": "preferred"}],
        ),
        criteria=[_criterion("comfort", None, status="needs_clarification", verification="unsupported")],
    )
    result = apply_adaptive_plan(_draft(), extraction)
    assert len(result["questions"]) == 1
    assert result["questions"][0]["field"] is None
    assert result["questions"][0]["response_type"] == "single"
    assert result["questions"][0]["answer_semantics"] is None


def test_same_generic_criterion_different_wording_does_not_repeat_after_answer():
    q1 = _question(
        criterion_key="quiet", field=None,
        text="What does quiet mean for this room?",
        answer_kind="text", answer_semantics=None,
    )
    criteria = [{**_criterion("quiet", None, status="captured", verification="unsupported"),
                 "source_quote": "quiet", "text": "quiet room"}]
    first = apply_adaptive_plan(
        _draft(), _extraction(question=q1, criteria=criteria),
    )
    current = deepcopy(first)
    current["messages"].append({
        "role": "user", "content": "I need it quiet at night.",
        "timestamp": "2026-10-14T01:00:00+00:00",
        "reply_to": first["questions"][0],
    })
    q2 = _question(
        criterion_key="quiet", field=None,
        text="How important is a quiet room to you?",
        answer_kind="text", answer_semantics=None,
    )
    second = apply_adaptive_plan(
        current, _extraction(question=q2, criteria=criteria),
    )
    assert second["questions"] == []
    assert "quiet" in second["unsupported"]
    record = second["generic_criteria"][0]
    assert record["answer_quote"] == "I need it quiet at night."
    assert record["answer_timestamp"] == "2026-10-14T01:00:00+00:00"
    assert record["answer_provenance"] == "server_owned_reply_binding"


def test_same_generic_criterion_can_get_one_explicit_ambiguity_followup():
    q1 = _question(
        criterion_key="quiet", field=None,
        text="What does quiet mean for this room?",
        answer_kind="text", answer_semantics=None,
    )
    first = apply_adaptive_plan(
        _draft(), _extraction(question=q1,
                              criteria=[_criterion("quiet", None, status="captured", verification="unsupported")]),
    )
    current = deepcopy(first)
    current["messages"].append({
        "role": "user", "content": "I'm not sure.",
        "timestamp": "2026-10-14T01:00:00+00:00",
        "reply_to": first["questions"][0],
    })
    q2 = _question(
        criterion_key="quiet", field=None,
        text="Would street noise at night be unacceptable?",
        answer_kind="text", answer_semantics=None,
    )
    second = apply_adaptive_plan(
        current, _extraction(question=q2,
                             criteria=[{**_criterion("quiet", None, status="needs_clarification", verification="unsupported"),
                                        "source_quote": "quiet", "text": "quiet room"}]),
    )
    assert len(second["questions"]) == 1
    assert second["questions"][0]["question"] == "Would street noise at night be unacceptable?"


def test_model_claimed_generic_answer_is_ignored_without_server_reply():
    draft = _draft(generic_criteria=[{
        "key": "quiet", "field": None, "text": "quiet room",
        "source_quote": "quiet", "kind": "requirement",
        "verification": "unsupported", "status": "captured",
        "answer_quote": "the model says yes",
    }])
    result = apply_adaptive_plan(
        draft,
        _extraction(question=None, criteria=[], action="review_required"),
    )
    criterion = result["generic_criteria"][0]
    assert "answer_quote" not in criterion


def test_prior_generic_criteria_survive_a_reviewer_omission():
    draft = _draft(generic_criteria=[{
        "key": "quiet",
        "field": None,
        "text": "quiet room",
        "source_quote": "quiet",
        "kind": "requirement",
        "verification": "unsupported",
        "status": "needs_clarification",
    }])
    extraction = _extraction(criteria=[], question=None, action="review_required")
    result = apply_adaptive_plan(draft, extraction)
    assert result["generic_criteria"][0]["key"] == "quiet"
    assert result["generic_criteria"][0]["field"] is None


def test_unknown_generic_criteria_become_purchase_holding_flags():
    draft = _draft(unsupported=["checked bag"])
    extraction = _extraction(
        criteria=[_criterion("quiet", None, status="needs_clarification", verification="unsupported")],
        question=None,
        action="ready_for_review",
    )
    extraction["adaptive_plan"]["criteria"][0]["source_quote"] = "quiet"
    extraction["adaptive_plan"]["criteria"][0]["text"] = "quiet room"
    result = apply_adaptive_plan(draft, extraction)
    assert result["unsupported"] == ["checked bag", "quiet"]
    assert result["adaptive_plan"]["action"] == "review_required"


def test_read_only_tool_facts_are_retained_as_context_and_not_requirements():
    extraction = _extraction(
        action="inspect_offers",
        question=None,
        criteria=[_criterion()],
        agent_tools=[{"tool": "inspect_offers", "status": "complete", "count": 2}],
        read_only_tool_log={
            "tool": "inspect_offers",
            "read_only": True,
            "offers": [{"id": "offer-a", "signed": True, "facts": {"total_cents": 29500}}],
        },
    )
    result = apply_adaptive_plan(_draft(), extraction)
    assert result["agent_tools"][0]["status"] == "complete"
    assert result["fact_context"]["offers"][0]["facts"]["total_cents"] == 29500
    assert "nonstop" not in result["fields"]


def test_generic_flag_overflow_fails_before_draft_mutation():
    existing = [f"condition-{index}" for index in range(20)]
    draft = _draft(unsupported=existing)
    before = deepcopy(draft)
    extraction = _extraction(
        question=None,
        criteria=[{
            "key": "unknown-extra",
            "field": None,
            "text": "unknown extra",
            "source_quote": "unknown extra",
            "kind": "requirement",
            "verification": "unsupported",
            "status": "needs_clarification",
        }],
        action="review_required",
    )
    import pytest
    with pytest.raises(ValueError, match="Too many flagged generic conditions"):
        apply_adaptive_plan(draft, extraction)
    assert draft == before


def test_general_under_bound_recovers_exact_usd_cents_from_wrong_model_value():
    message = "Find it under $120."
    data = {
        "fields": {"max_total_cents": 12000},
        "sources": {"max_total_cents": "under $120"},
        "unsupported": [], "clarifications": [], "explanation": "Review.",
    }
    recovered = recover_grounded_parts("general", message, data)
    assert recovered is not None
    assert recovered["fields"]["max_total_cents"] == 11999
    assert recovered["sources"]["max_total_cents"] == "under $120"
    assert recovered["clarifications"] == []


def test_non_usd_or_mixed_currency_never_compiles_budget_recovery():
    for message, quote in [
        ("Keep it under €120.", "under €120"),
        ("Keep it under €120 or $150.", "under $150"),
    ]:
        data = {
            "fields": {"max_total_cents": 12000},
            "sources": {"max_total_cents": quote},
            "unsupported": [], "clarifications": [], "explanation": "Review.",
        }
        recovered = recover_grounded_parts("general", message, data)
        assert recovered is None or "max_total_cents" not in recovered["fields"]

