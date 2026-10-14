"""Provider-free checks for latest-turn coverage in the adaptive pipeline."""

from copy import deepcopy
import json
from types import SimpleNamespace

import pytest


@pytest.fixture
def mocked_pipeline(monkeypatch):
    """Use mocked provider calls without enabling the offline-only guard."""
    monkeypatch.setenv("MOCK_LLM", "0")


def _envelope(*, fields=None, sources=None, clarifications=None, unsupported=None):
    return {
        "fields": fields or {},
        "sources": sources or {},
        "unsupported": unsupported or [],
        "clarifications": clarifications or [],
        "explanation": "Review the captured requirements.",
    }


def _date_draft(*, criteria, question=None, action="ask_user", clarifications=None):
    return {
        "action": action,
        "assistant_message": "I need one useful detail before continuing.",
        "question": question,
        "criteria": criteria,
        "offer_observations": [],
        **_envelope(
            fields={
                "city": "Tbilisi",
                "checkin_date": "2027-04-03",
                "checkout_date": "2027-04-07",
            },
            sources={
                "city": "Tbilisi",
                "checkin_date": "check in on April 3, 2027",
                "checkout_date": "check out April 7, 2027",
            },
            clarifications=clarifications,
        ),
    }


def _criterion(key, quote, *, field=None, kind="requirement", verification="unsupported"):
    return {
        "key": key,
        "field": field,
        "text": quote,
        "source_quote": quote,
        "kind": kind,
        "status": "needs_clarification",
        "verification": verification,
    }


def test_provider_payload_promotes_only_verified_latest_customer_turn(monkeypatch):
    from app.ai_pipeline import call_json

    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://synthetic.example")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "synthetic-key")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "synthetic-model")
    captured = {}
    response = SimpleNamespace(
        usage=None,
        choices=[SimpleNamespace(
            finish_reason="stop",
            message=SimpleNamespace(content=json.dumps({
                "fields": {}, "sources": {}, "unsupported": [],
                "clarifications": [], "explanation": "Review.",
            })),
        )],
        id="synthetic-response",
    )

    def create(**kwargs):
        captured.update(kwargs)
        return response

    monkeypatch.setattr(
        "app.ai_pipeline.OpenAI",
        lambda **kwargs: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
        ),
    )
    source_messages = [
        {"role": "user", "content": "Find a hotel in Tbilisi."},
        {
            "role": "user",
            "content": "Use April 3 to April 7 and keep a separate $175 nightly cap.",
            "timestamp": "2026-10-14T12:00:00Z",
            "reference_date": "2026-10-14",
        },
    ]
    current_draft = {
        "fields": {"city": "Tbilisi"},
        "latest_customer_turn": {
            "content": source_messages[-1]["content"],
            "timestamp": "state-timestamp-is-not-authoritative",
        },
    }

    call_json(
        "adaptive_review", "hotel", "conversation context", "adaptive",
        source_text="\n".join(item["content"] for item in source_messages),
        source_messages=source_messages,
        current_draft=current_draft,
    )

    payload = json.loads(captured["messages"][1]["content"])
    assert payload["latest_customer_turn"] == {
        "content": source_messages[-1]["content"],
        "timestamp": source_messages[-1]["timestamp"],
        "reference_date": source_messages[-1]["reference_date"],
    }
    assert "latest_customer_turn" not in payload["current_draft"]

    current_draft["latest_customer_turn"]["content"] = "untrusted state text"
    captured.clear()
    call_json(
        "adaptive_review", "hotel", "conversation context", "adaptive",
        source_text="\n".join(item["content"] for item in source_messages),
        source_messages=source_messages,
        current_draft=current_draft,
    )
    payload = json.loads(captured["messages"][1]["content"])
    assert "latest_customer_turn" not in payload


def test_adaptive_prompt_requires_fresh_latest_turn_multi_clause_audit():
    from app.ai_pipeline import prompt

    text = prompt("hotel", "adaptive", "adaptive_review")

    assert "verified latest_customer_turn" in text
    assert "one turn may answer the pending question" in text
    assert "Emit every new material clause" in text
    assert "Preserve full unit and currency wording" in text
    assert "keep an optional date extension separate" in text
    assert "fresh,\ncomplete condition audit" in text
    assert "candidate omission is" in text


def test_reviewer_added_latest_turn_generic_clauses_survive_grounded_merge(
    monkeypatch, mocked_pipeline,
):
    from app.ai_pipeline import run_pipeline

    initial = "I need a quiet hotel in Tbilisi around €140 a night."
    latest = (
        "Please set check in on April 3, 2027 and check out April 7, 2027. "
        "Keep a separate $175 USD all-in nightly cap including taxes and fees "
        "for enforcement, with the option to extend to April 8 for five nights."
    )
    source_text = f"{initial}\n{latest}"
    source_messages = [
        {"role": "user", "content": initial},
        {"role": "user", "content": latest},
    ]
    current_draft = {
        "fields": {"city": "Tbilisi"},
        "latest_customer_turn": {"content": latest},
    }
    old_quote = "around €140 a night"
    cap_quote = "$175 USD all-in nightly cap including taxes and fees"
    extension_quote = "option to extend to April 8 for five nights"
    max_total = {
        "field": "max_total_cents",
        "source_quote": old_quote,
        "reason": "ambiguity",
    }
    candidate = _date_draft(
        criteria=[
            _criterion("city", "Tbilisi", field="city", verification="supported"),
            _criterion("max_total_cents", old_quote, field="max_total_cents",
                       kind="ambiguity", verification="supported"),
        ],
        question={
            "criterion_key": "max_total_cents",
            "field": "max_total_cents",
            "text": "What total all-in USD amount should I use for the stay?",
            "why": "The total changes which offers can satisfy the request.",
            "answer_kind": "number",
            "options": [],
        },
        clarifications=[max_total],
    )
    reviewed = deepcopy(candidate)
    reviewed["criteria"].extend([
        _criterion("nightly_budget_cap", cap_quote),
        _criterion("optional_stay_extension", extension_quote),
    ])
    reviewed["assistant_message"] = "What total all-in USD amount should I use for the stay?"

    monkeypatch.setattr("app.ai_pipeline.reserve_ai_calls", lambda *args, **kwargs: 2)
    calls = []

    def fake_call(stage, *args, **kwargs):
        calls.append(stage)
        return deepcopy(candidate if stage == "adaptive_plan" else reviewed), {"stage": stage}

    monkeypatch.setattr("app.ai_pipeline.call_json", fake_call)

    result = run_pipeline(
        "hotel", source_text, "coverage-session", variant="adaptive",
        source_text=source_text, source_messages=source_messages,
        current_draft=current_draft,
    )

    assert calls == ["adaptive_plan", "adaptive_review"]
    assert cap_quote in result["unsupported"]
    assert extension_quote in result["unsupported"]
    result_criteria = {
        item["source_quote"]
        for item in result["criteria"]
        if isinstance(item, dict) and item.get("source_quote")
    }
    assert cap_quote in result_criteria
    assert extension_quote in result_criteria
    assert result["fields"]["checkin_date"] == "2027-04-03"
    assert result["fields"]["checkout_date"] == "2027-04-07"
