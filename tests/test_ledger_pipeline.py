"""Fixture tests for transactional B orchestration."""

from copy import deepcopy

import pytest

from app import ledger_pipeline
from app.ai_errors import AIServiceError


def _proposal(payload, operation, *, action="ready_for_review", question=None, explanation=""):
    return {
        "expected_revision": payload["ledger_revision"],
        "operations": [operation] if operation else [],
        "action": action,
        "question": question,
        "assistant_message": "Captured the latest requirements.",
        "explanation": explanation,
    }


def _operation(payload, *, op="add", target_id=None, value=29999, text="under $300", ref_index=0):
    ref = payload["customer_source_catalog"][ref_index]["id"]
    return {
        "op": op,
        "target_id": target_id,
        "key": "max_total_cents",
        "field": "max_total_cents",
        "value": value,
        "strength": "required",
        "status": "active",
        "text": text,
        "source_refs": [ref],
        "unit": "total",
    }


def test_ledger_turn_returns_legacy_projection_and_one_call(monkeypatch):
    calls = []
    monkeypatch.delenv("MOCK_LLM", raising=False)
    monkeypatch.setattr(ledger_pipeline, "reserve_ai_calls", lambda *args, **kwargs: calls.append("reserve"))

    def fake(stage, **kwargs):
        calls.append(stage)
        payload = kwargs["payload"]
        return {"proposal": _proposal(payload, _operation(payload)), "trace": {"model": "fixture"}}

    monkeypatch.setattr(ledger_pipeline, "call_model", fake)
    result = ledger_pipeline.run_ledger_pipeline(
        "general", "Find something under $300", "fixture-session", source_text="Find something under $300"
    )

    assert calls == ["reserve", "ledger_plan"]
    assert result["pipeline"] == "ledger"
    assert result["fields"] == {"max_total_cents": 29999}
    assert result["intent_ledger"]["revision"] == 1
    assert result["ledger_transition"]["before_revision"] == 0
    assert result["ledger_transition"]["after_revision"] == 1
    assert result["trace"][0]["raw_proposal"]["operations"]
    assert result["source_metadata"]["merchant_data_separate"] is True


def test_risky_correction_is_reviewed_against_original_base(monkeypatch):
    calls = []
    monkeypatch.delenv("MOCK_LLM", raising=False)
    monkeypatch.setattr(ledger_pipeline, "reserve_ai_calls", lambda *args, **kwargs: calls.append(args[1]))
    base = None

    def fake(stage, **kwargs):
        calls.append(stage)
        payload = kwargs["payload"]
        if payload["ledger_revision"] == 0:
            candidate = _operation(payload, value=29999, text="Under $300")
        else:
            candidate = _operation(
                payload,
                op="replace",
                target_id="r1",
                value=35000,
                text="actually up to $350",
                ref_index=1,
            )
        return {
            "proposal": _proposal(
                payload,
                candidate,
                explanation="correction" if payload["ledger_revision"] else "captured",
            ),
            "trace": {"model": "fixture"},
        }

    monkeypatch.setattr(ledger_pipeline, "call_model", fake)
    first = ledger_pipeline.run_ledger_pipeline(
        "general", "Under $300", "fixture-session", source_messages=[{"role": "user", "content": "Under $300"}]
    )
    # Use a valid current semantic ledger and a second exact customer turn.
    base = {"intent_ledger": deepcopy(first["intent_ledger"]), "adaptive_plan": first["adaptive_plan"]}
    result = ledger_pipeline.run_ledger_pipeline(
        "general",
        "Actually up to $350",
        "fixture-session",
        source_messages=[
            {"role": "user", "content": "Under $300"},
            {"role": "user", "content": "Actually up to $350"},
        ],
        current_draft=base,
    )

    assert calls[0:2] == [1, "ledger_plan"]
    assert calls[2:] == [1, "ledger_plan", 1, "ledger_review"]
    assert result["ledger_transition"]["reviewed"] is True
    assert result["fields"]["max_total_cents"] == 35000
    assert all(trace["base_revision"] == 1 for trace in result["trace"])


def test_stale_question_is_suppressed_without_replacement_text(monkeypatch):
    monkeypatch.delenv("MOCK_LLM", raising=False)
    monkeypatch.setattr(ledger_pipeline, "reserve_ai_calls", lambda *args, **kwargs: None)

    question = {
        "criterion_key": "max_total_cents",
        "field": "max_total_cents",
        "text": "What is your maximum all-in price?",
        "why": "The maximum changes which offers can be reviewed.",
        "answer_kind": "number",
        "answer_semantics": "requirement_boolean",
        "options": [],
    }

    def fake(stage, **kwargs):
        payload = kwargs["payload"]
        return {
            "proposal": {
                **_proposal(payload, None, action="ask_user", question=question),
                "assistant_message": question["text"],
            },
            "trace": {"model": "fixture"},
        }

    monkeypatch.setattr(ledger_pipeline, "call_model", fake)
    ledger = {
        "revision": 1,
        "records": [
            {
                "id": "r1",
                "key": "max_total_cents",
                "field": "max_total_cents",
                "value": 29999,
                "unit": "total",
                "strength": "required",
                "status": "active",
                "text": "under $300",
                "source_refs": [],
            }
        ],
        "history": [],
    }
    result = ledger_pipeline.run_ledger_pipeline(
        "general",
        "Thanks",
        "fixture-session",
        source_text="Thanks",
        current_draft={
            "intent_ledger": ledger,
            "adaptive_plan": {
                "question": question,
                "assistant_message": "What is your maximum all-in price?",
            },
        },
    )

    assert result["adaptive_plan"]["question"] is None
    assert result["adaptive_plan"]["action"] == "review_required"
    assert result["adaptive_plan"]["assistant_message"] == ""
    assert result["ledger_transition"]["question_suppressed"] in {
        "question_target_already_resolved",
        "question_repeated",
    }


def test_model_can_ask_about_a_new_unresolved_semantic_record(monkeypatch):
    monkeypatch.delenv("MOCK_LLM", raising=False)
    monkeypatch.setattr(ledger_pipeline, "reserve_ai_calls", lambda *args, **kwargs: None)

    def fake(stage, **kwargs):
        payload = kwargs["payload"]
        return {
            "proposal": {
                "expected_revision": payload["ledger_revision"],
                "operations": [{
                    "op": "add",
                    "target_id": None,
                    "key": "quiet_hours",
                    "field": None,
                    "value": None,
                    "strength": "required",
                    "status": "needs_clarification",
                    "text": "quiet hours are requested but not defined",
                    "source_refs": [payload["customer_source_catalog"][0]["id"]],
                    "unit": None,
                }],
                "action": "ask_user",
                "question": {
                    "criterion_key": "quiet_hours",
                    "field": None,
                    "text": "What quiet hours should apply?",
                    "why": "The answer changes which stays can be reviewed.",
                    "answer_kind": "text",
                    "answer_semantics": "requirement_boolean",
                    "options": [],
                },
                "assistant_message": "I need one detail about quiet hours.",
                "explanation": "The customer request is unresolved.",
            },
            "trace": {"model": "fixture"},
        }

    monkeypatch.setattr(ledger_pipeline, "call_model", fake)
    result = ledger_pipeline.run_ledger_pipeline(
        "general", "Quiet hours matter", "fixture-session", source_text="Quiet hours matter"
    )

    assert result["adaptive_plan"]["action"] == "ask_user"
    assert result["adaptive_plan"]["question"]["criterion_key"] == "quiet_hours"
    assert result["intent_ledger"]["records"][0]["status"] == "needs_clarification"
    assert result["unsupported"] == ["quiet hours are requested but not defined"]


def test_invalid_first_batch_gets_one_bounded_review_with_validator_feedback(monkeypatch):
    calls = []
    monkeypatch.delenv("MOCK_LLM", raising=False)
    monkeypatch.setattr(ledger_pipeline, "reserve_ai_calls", lambda *args, **kwargs: calls.append("reserve"))

    def fake(stage, **kwargs):
        calls.append(stage)
        payload = kwargs["payload"]
        operation = _operation(payload)
        if stage == "ledger_plan":
            operation["source_refs"] = ["spoofed-source-id"]
            proposal = _proposal(payload, operation)
        else:
            assert payload["review_base_ledger"]["revision"] == 0
            assert payload["candidate_proposal_withheld"] is True
            assert "candidate_proposal" not in payload
            assert payload["validator_feedback"]["code"] == "invalid_proposal"
            proposal = _proposal(payload, _operation(payload))
        return {"proposal": proposal, "trace": {"model": "fixture"}}

    monkeypatch.setattr(ledger_pipeline, "call_model", fake)
    result = ledger_pipeline.run_ledger_pipeline(
        "general", "Find something under $300", "fixture-session",
        source_text="Find something under $300",
    )

    assert calls == ["reserve", "ledger_plan", "reserve", "ledger_review"]
    assert result["ledger_transition"]["reviewed"] is True
    assert result["fields"] == {"max_total_cents": 29999}
    assert result["trace"][0]["validator_feedback"]["kind"] == "source_binding"


def test_noncooperative_review_cannot_return_ready_with_required_gap(monkeypatch):
    calls = []
    monkeypatch.delenv("MOCK_LLM", raising=False)
    monkeypatch.setattr(ledger_pipeline, "reserve_ai_calls", lambda *args, **kwargs: calls.append("reserve"))

    def fake(stage, **kwargs):
        calls.append(stage)
        payload = kwargs["payload"]
        if stage == "ledger_review":
            assert payload["missing_required_fields"] == [
                "origin_airports",
                "destination_airports",
                "departure_date",
            ]
        # The reviewer is deliberately noncooperative: it repeats a ready
        # proposal with no question and leaves all required flight gaps open.
        return {
            "proposal": _proposal(payload, _operation(payload)),
            "trace": {"model": "fixture"},
        }

    monkeypatch.setattr(ledger_pipeline, "call_model", fake)
    with pytest.raises(AIServiceError) as raised:
        ledger_pipeline.run_ledger_pipeline(
            "flight",
            "Find a flight under $500",
            "fixture-session",
            source_text="Find a flight under $500",
        )

    assert calls == ["reserve", "ledger_plan", "reserve", "ledger_review"]
    assert raised.value.review_required is True
    assert raised.value.validator_feedback["kind"] == "missing_required_question"
    assert raised.value.validator_feedback["missing_required_fields"] == [
        "origin_airports",
        "destination_airports",
        "departure_date",
    ]
    assert raised.value.preserved_ledger["revision"] == 0


def test_review_can_return_one_model_question_for_remaining_required_gap(monkeypatch):
    calls = []
    monkeypatch.delenv("MOCK_LLM", raising=False)
    monkeypatch.setattr(ledger_pipeline, "reserve_ai_calls", lambda *args, **kwargs: calls.append("reserve"))

    question = {
        "criterion_key": "origin_airports",
        "field": "origin_airports",
        "text": "Which departure airports are acceptable?",
        "why": "The answer changes which flights can be reviewed.",
        "answer_kind": "multi",
        "answer_semantics": "requirement_boolean",
        "options": [],
    }

    def fake(stage, **kwargs):
        calls.append(stage)
        payload = kwargs["payload"]
        operation = _operation(payload)
        if stage == "ledger_review":
            proposal = _proposal(payload, operation, action="ask_user", question=question)
        else:
            proposal = _proposal(payload, operation)
        return {"proposal": proposal, "trace": {"model": "fixture"}}

    monkeypatch.setattr(ledger_pipeline, "call_model", fake)
    result = ledger_pipeline.run_ledger_pipeline(
        "flight",
        "Find a flight under $500",
        "fixture-session",
        source_text="Find a flight under $500",
    )

    assert calls == ["reserve", "ledger_plan", "reserve", "ledger_review"]
    assert result["adaptive_plan"]["action"] == "ask_user"
    assert result["adaptive_plan"]["question"]["field"] == "origin_airports"
    assert result["missing_required_fields"] == [
        "origin_airports",
        "destination_airports",
        "departure_date",
    ]


def test_question_guard_uses_latest_nonterminal_record_after_replacement(monkeypatch):
    monkeypatch.delenv("MOCK_LLM", raising=False)
    monkeypatch.setattr(ledger_pipeline, "reserve_ai_calls", lambda *args, **kwargs: None)
    question = {
        "criterion_key": "quiet_hours",
        "field": None,
        "text": "What quiet hours should apply?",
        "why": "The answer changes which stays can be reviewed.",
        "answer_kind": "text",
        "answer_semantics": "requirement_boolean",
        "options": [],
    }

    def fake(stage, **kwargs):
        payload = kwargs["payload"]
        return {
            "proposal": {
                **_proposal(payload, None, action="ask_user", question=question),
                "assistant_message": question["text"],
            },
            "trace": {"model": "fixture"},
        }

    monkeypatch.setattr(ledger_pipeline, "call_model", fake)
    catalog_text = "Quiet hours should be quiet, but I am unsure of the exact period."
    source_catalog = ledger_pipeline.build_source_catalog(catalog_text, [{"role": "user", "content": catalog_text}])
    ledger = {
        "revision": 1,
        "records": [
            {
                "id": "r1", "key": "quiet_hours", "field": None, "value": None,
                "unit": None, "strength": "required", "status": "superseded",
                "text": "older quiet-hours request", "source_refs": [source_catalog[0]["id"]],
            },
            {
                "id": "r2", "key": "quiet_hours", "field": None, "value": None,
                "unit": None, "strength": "required", "status": "needs_clarification",
                "text": "new quiet-hours request", "source_refs": [source_catalog[0]["id"]],
            },
        ],
        "history": [],
    }
    result = ledger_pipeline.run_ledger_pipeline(
        "general", catalog_text, "fixture-session", source_text=catalog_text,
        current_draft={"intent_ledger": ledger},
    )

    assert result["adaptive_plan"]["action"] == "ask_user"
    assert result["adaptive_plan"]["question"]["criterion_key"] == "quiet_hours"


@pytest.mark.parametrize(
    "domain,message,field,value,unit,reason",
    [
        ("general", "My budget is $300", "max_total_cents", 30000, "total", "money"),
        ("flight", "I want to travel on March 14, 2027", "departure_date", "2027-03-14", None, "date"),
    ],
)
def test_question_ignoring_latest_date_or_money_literal_gets_review(
    monkeypatch, domain, message, field, value, unit, reason
):
    calls = []
    monkeypatch.delenv("MOCK_LLM", raising=False)
    monkeypatch.setattr(ledger_pipeline, "reserve_ai_calls", lambda *args, **kwargs: calls.append("reserve"))
    question = {
        "criterion_key": field,
        "field": field,
        "text": f"What is your {field}?",
        "why": "The answer changes which requirements can be reviewed.",
        "answer_kind": "date_choice" if reason == "date" else "number",
        "answer_semantics": "requirement_boolean",
        "options": [],
    }

    def fake(stage, **kwargs):
        calls.append(stage)
        payload = kwargs["payload"]
        if stage == "ledger_plan":
            return {
                "proposal": _proposal(payload, None, action="ask_user", question=question),
                "trace": {"model": "fixture"},
            }
        operation = _operation(payload, value=value, text=message)
        operation["key"] = field
        operation["field"] = field
        operation["unit"] = unit
        return {
            "proposal": _proposal(payload, operation, explanation="captured from latest turn"),
            "trace": {"model": "fixture"},
        }

    monkeypatch.setattr(ledger_pipeline, "call_model", fake)
    result = ledger_pipeline.run_ledger_pipeline(
        domain, message, "fixture-session", source_text=message,
    )

    assert calls == ["reserve", "ledger_plan", "reserve", "ledger_review"]
    assert result["ledger_transition"]["reviewed"] is True
    assert any(
        item.startswith("question_target_has_latest_")
        for item in result["ledger_transition"]["review_reasons"]
    )


def test_reply_to_question_is_separate_from_quotable_customer_source(monkeypatch):
    monkeypatch.delenv("MOCK_LLM", raising=False)
    monkeypatch.setattr(ledger_pipeline, "reserve_ai_calls", lambda *args, **kwargs: None)
    seen = {}

    def fake(stage, **kwargs):
        seen["payload"] = kwargs["payload"]
        return {
            "proposal": _proposal(
                kwargs["payload"],
                _operation(kwargs["payload"], value=30000, text="300"),
            ),
            "trace": {"model": "fixture"},
        }

    monkeypatch.setattr(ledger_pipeline, "call_model", fake)
    reply = {
        "question_id": "q1",
        "criterion_key": "max_total_cents",
        "field": "max_total_cents",
        "text": "What is your maximum total?",
        "why": "The answer changes review.",
        "answer_kind": "number",
        "answer_semantics": "requirement_boolean",
        "options": [],
    }
    ledger_pipeline.run_ledger_pipeline(
        "general", "300", "fixture-session", source_messages=[
            {"role": "assistant", "content": reply["text"]},
            {"role": "user", "content": "300", "reply_to": reply},
        ],
    )

    turn = seen["payload"]["customer_turns"][-1]
    assert turn["reply_context"]["question_id"] == "q1"
    assert turn["reply_context"]["criterion_key"] == "max_total_cents"
    assert "reply_to" not in turn
    assert all(item["text"] == "300" for item in seen["payload"]["customer_source_catalog"])


def test_prompt_contract_separates_money_currency_from_scope_and_definitions():
    capabilities = ledger_pipeline._profile_capabilities("flight")
    prompt = ledger_pipeline._prompt("flight", "ledger_plan", capabilities=capabilities)

    assert capabilities["fields"]["nonstop"]["question"]
    assert capabilities["fields"]["departure_date"]["question"]
    assert "integer number of" in prompt
    assert "profile_capabilities.currency" in prompt
    assert "Never put a currency name" in prompt
    assert "all_in_total" in prompt
    assert "STRUCTURAL EXAMPLE ONLY" in prompt
    assert "expected_revision must copy ledger_revision exactly" in prompt
    assert "semantic_exclusions" in prompt
    assert "does not establish nonstop" in prompt
    assert "exclusive" in prompt
    assert "no_preference only when the customer explicitly declines" in prompt
    assert "inventory every independent substantive customer condition" in prompt
    assert "unsupported or unresolved hard customer requirement" in prompt
    assert "unsupported or unresolved soft preference" in prompt
    assert "Never infer defaults" in prompt
    assert "date tolerance" in prompt
    assert "scope; do not normalize it to all_in_total" in prompt
    assert "Item or service category and intended use are customer intent" in prompt
    assert "Every explicit customer no-preference or decline" in prompt
    assert "exactly ONE specific model-generated question" in prompt
    assert "never use ready_for_review while an answerable required gap remains" in prompt
    assert "unsupported customer meaning is already clear" in prompt


def test_review_prompt_withholds_candidate_and_requires_clause_coverage():
    capabilities = ledger_pipeline._profile_capabilities("general")
    prompt = ledger_pipeline._prompt("general", "ledger_review", capabilities=capabilities)

    assert "first proposal is deliberately withheld" in prompt
    assert "Reconstruct the complete operation batch independently" in prompt
    assert "Each independent customer condition must be represented once" in prompt


def test_canonical_all_in_total_money_does_not_trigger_review(monkeypatch):
    calls = []
    monkeypatch.delenv("MOCK_LLM", raising=False)
    monkeypatch.setattr(ledger_pipeline, "reserve_ai_calls", lambda *args, **kwargs: calls.append("reserve"))

    def fake(stage, **kwargs):
        calls.append(stage)
        payload = kwargs["payload"]
        operation = _operation(payload, value=50000, text="up to $500")
        operation["unit"] = "all_in_total"
        return {"proposal": _proposal(payload, operation), "trace": {"model": "fixture"}}

    monkeypatch.setattr(ledger_pipeline, "call_model", fake)
    result = ledger_pipeline.run_ledger_pipeline(
        "general", "Up to $500 all-in", "fixture-session", source_text="Up to $500 all-in"
    )

    assert calls == ["reserve", "ledger_plan"]
    assert result["fields"] == {"max_total_cents": 50000}


def test_typed_money_scope_triggers_review_when_operation_unit_is_null(monkeypatch):
    calls = []
    monkeypatch.delenv("MOCK_LLM", raising=False)
    monkeypatch.setattr(ledger_pipeline, "reserve_ai_calls", lambda *args, **kwargs: calls.append("reserve"))

    def fake(stage, **kwargs):
        calls.append(stage)
        payload = kwargs["payload"]
        operation = _operation(
            payload,
            value={"amount": 220, "currency": "USD", "scope": "per_night"},
            text="220 USD per night",
        )
        operation["unit"] = None
        return {"proposal": _proposal(payload, operation), "trace": {"model": "fixture"}}

    monkeypatch.setattr(ledger_pipeline, "call_model", fake)
    result = ledger_pipeline.run_ledger_pipeline(
        "general", "Budget is 220 USD per night", "fixture-session",
        source_text="Budget is 220 USD per night",
    )

    assert calls == ["reserve", "ledger_plan", "reserve", "ledger_review"]
    assert result["ledger_transition"]["reviewed"] is True
    assert "typed_money_scope" in result["ledger_transition"]["review_reasons"]
    assert result["unsupported"] == ["220 USD per night"]


def test_reviewer_cannot_broaden_scoped_money_to_all_in_total(monkeypatch):
    calls = []
    monkeypatch.delenv("MOCK_LLM", raising=False)
    monkeypatch.setattr(ledger_pipeline, "reserve_ai_calls", lambda *args, **kwargs: calls.append("reserve"))

    def fake(stage, **kwargs):
        calls.append(stage)
        payload = kwargs["payload"]
        if stage == "ledger_plan":
            operation = _operation(
                payload,
                value={"amount": 350, "currency": "USD", "scope": "per_person"},
                text="$350 per person",
            )
            operation["unit"] = None
        else:
            # This is the unsafe reviewer rewrite observed in blind UAT. The
            # pipeline must not guess whether the conversion is valid.
            operation = _operation(payload, value=35000, text="$350 total")
            operation["unit"] = "all_in_total"
        return {"proposal": _proposal(payload, operation), "trace": {"model": "fixture"}}

    monkeypatch.setattr(ledger_pipeline, "call_model", fake)
    with pytest.raises(AIServiceError) as raised:
        ledger_pipeline.run_ledger_pipeline(
            "general",
            "$350 per person",
            "fixture-session",
            source_text="$350 per person",
        )

    assert calls == ["reserve", "ledger_plan", "reserve", "ledger_review"]
    assert raised.value.code == "ai_interpretation"
    assert raised.value.review_required is True
    assert "review_scope_normalization" in raised.value.review_reasons
    assert raised.value.validator_feedback["kind"] == "review_scope_normalization"
    assert raised.value.preserved_ledger["revision"] == 0


def test_rich_source_spans_trigger_source_first_coverage_review(monkeypatch):
    calls = []
    monkeypatch.delenv("MOCK_LLM", raising=False)
    monkeypatch.setattr(ledger_pipeline, "reserve_ai_calls", lambda *args, **kwargs: calls.append("reserve"))
    source = "Under $300 and headphones with USB-C and neutral color."

    def fake(stage, **kwargs):
        calls.append(stage)
        payload = kwargs["payload"]
        catalog = payload["customer_source_catalog"]
        granular = [item["id"] for item in catalog if "p0e" not in item["id"]]
        operation = _operation(payload, text="under $300 and the remaining customer clauses")
        if stage == "ledger_plan":
            # Deliberately cite only one local span: coverage review is
            # required before this can be committed.
            operation["source_refs"] = granular[:1] or [catalog[0]["id"]]
        else:
            # The independent reviewer cites each local span while keeping one
            # semantic operation. This is enough for the structural gate; it
            # does not infer values for the non-money clauses.
            operation["source_refs"] = granular or [catalog[0]["id"]]
        return {"proposal": _proposal(payload, operation), "trace": {"model": "fixture"}}

    monkeypatch.setattr(ledger_pipeline, "call_model", fake)
    result = ledger_pipeline.run_ledger_pipeline(
        "general", source, "fixture-session", source_text=source
    )

    assert calls == ["reserve", "ledger_plan", "reserve", "ledger_review"]
    assert result["ledger_transition"]["reviewed"] is True
    assert "source_coverage_review" in result["ledger_transition"]["review_reasons"]


def test_old_rich_turn_does_not_force_coverage_refs_on_latest_correction(monkeypatch):
    calls = []
    monkeypatch.delenv("MOCK_LLM", raising=False)
    monkeypatch.setattr(ledger_pipeline, "reserve_ai_calls", lambda *args, **kwargs: calls.append("reserve"))
    old_source = "Under $300 and headphones with USB-C and neutral color."
    latest_source = "Actually up to $350."
    base = {
        "intent_ledger": {
            "revision": 1,
            "records": [{
                "id": "r1",
                "key": "max_total_cents",
                "field": "max_total_cents",
                "value": 29999,
                "unit": "total",
                "strength": "required",
                "status": "active",
                "text": "under $300",
                "source_refs": [],
            }],
            "history": [],
        }
    }

    def fake(stage, **kwargs):
        calls.append(stage)
        payload = kwargs["payload"]
        operation = _operation(
            payload,
            op="replace",
            target_id="r1",
            value=35000,
            text="Actually up to $350",
            ref_index=1,
        )
        return {"proposal": _proposal(payload, operation, explanation="correction"), "trace": {"model": "fixture"}}

    monkeypatch.setattr(ledger_pipeline, "call_model", fake)
    result = ledger_pipeline.run_ledger_pipeline(
        "general",
        latest_source,
        "fixture-session",
        source_messages=[
            {"role": "user", "content": old_source},
            {"role": "user", "content": latest_source},
        ],
        current_draft=base,
    )

    assert calls == ["reserve", "ledger_plan", "reserve", "ledger_review"]
    assert "source_coverage_review" not in result["ledger_transition"]["review_reasons"]
    assert result["fields"] == {"max_total_cents": 35000}


def test_linked_strict_predicate_expansion_is_reviewed_and_reproposed(monkeypatch):
    calls = []
    monkeypatch.delenv("MOCK_LLM", raising=False)
    monkeypatch.setattr(ledger_pipeline, "reserve_ai_calls", lambda *args, **kwargs: calls.append("reserve"))

    def operation(payload, *, field, key, value, text):
        return {
            "op": "add",
            "target_id": None,
            "key": key,
            "field": field,
            "value": value,
            "strength": "required",
            "status": "active",
            "text": text,
            "source_refs": [payload["customer_source_catalog"][0]["id"]],
            "unit": None,
        }

    def fake(stage, **kwargs):
        calls.append(stage)
        payload = kwargs["payload"]
        max_connections = operation(
            payload,
            field="max_connections",
            key="max_connections",
            value=0,
            text="no connections",
        )
        if stage == "ledger_plan":
            proposal = _proposal(
                payload,
                max_connections,
                action="ask_user",
                question={
                    "criterion_key": "origin_airports",
                    "field": "origin_airports",
                    "text": "Which departure airports are acceptable?",
                    "why": "The answer changes which flights can be reviewed.",
                    "answer_kind": "multi",
                    "answer_semantics": "requirement_boolean",
                    "options": [],
                },
            )
            proposal["operations"].append(operation(
                payload,
                field="nonstop",
                key="nonstop",
                value=True,
                text="no connections",
            ))
        else:
            # The source-first reviewer removes the stronger predicate after
            # rereading the exact source. The backend does not rewrite the
            # candidate or silently infer an unsupported technical-stop fact.
            proposal = _proposal(
                payload,
                max_connections,
                action="ask_user",
                question={
                    "criterion_key": "origin_airports",
                    "field": "origin_airports",
                    "text": "Which departure airports are acceptable?",
                    "why": "The answer changes which flights can be reviewed.",
                    "answer_kind": "multi",
                    "answer_semantics": "requirement_boolean",
                    "options": [],
                },
            )
        return {"proposal": proposal, "trace": {"model": "fixture"}}

    monkeypatch.setattr(ledger_pipeline, "call_model", fake)
    result = ledger_pipeline.run_ledger_pipeline(
        "flight", "No connections.", "fixture-session", source_text="No connections."
    )

    assert calls == ["reserve", "ledger_plan", "reserve", "ledger_review"]
    assert result["ledger_transition"]["reviewed"] is True
    assert "linked_strict_field_expansion" in result["ledger_transition"]["review_reasons"]
    assert result["fields"] == {"max_connections": 0}
    assert "nonstop" not in result["fields"]
    assert len(result["trace"][0]["raw_proposal"]["operations"]) == 2
    assert len(result["trace"][1]["raw_proposal"]["operations"]) == 1


def test_uncooperative_linked_review_fails_closed_and_preserves_base(monkeypatch):
    calls = []
    monkeypatch.delenv("MOCK_LLM", raising=False)
    monkeypatch.setattr(ledger_pipeline, "reserve_ai_calls", lambda *args, **kwargs: calls.append("reserve"))

    def operation(payload, *, field, key, value):
        return {
            "op": "add",
            "target_id": None,
            "key": key,
            "field": field,
            "value": value,
            "strength": "required",
            "status": "active",
            "text": "no connections",
            "source_refs": [payload["customer_source_catalog"][0]["id"]],
            "unit": None,
        }

    def fake(stage, **kwargs):
        calls.append(stage)
        payload = kwargs["payload"]
        proposal = _proposal(payload, operation(
            payload, field="max_connections", key="max_connections", value=0,
        ), action="ask_user", question={
            "criterion_key": "origin_airports",
            "field": "origin_airports",
            "text": "Which departure airports are acceptable?",
            "why": "The answer changes which flights can be reviewed.",
            "answer_kind": "multi",
            "answer_semantics": "requirement_boolean",
            "options": [],
        })
        proposal["operations"].append(operation(
            payload, field="nonstop", key="nonstop", value=True,
        ))
        return {"proposal": proposal, "trace": {"model": "fixture"}}

    monkeypatch.setattr(ledger_pipeline, "call_model", fake)
    with pytest.raises(AIServiceError) as raised:
        ledger_pipeline.run_ledger_pipeline(
            "flight", "No connections.", "fixture-session", source_text="No connections."
        )

    assert calls == ["reserve", "ledger_plan", "reserve", "ledger_review"]
    assert raised.value.code == "ai_interpretation"
    assert raised.value.review_required is True
    assert "linked_strict_field_expansion" in raised.value.review_reasons
    assert raised.value.preserved_ledger["revision"] == 0
    assert raised.value.validator_feedback["kind"] == "linked_strictness_unresolved"


def test_review_capacity_error_preserves_previous_ledger(monkeypatch):
    monkeypatch.delenv("MOCK_LLM", raising=False)
    reservations = iter([None, AIServiceError("ai_budget_limit", "capacity")])

    def reserve(*args, **kwargs):
        value = next(reservations)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(ledger_pipeline, "reserve_ai_calls", reserve)

    def fake(stage, **kwargs):
        payload = kwargs["payload"]
        return {
            "proposal": _proposal(
                payload,
                _operation(payload, op="add", text="budget in a foreign currency", ref_index=0),
                explanation="currency scope is unclear",
            ),
            "trace": {"model": "fixture"},
        }

    monkeypatch.setattr(ledger_pipeline, "call_model", fake)
    with pytest.raises(AIServiceError) as raised:
        ledger_pipeline.run_ledger_pipeline(
            "general", "Budget in a foreign currency", "fixture-session", source_text="Budget in a foreign currency"
        )
    assert raised.value.code == "ai_budget_limit"
    assert raised.value.review_required is True
    assert raised.value.preserved_ledger["revision"] == 0

