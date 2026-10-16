"""Provider-free checks for the one-call adaptive fast path."""

from copy import deepcopy


def _plan(*, action="ready_for_review", fields=None, sources=None):
    return {
        "action": action,
        "assistant_message": "I captured the request for your review.",
        "question": None,
        "criteria": [],
        "offer_observations": [],
        "fields": fields or {"max_total_cents": 9999},
        "sources": sources or {"max_total_cents": "under $100"},
        "unsupported": [],
        "clarifications": [],
        "explanation": "The captured condition remains unapproved until review.",
    }


def test_adaptive_fast_ordinary_turn_calls_provider_once_and_reserves_one(monkeypatch):
    from app.ai_pipeline import run_pipeline

    calls = []
    reservations = []
    response = _plan()

    def fake_call(stage, *args, **kwargs):
        calls.append(stage)
        assert kwargs["compact_adaptive_payload"] is True
        return deepcopy(response), {"stage": stage, "tokens": {}}

    monkeypatch.setenv("MOCK_LLM", "0")
    monkeypatch.setattr(
        "app.ai_pipeline.reserve_ai_calls",
        lambda session, count, purpose="interactive": reservations.append((count, purpose)),
    )
    monkeypatch.setattr("app.ai_pipeline.call_json", fake_call)

    result = run_pipeline("general", "Find a lamp under $100", "fast-session", variant="adaptive_fast")

    assert calls == ["adaptive_plan"]
    assert reservations == [(1, "interactive")]
    assert result["pipeline"] == "adaptive_fast"
    assert len(result["trace"]) == 1
    assert result["trace"][0]["review_skipped"] == "no_read_only_observation"


def test_adaptive_fast_reserves_second_call_only_after_model_tool_observation(monkeypatch):
    from app.ai_pipeline import run_pipeline

    calls = []
    reservations = []
    candidate = _plan(action="retrieve_policy")
    reviewed = _plan(action="review_required")

    def fake_call(stage, *args, **kwargs):
        calls.append((stage, kwargs.get("tool_result")))
        return deepcopy(candidate if stage == "adaptive_plan" else reviewed), {
            "stage": stage,
            "tokens": {},
        }

    def fake_tool(action, *, domain, fields):
        assert action == "retrieve_policy"
        return {"tool": action, "status": "ok", "read_only": True, "summary": "policy"}

    monkeypatch.setenv("MOCK_LLM", "0")
    monkeypatch.setattr(
        "app.ai_pipeline.reserve_ai_calls",
        lambda session, count, purpose="interactive": reservations.append((count, purpose)),
    )
    monkeypatch.setattr("app.ai_pipeline.call_json", fake_call)
    monkeypatch.setattr("app.ai_pipeline.execute_tool", fake_tool)

    result = run_pipeline("general", "Find a lamp under $100", "tool-session", variant="adaptive_fast")

    assert [stage for stage, _ in calls] == ["adaptive_plan", "adaptive_review"]
    assert calls[0][1] is None
    assert calls[1][1]["tool"] == "retrieve_policy"
    assert reservations == [(1, "interactive"), (1, "interactive")]
    assert len(result["trace"]) == 2


def test_adaptive_fast_holds_grounded_candidate_when_review_capacity_is_exhausted(monkeypatch):
    from app.ai_errors import AIServiceError
    from app.ai_pipeline import run_pipeline

    calls = []
    reservations = []
    candidate = _plan(action="retrieve_policy")

    def fake_call(stage, *args, **kwargs):
        calls.append(stage)
        return deepcopy(candidate), {"stage": stage, "tokens": {}}

    def fake_reserve(session, count, purpose="interactive"):
        reservations.append((count, purpose))
        if len(reservations) == 2:
            raise AIServiceError(
                "ai_session_limit",
                "The session has no review capacity left.",
                status_code=429,
            )

    def fake_tool(action, *, domain, fields):
        assert action == "retrieve_policy"
        return {
            "tool": action,
            "status": "ok",
            "read_only": True,
            "summary": "policy",
        }

    monkeypatch.setenv("MOCK_LLM", "0")
    monkeypatch.setattr("app.ai_pipeline.reserve_ai_calls", fake_reserve)
    monkeypatch.setattr("app.ai_pipeline.call_json", fake_call)
    monkeypatch.setattr("app.ai_pipeline.execute_tool", fake_tool)

    result = run_pipeline(
        "general",
        "Find a lamp under $100",
        "capacity-session",
        variant="adaptive_fast",
    )

    assert calls == ["adaptive_plan"]
    assert reservations == [(1, "interactive"), (1, "interactive")]
    assert result["fields"]["max_total_cents"] == 9999
    assert result["adaptive_plan"]["action"] == "review_required"
    assert result["adaptive_plan"]["question"] is None
    assert result["next_step"] == "review_required"
    assert result["review_deferred"] is True
    assert result["review_warning"]["code"] == "ai_session_limit"
    assert result["review_warning"]["kind"] == "adaptive_review_capacity_unavailable"
    assert result["review_warning"]["candidate_preserved"] is True
    assert result["review_warning"]["review_ran"] is False
    assert result["read_only_tool_log"]["tool"] == "retrieve_policy"
    assert result["read_only_tool_log"]["read_only"] is True
    assert len(result["trace"]) == 1
    assert result["trace"][0]["review_skipped"] == "capacity_unavailable"
    assert result["trace"][0]["read_only_tool_observation"]["tool"] == "retrieve_policy"

    # The API bridge must retain the system warning separately from AI prose,
    # and a later successful pass must clear the temporary status.
    from app.conversation import apply_adaptive_plan, provenance
    draft = apply_adaptive_plan({"domain": "general", **result}, result)
    assert draft["review_deferred"] is True
    assert draft["review_warning"] == result["review_warning"]
    assert provenance(result, 1)["review_deferred"] is True
    completed = {**result, "review_deferred": False, "review_warning": None}
    updated = apply_adaptive_plan(draft, completed)
    assert updated["review_deferred"] is False
    assert "review_warning" not in updated


def test_adaptive_fast_does_not_add_reviewer_to_server_required_offer_preview(monkeypatch):
    from app.ai_pipeline import run_pipeline

    calls = []
    reservations = []
    response = _plan(
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

    def fake_call(stage, *args, **kwargs):
        calls.append(stage)
        return deepcopy(response), {"stage": stage, "tokens": {}}

    def fake_tool(action, *, domain, fields):
        assert action == "inspect_offers"
        return {"tool": action, "status": "ok", "read_only": True, "offers": []}

    monkeypatch.setenv("MOCK_LLM", "0")
    monkeypatch.setattr(
        "app.ai_pipeline.reserve_ai_calls",
        lambda session, count, purpose="interactive": reservations.append((count, purpose)),
    )
    monkeypatch.setattr("app.ai_pipeline.call_json", fake_call)
    monkeypatch.setattr("app.ai_pipeline.execute_tool", fake_tool)

    result = run_pipeline(
        "flight",
        "EWR to MCO on 2026-11-12 under $300",
        "preview-session",
        variant="adaptive_fast",
    )

    assert calls == ["adaptive_plan"]
    assert reservations == [(1, "interactive")]
    assert result["read_only_tool_log"]["status"] == "ok"
    assert len(result["trace"]) == 1


def test_adaptive_fast_compacts_duplicate_context_but_keeps_customer_bindings():
    from app.ai_pipeline import _compact_current_draft, _compact_source_messages

    messages = [{
        "role": "user",
        "content": "no layovers",
        "timestamp": "2026-10-16T10:00:00Z",
        "reply_to": {
            "question_id": "q1",
            "question": "How many connections?",
            "criterion_key": "max_connections",
            "ui_rendered_copy": "discard this UI field",
        },
        "large_ui_state": "discard this duplicate state",
    }]
    draft = {
        "revision": 3,
        "fields": {"max_connections": 0},
        "sources": {"max_connections": "no layovers"},
        "criteria": [],
        "adaptive_plan": {"assistant_message": "old model trace"},
        "offer_context": {"offers": ["old merchant context"]},
    }

    compact_messages = _compact_source_messages(messages)
    compact_draft = _compact_current_draft(draft)

    assert compact_messages[0]["content"] == "no layovers"
    assert compact_messages[0]["reply_to"]["criterion_key"] == "max_connections"
    assert "large_ui_state" not in compact_messages[0]
    assert compact_draft["fields"] == {"max_connections": 0}
    assert "adaptive_plan" not in compact_draft
    assert "offer_context" not in compact_draft
