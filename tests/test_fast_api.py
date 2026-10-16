"""Focused API checks for the faster adaptive pipeline and saved-draft repair.

These tests use a synthetic provider response at the API boundary. They do not
claim live Foundry or browser UAT coverage; the real provider tests live in the
pipeline/evaluation suites and the hosted walkthrough remains a separate check.
"""

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.ai_errors import AIServiceError
from app.ai_grounding import validate_extraction
from app.ai_config import PROMPT_VERSION
from app.intent_service import refresh
from app.main import app
from app.store import get_store


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("STORE_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "state.sqlite3"))
    monkeypatch.setenv("AI_BUDGET_SQLITE_PATH", "")
    monkeypatch.setenv("AI_CALL_LIMIT", "1500")
    monkeypatch.setenv("AI_DAILY_LIMIT", "2000")
    monkeypatch.setenv("AI_SESSION_LIMIT", "64")
    monkeypatch.setenv("AI_RESERVATION_USD", "0.02")
    monkeypatch.setenv("AI_EMERGENCY_BUDGET_CENTS", "1000")
    monkeypatch.setenv("AI_PIPELINE_VERSION", "adaptive_fast")
    monkeypatch.setenv("AI_REASONING_EFFORT", "low")
    monkeypatch.setenv("MOCK_LLM", "0")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://synthetic.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "synthetic-key")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "synthetic-foundry")
    get_store.cache_clear()
    with TestClient(app) as test_client:
        test_client.get("/api/session")
        yield test_client
    get_store.cache_clear()


def _seed_old_v15_draft(client):
    """Create a literal synthetic saved draft that predates the v16 contract."""
    message = (
        "Book a nonstop flight from EWR to MCO on 2026-11-12 under $300, "
        "no layovers, round trip, and checked baggage."
    )
    created = client.post(
        "/api/intents",
        json={"domain": "flight", "message": message, "mode": "offline"},
    ).json()
    sid = client.cookies["ij_session"]
    old_fields = {
        "origin_airports": ["EWR"],
        "destination_airports": ["MCO"],
        "departure_date": "2026-11-12",
        "max_total_cents": 29999,
        "nonstop": True,
    }
    old_sources = {
        "origin_airports": "from EWR",
        "destination_airports": "to MCO",
        "departure_date": "2026-11-12",
        "max_total_cents": "under $300",
        "nonstop": "nonstop",
    }
    old_question = {
        "id": "old-v15-max-connections",
        "question_id": "old-v15-max-connections",
        "field": "max_connections",
        "question": "How many connections can you accept?",
        "required": False,
        "response_type": "single",
        "allow_multiple": False,
        "options": [],
    }

    def install(state):
        draft = state["drafts"][created["id"]]
        draft.update(
            mode="live",
            model="synthetic-foundry",
            pipeline="adaptive_fast",
            fields=old_fields,
            sources=old_sources,
            unsupported=["round trip", "checked baggage"],
            clarifications=[],
            questions=[old_question],
            adaptive_plan={
                "action": "ask_user",
                "assistant_message": "The saved v15 question needs an explicit refresh.",
                "question": old_question,
                "offer_observations": [],
            },
            ai_runs=[
                {
                    "revision": created["revision"],
                    "mode": "live",
                    "pipeline": "adaptive_fast",
                    "model": "synthetic-foundry",
                    "trace": [
                        {"stage": "adaptive_plan", "prompt_version": "intent-envelope-v15-explicit-optionals"}
                    ],
                    "fields": deepcopy(old_fields),
                    "sources": deepcopy(old_sources),
                    "unsupported": ["round trip", "checked baggage"],
                    "clarifications": [],
                    "guidance": "Old v15 synthetic trace.",
                }
            ],
        )
        refresh(draft)

    get_store().mutate(sid, install)
    return client.get(f"/api/intents/{created['id']}").json()


def _validated_refresh_proposal(source_text, source_messages):
    proposal = {
        "fields": {
            "origin_airports": ["EWR"],
            "destination_airports": ["MCO"],
            "departure_date": "2026-11-12",
            "max_total_cents": 29999,
            "max_connections": 0,
        },
        "sources": {
            "origin_airports": "from EWR",
            "destination_airports": "to MCO",
            "departure_date": "2026-11-12",
            "max_total_cents": "under $300",
            "max_connections": "no layovers",
        },
        "unsupported": ["round trip", "checked baggage"],
        "clarifications": [],
        "explanation": "Review the retained route, date, price, and connection limit.",
    }
    # Keep the fixture honest: the fake provider output is checked through the
    # same deterministic grounding validator before it crosses the API boundary.
    validated = validate_extraction(
        "flight", source_text, proposal, source_messages=source_messages
    )
    return {
        **validated,
        "mode": "live",
        "model": "synthetic-foundry",
        "pipeline": "adaptive_fast",
        "trace": [{"stage": "adaptive_plan", "prompt_version": PROMPT_VERSION}],
        "adaptive_plan": {
            "action": "review_required",
            "assistant_message": "I refreshed the saved intent for review.",
            "question": None,
            "criteria": [],
            "offer_observations": [],
        },
    }


def test_fast_status_counts_one_call_and_reads_without_reserving(client):
    sid = client.cookies["ij_session"]
    get_store().mutate(sid, lambda state: state.update(ai_calls=8))
    before = get_store().read("global-ai-budget")

    response = client.get("/api/ai/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["pipeline"] == "adaptive_fast"
    assert payload["available"] is True
    assert payload["interpretation_calls"] == 1
    assert payload["interpretation_calls_max"] == 2
    assert payload["session_remaining_calls"] == 56
    assert get_store().read("global-ai-budget") == before


def test_old_v15_draft_exposes_refresh_required_state(client):
    saved = _seed_old_v15_draft(client)

    assert saved["profile_current"] is True
    assert saved["clarification_current"] is False
    assert saved["refresh_required"] is True
    assert saved["ai_runs"][-1]["trace"][0]["prompt_version"] == "intent-envelope-v15-explicit-optionals"


def test_refresh_profile_retains_route_date_money_and_old_unsupported_clauses(
    client, monkeypatch
):
    saved = _seed_old_v15_draft(client)
    sid = client.cookies["ij_session"]
    source_messages = deepcopy(saved["messages"])
    source_text = "\n".join(message["content"] for message in source_messages)
    proposal = _validated_refresh_proposal(source_text, source_messages)

    def fake_extract(domain, conversation, session, **kwargs):
        assert domain == "flight"
        assert session == sid
        return deepcopy(proposal)

    monkeypatch.setattr("app.foundry_client.extract", fake_extract)
    response = client.post(
        f"/api/intents/{saved['id']}/refresh-profile",
        json={"revision": saved["revision"], "time_zone": "UTC"},
    )

    assert response.status_code == 200, response.text
    refreshed = response.json()
    assert refreshed["revision"] == saved["revision"] + 1
    assert refreshed.get("approved") is None
    assert refreshed["reviewed"] is False
    assert refreshed["fields"]["origin_airports"] == ["EWR"]
    assert refreshed["fields"]["destination_airports"] == ["MCO"]
    assert refreshed["fields"]["departure_date"] == "2026-11-12"
    assert refreshed["fields"]["max_total_cents"] == 29999
    assert refreshed["fields"]["max_connections"] == 0
    assert refreshed["unsupported"] == ["round trip", "checked baggage"]
    assert refreshed["profile_current"] is True
    assert refreshed["clarification_current"] is True
    assert refreshed["ai_runs"][-1]["trace"][0]["prompt_version"] == PROMPT_VERSION


def test_failed_live_reply_preserves_saved_draft(client, monkeypatch):
    saved = _seed_old_v15_draft(client)
    sid = client.cookies["ij_session"]
    # Make this a current v16 draft so the failure reaches the provider path.
    def make_current(state):
        draft = state["drafts"][saved["id"]]
        draft["ai_runs"][-1]["trace"][0]["prompt_version"] = PROMPT_VERSION
        draft["adaptive_plan"]["action"] = "review_required"
        draft["adaptive_plan"]["question"] = None
        draft["questions"] = []
        refresh(draft)

    get_store().mutate(sid, make_current)
    before = client.get(f"/api/intents/{saved['id']}").json()

    def failed_extract(*args, **kwargs):
        raise AIServiceError(
            "ai_provider", "Synthetic provider failure for API preservation test.", status_code=503
        )

    monkeypatch.setattr("app.foundry_client.extract", failed_extract)
    response = client.post(
        f"/api/intents/{saved['id']}/clarify",
        json={"revision": before["revision"], "message": "Keep the same route."},
    )

    assert response.status_code == 503
    after = client.get(f"/api/intents/{saved['id']}").json()
    for key in ("revision", "fields", "sources", "unsupported", "messages", "digest"):
        assert after[key] == before[key]


def test_deferred_review_persists_warning_and_still_requires_explicit_review(
    client, monkeypatch
):
    """A deferred optional review stays visible through the signed evidence path."""
    saved = _seed_old_v15_draft(client)
    sid = client.cookies["ij_session"]

    def make_current(state):
        draft = state["drafts"][saved["id"]]
        draft["ai_runs"][-1]["trace"][0]["prompt_version"] = PROMPT_VERSION
        draft["adaptive_plan"] = {
            "action": "review_required",
            "assistant_message": "Review the captured requirements.",
            "question": None,
            "offer_observations": [],
        }
        draft["questions"] = []
        refresh(draft)

    get_store().mutate(sid, make_current)
    before = client.get(f"/api/intents/{saved['id']}").json()

    warning = {
        "code": "ai_session_limit",
        "kind": "adaptive_review_capacity_unavailable",
        "stage": "adaptive_review",
        "message": "The optional independent review could not run.",
        "candidate_preserved": True,
        "review_ran": False,
        "read_only_tool_observed": True,
    }

    def deferred_extract(domain, conversation, session, **kwargs):
        assert domain == "flight"
        assert session == sid
        return {
            "fields": deepcopy(before["fields"]),
            "sources": deepcopy(before["sources"]),
            "unsupported": deepcopy(before["unsupported"]),
            "clarifications": [],
            "explanation": "The grounded first pass is preserved for review.",
            "mode": "live",
            "model": "synthetic-foundry",
            "pipeline": "adaptive_fast",
            "trace": [
                {
                    "stage": "adaptive_fast",
                    "prompt_version": PROMPT_VERSION,
                    "review_ran": False,
                }
            ],
            "adaptive_plan": {
                "action": "review_required",
                "assistant_message": "Review the captured requirements.",
                "question": None,
                "offer_observations": [],
            },
            "review_deferred": True,
            "review_warning": warning,
            "read_only_tool_log": {
                "tool": "retrieve_policy",
                "status": "ok",
                "read_only": True,
            },
        }

    monkeypatch.setattr("app.foundry_client.extract", deferred_extract)
    clarified = client.post(
        f"/api/intents/{saved['id']}/clarify",
        json={
            "revision": before["revision"],
            "message": "Keep the captured requirements.",
        },
    )
    assert clarified.status_code == 200, clarified.text
    draft = clarified.json()
    assert draft["review_deferred"] is True
    assert draft["review_warning"] == warning
    assert draft["adaptive_plan"]["action"] == "review_required"
    assert draft["ai_runs"][-1]["review_deferred"] is True
    assert draft["ai_runs"][-1]["review_warning"] == warning

    # The deferred flag cannot satisfy the explicit review gate by itself.
    blocked = client.post(
        f"/api/intents/{saved['id']}/approve",
        json={
            "revision": draft["revision"],
            "digest": draft["digest"],
            "confirmation": True,
        },
    )
    assert blocked.status_code == 409
    assert "exact reviewed draft" in blocked.json()["detail"]

    profile = client.get("/api/profiles/flight").json()
    reviewed_fields = {key: None for key in profile["fields"]}
    reviewed_fields.update(draft["fields"])
    reviewed = client.post(
        f"/api/intents/{saved['id']}/answers",
        json={
            "revision": draft["revision"],
            "fields": reviewed_fields,
            "unsupported": [],
            "removed_unsupported": draft["unsupported"],
            "confirmation": True,
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    reviewed_draft = reviewed.json()
    assert reviewed_draft["reviewed"] is True
    assert reviewed_draft["review_deferred"] is True

    approved = client.post(
        f"/api/intents/{saved['id']}/approve",
        json={
            "revision": reviewed_draft["revision"],
            "digest": reviewed_draft["digest"],
            "confirmation": True,
        },
    )
    assert approved.status_code == 200, approved.text
    offer_id = approved.json()["offers"][0]["id"]
    checked = client.post(
        "/api/check",
        json={"intent_id": saved["id"], "offer_id": offer_id},
    )
    assert checked.status_code == 200, checked.text
    purchased = client.post(
        "/api/purchase",
        json={
            "decision_id": checked.json()["id"],
            "idempotency_key": "deferred-review-evidence-1",
        },
    )
    assert purchased.status_code == 200, purchased.text

    evidence = client.get(f"/api/purchases/{purchased.json()['id']}/evidence")
    assert evidence.status_code == 200, evidence.text
    latest_run = evidence.json()["interpretation_runs"][-1]
    assert latest_run["review_deferred"] is True
    assert latest_run["review_warning"] == warning

