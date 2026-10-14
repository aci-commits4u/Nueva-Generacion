"""Provider-free regression tests for adaptive planner rejection feedback."""

from copy import deepcopy

import pytest


@pytest.fixture
def mocked_pipeline(monkeypatch):
    """Enable only the fake provider path used by this file's pipeline tests."""
    monkeypatch.setenv("MOCK_LLM", "0")


def _envelope(*, fields=None, sources=None, clarifications=None):
    return {
        "fields": fields or {},
        "sources": sources or {},
        "unsupported": [],
        "clarifications": clarifications or [],
        "explanation": "Review the request.",
    }


def _hotel_plan(*, question, criterion_key="nightly_budget", action="ask_user"):
    quote = "roughly €140 a night"
    return {
        "action": action,
        "assistant_message": "I need one useful detail before continuing.",
        "question": question,
        "criteria": [{
            "key": criterion_key,
            "field": None,
            "text": quote,
            "source_quote": quote,
            "kind": "ambiguity",
            "status": "needs_clarification",
            "verification": "unsupported",
        }],
        "offer_observations": [],
        **_envelope(
            fields={
                "city": "Tbilisi",
                "checkin_date": "2027-04-03",
                "checkout_date": "2027-04-07",
            },
            sources={
                "city": "Tbilisi",
                "checkin_date": "April 3, 2027",
                "checkout_date": "April 7, 2027",
            },
            clarifications=[{
                "field": "max_total_cents",
                "source_quote": quote,
                "reason": "ambiguity",
            }],
        ),
    }


def _question(key, *, field=None, why="The answer changes which hotel offers can satisfy the request.",
              answer_kind="text"):
    return {
        "criterion_key": key,
        "field": field,
        "text": "What all-in total should I use for the complete stay?",
        "why": why,
        "answer_kind": answer_kind,
        "options": [],
    }


def test_feedback_is_bounded_and_names_only_source_backed_repair_targets():
    from app.adaptive_intent import planner_question_validation_feedback

    diagnostic = planner_question_validation_feedback(
        _question("nightly_budget_basis", field="max_total_cents", why="", answer_kind="radio"),
        domain="hotel",
        source_text="Find a hotel in Tbilisi around roughly €140 a night.",
        criteria=[{
            "key": "nightly_budget",
            "field": None,
            "text": "roughly €140 a night",
            "source_quote": "roughly €140 a night",
            "kind": "ambiguity",
            "status": "needs_clarification",
        }],
        draft={"fields": {"city": "Tbilisi"}},
    )

    assert diagnostic["codes"] == [
        "question_missing_why",
        "question_invalid_answer_kind",
        "question_criterion_key_unbound",
    ]
    assert diagnostic["criterion_key"] == "nightly_budget_basis"
    assert diagnostic["field"] == "max_total_cents"
    assert diagnostic["valid_criterion_keys"] == ["nightly_budget"]
    assert diagnostic["required_missing_fields"] == ["max_total_cents", "checkin_date", "checkout_date"]
    assert "What all-in total" not in repr(diagnostic)
    assert "roughly €140" not in repr(diagnostic)


def test_feedback_reports_mixed_route_scope_without_copying_question_prose():
    from app.adaptive_intent import planner_question_validation_feedback

    diagnostic = planner_question_validation_feedback(
        {
            "criterion_key": "origin_airports",
            "field": "origin_airports",
            "text": "Which departure airport and arrival airport work?",
            "why": "The route matters.",
            "answer_kind": "multi",
        },
        domain="flight",
        source_text="Find a flight from London to Toronto.",
        criteria=[],
        draft={"fields": {}},
    )

    assert diagnostic["codes"] == ["question_mixed_route_scope"]
    assert diagnostic["field"] == "origin_airports"
    assert "Which departure airport" not in repr(diagnostic)


def test_valid_source_backed_optional_question_has_no_rejection_feedback():
    from app.adaptive_intent import planner_question_validation_feedback

    diagnostic = planner_question_validation_feedback(
        _question("breakfast", field="breakfast", why="The answer is useful."),
        domain="hotel",
        source_text="Find a hotel in Tbilisi with breakfast.",
        criteria=[{
            "key": "breakfast",
            "field": "breakfast",
            "text": "breakfast",
            "source_quote": "breakfast",
            "kind": "preference",
            "status": "needs_clarification",
        }],
        draft={"fields": {}},
    )

    assert diagnostic is None


def test_valid_required_profile_gap_without_explicit_field_has_no_feedback():
    from app.adaptive_intent import planner_question_validation_feedback

    diagnostic = planner_question_validation_feedback(
        _question("city", field=None),
        domain="hotel",
        source_text="Find a hotel.",
        criteria=[],
        draft={"fields": {}},
    )

    assert diagnostic is None


def test_declined_source_criterion_is_not_offered_as_a_repair_target():
    from app.adaptive_intent import planner_question_validation_feedback

    diagnostic = planner_question_validation_feedback(
        _question("breakfast", field="breakfast"),
        domain="hotel",
        source_text="I do not need breakfast.",
        criteria=[{
            "key": "breakfast",
            "field": "breakfast",
            "text": "breakfast",
            "source_quote": "breakfast",
            "kind": "preference",
            "status": "declined",
        }],
        draft={"fields": {}},
    )

    assert diagnostic["codes"] == ["question_declined_criterion"]
    assert diagnostic["valid_criterion_keys"] == []


def test_adaptive_prompt_keeps_customer_budget_and_date_wording_bounded():
    from app.ai_pipeline import prompt

    text = prompt("hotel", "adaptive", "adaptive_review")

    assert "never ask the traveler to express an amount in cents" in text
    assert "do not convert or guess an exchange rate" in text
    assert "demo's bounded profile accepts USD" in text
    assert "do not invent example dates" in text


def test_accepted_source_phrase_recovery_has_no_rejection_diagnostic(monkeypatch, mocked_pipeline):
    from app.ai_pipeline import run_pipeline

    source = (
        "I need a hotel in Tbilisi from April 3 to April 7, 2027, around roughly "
        "€140 a night."
    )
    recovered_question = {
        "criterion_key": "Nightly_Budget",
        "field": None,
        "text": "roughly €140 a night",
        "why": "The answer changes which hotel offers can satisfy the request.",
        "answer_kind": "text",
        "options": [],
    }
    candidate = _hotel_plan(question=recovered_question, criterion_key="Nightly_Budget")
    candidate["assistant_message"] = "What all-in USD amount should I use for the complete stay?"
    monkeypatch.setattr("app.ai_pipeline.reserve_ai_calls", lambda *args, **kwargs: 2)
    monkeypatch.setattr(
        "app.ai_pipeline.call_json",
        lambda stage, *args, **kwargs: (deepcopy(candidate), {"stage": stage}),
    )

    result = run_pipeline("hotel", source, "session", variant="adaptive")

    assert result["planner"]["action"] == "ask_user"
    assert result["planner"]["question"]["text"] == candidate["assistant_message"]
    assert "planner_validation" not in result["trace"][0]
    assert "planner_validation" not in result["trace"][1]


def test_invalid_planner_action_is_reported_without_fallback_question(monkeypatch, mocked_pipeline):
    from app.ai_pipeline import run_pipeline

    source = "Find a hotel in Tbilisi around €140 a night."
    invalid = _hotel_plan(question=None, action="approve_purchase")
    calls = []
    monkeypatch.setattr("app.ai_pipeline.reserve_ai_calls", lambda *args, **kwargs: 2)

    def fake_call(stage, *args, **kwargs):
        calls.append(kwargs.get("candidate_issue"))
        return deepcopy(invalid), {"stage": stage}

    monkeypatch.setattr("app.ai_pipeline.call_json", fake_call)
    result = run_pipeline("hotel", source, "session", variant="adaptive")

    assert "planner_action_invalid" in calls[1]
    assert result["trace"][0]["planner_validation"]["codes"] == [
        "planner_action_invalid"
    ]
    assert result["trace"][1]["planner_validation"]["codes"] == [
        "planner_action_invalid"
    ]
    assert result["planner"]["action"] == "review_required"
    assert result["planner"]["question"] is None
    assert "approved" not in result


def test_review_feedback_repairs_an_unbound_question_and_preserves_corrected_question(monkeypatch, mocked_pipeline):
    from app.ai_pipeline import run_pipeline

    source = (
        "I need a hotel in Tbilisi from April 3 to April 7, 2027, around roughly "
        "€140 a night."
    )
    candidate = _hotel_plan(question=_question("nightly_budget_basis", field="max_total_cents"))
    corrected = _hotel_plan(question=_question("nightly_budget", field=None))
    calls = []

    monkeypatch.setattr("app.ai_pipeline.reserve_ai_calls", lambda *args, **kwargs: 2)

    def fake_call(stage, *args, **kwargs):
        calls.append({"stage": stage, "candidate_issue": kwargs.get("candidate_issue")})
        response = candidate if stage == "adaptive_plan" else corrected
        return deepcopy(response), {"stage": stage, "response_id": stage}

    monkeypatch.setattr("app.ai_pipeline.call_json", fake_call)
    result = run_pipeline("hotel", source, "session", variant="adaptive")

    assert calls[1]["candidate_issue"] == (
        "planner_question_validation_failed;"
        "codes=question_criterion_key_unbound;"
        "criterion_key=nightly_budget_basis;field=max_total_cents;"
        "valid_criterion_keys=nightly_budget;"
        "required_missing_fields=max_total_cents;"
        "repair_question_with_bounded_targets"
    )
    assert result["planner"]["action"] == "ask_user"
    assert result["planner"]["question"]["criterion_key"] == "nightly_budget"
    assert result["trace"][0]["planner_validation"]["codes"] == [
        "question_criterion_key_unbound"
    ]
    assert "planner_validation" not in result["trace"][1]
    assert "approved" not in result
    assert "decision" not in result


def test_unrepairable_reviewer_question_stays_review_required_without_approval(monkeypatch, mocked_pipeline):
    from app.ai_pipeline import run_pipeline

    source = (
        "I need a hotel in Tbilisi from April 3 to April 7, 2027, around roughly "
        "€140 a night."
    )
    candidate = _hotel_plan(question=_question("nightly_budget_basis", field="max_total_cents"))
    rejected = _hotel_plan(question=_question("nightly_budget_basis", field="max_total_cents"))
    monkeypatch.setattr("app.ai_pipeline.reserve_ai_calls", lambda *args, **kwargs: 2)

    def fake_call(stage, *args, **kwargs):
        return deepcopy(candidate if stage == "adaptive_plan" else rejected), {
            "stage": stage,
            "response_id": stage,
        }

    monkeypatch.setattr("app.ai_pipeline.call_json", fake_call)
    result = run_pipeline("hotel", source, "session", variant="adaptive")

    assert result["planner"]["action"] == "review_required"
    assert result["planner"]["question"] is None
    assert result["trace"][0]["planner_validation"]["codes"] == [
        "question_criterion_key_unbound"
    ]
    assert result["trace"][1]["planner_validation"]["codes"] == [
        "question_criterion_key_unbound"
    ]
    assert "approved" not in result
    assert "decision" not in result
