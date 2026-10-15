"""API boundary tests for read-only live shopping discovery.

These tests deliberately use an offline intent draft and a provider stub.  The
provider adapter has its own tests; this module verifies that the FastAPI layer
keeps external quotes outside the signed-offer and purchase state machine.
"""

from __future__ import annotations

import copy
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.shopping_provider import ShoppingProviderError
from app.store import get_budget_store, get_store


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("STORE_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "shopping-api.sqlite3"))
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    get_store.cache_clear()
    get_budget_store.cache_clear()
    with TestClient(app) as value:
        value.get("/api/session")
        yield value
    get_store.cache_clear()
    get_budget_store.cache_clear()


def _approved_intent(
    client: TestClient,
    *,
    origins: list[str] | None = None,
    destinations: list[str] | None = None,
):
    origins = origins or ["WAW"]
    destinations = destinations or ["BER"]
    created = client.post(
        "/api/intents",
        json={
            "domain": "flight",
            "message": "Nonstop flight EWR to MCO on 2027-02-10 under $300.",
            "mode": "offline",
        },
    )
    assert created.status_code == 200, created.text
    draft = created.json()

    fields = {field: None for field in client.get("/api/profiles/flight").json()["fields"]}
    fields.update(
        {
            "nonstop": True,
            "max_total_cents": 29_999,
            "origin_airports": origins,
            "destination_airports": destinations,
            "departure_date": "2027-02-10",
        }
    )
    reviewed = client.post(
        f"/api/intents/{draft['id']}/answers",
        json={
            "revision": draft["revision"],
            "fields": fields,
            "unsupported": [],
            "confirmation": True,
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    reviewed_draft = reviewed.json()
    approval = client.post(
        f"/api/intents/{draft['id']}/approve",
        json={
            "revision": reviewed_draft["revision"],
            "digest": reviewed_draft["digest"],
            "confirmation": True,
        },
    )
    assert approval.status_code == 200, approval.text
    return {
        "id": draft["id"],
        "revision": reviewed_draft["revision"],
        "digest": reviewed_draft["digest"],
        "approved": approval.json()["approved"],
    }


def _quote_result(*, option_id: str = "kiwi-external-1"):
    return {
        "record_type": "external_discovery_result",
        "status": "external_unverified",
        "provider": "kiwi",
        "retrieved_at": "2026-10-15T00:00:00Z",
        "currency": "USD",
        "query": {"query_count": 1},
        "query_summary": {"query_count": 1},
        "results": [
            {
                "record_type": "external_discovery",
                "id": option_id,
                "verification_status": "external_unverified",
                "verified": False,
                "price_cents": 12_100,
                "booking_url": "https://kiwi.com/u/example",
                # A provider must not be able to turn this field into a
                # checkout credential merely by returning one in its payload.
                "checkout_jwt": "unsigned-provider-data",
            }
        ],
        "not_verified": "External quote only.",
        "not_verified_notice": "External quote only.",
    }


def _shopping(client: TestClient, intent: dict, **overrides):
    payload = {"revision": intent["revision"], "adults": 1}
    payload.update(overrides)
    return client.post(f"/api/intents/{intent['id']}/shopping", json=payload)


def test_shopping_requires_session(client):
    intent = _approved_intent(client)
    client.cookies.clear()

    response = _shopping(client, intent)

    assert response.status_code == 401
    assert response.json()["detail"] == "Start a demo session first."


def test_shopping_is_owned_by_session_and_requires_current_approval(client, monkeypatch):
    intent = client.post(
        "/api/intents",
        json={
            "domain": "flight",
            "message": "Book a flight from Warsaw to Berlin.",
            "mode": "offline",
        },
    ).json()
    monkeypatch.setattr("app.shopping_provider.search_flights", lambda *args, **kwargs: _quote_result())

    # A draft that has not been reviewed and approved cannot reach the provider.
    response = _shopping(client, intent)
    assert response.status_code == 409
    assert "Approve the current reviewed requirements" in response.json()["detail"]

    approved = _approved_intent(client)
    stale = _shopping(client, approved, revision=approved["revision"] - 1)
    assert stale.status_code == 409
    assert "Approve the current reviewed requirements" in stale.json()["detail"]

    # The record belongs to the original cookie-bound session.
    other = TestClient(app)
    try:
        other.get("/api/session")
        foreign = _shopping(other, approved)
        assert foreign.status_code == 404
        assert foreign.json()["detail"] == "This record is not in your demo session."
    finally:
        other.close()


def test_shopping_provider_receives_exact_approved_requirements_and_scope(client, monkeypatch):
    intent = _approved_intent(client, origins=["WAW", "KRK"], destinations=["BER", "MUC"])
    captures = []

    def fake_search(approved, **kwargs):
        captures.append((copy.deepcopy(approved), copy.deepcopy(kwargs)))
        return _quote_result()

    monkeypatch.setattr("app.shopping_provider.search_flights", fake_search)
    response = _shopping(
        client,
        intent,
        adults=3,
        origin_airports=["KRK"],
        destination_airports=["BER", "MUC"],
    )

    assert response.status_code == 200, response.text
    assert response.json()["intent_id"] == intent["id"]
    assert response.json()["revision"] == intent["revision"]
    assert response.json()["approved_digest"]
    assert captures == [
        (
            intent["approved"],
            {
                "adults": 3,
                "origin_airports": ["KRK"],
                "destination_airports": ["BER", "MUC"],
            },
        )
    ]


def test_nonflight_domain_returns_explicit_unsupported_error(client):
    created = client.post(
        "/api/intents",
        json={
            "domain": "hotel",
            "message": "Hotel under $200.",
            "mode": "offline",
        },
    )
    assert created.status_code == 200, created.text
    draft = created.json()

    fields = {field: None for field in client.get("/api/profiles/hotel").json()["fields"]}
    fields.update(
        {
            "max_total_cents": 20_000,
            "city": "Berlin",
            "checkin_date": "2027-02-10",
            "checkout_date": "2027-02-11",
        }
    )
    reviewed = client.post(
        f"/api/intents/{draft['id']}/answers",
        json={
            "revision": draft["revision"],
            "fields": fields,
            "unsupported": [],
            "removed_unsupported": draft.get("unsupported", []),
            "confirmation": True,
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    reviewed_draft = reviewed.json()
    approval = client.post(
        f"/api/intents/{draft['id']}/approve",
        json={
            "revision": reviewed_draft["revision"],
            "digest": reviewed_draft["digest"],
            "confirmation": True,
        },
    )
    assert approval.status_code == 200, approval.text

    response = _shopping(
        client,
        {
            "id": draft["id"],
            "revision": reviewed_draft["revision"],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Live shopping currently supports flights. Hotel and general checks remain signed synthetic demonstrations."
    )


def test_provider_error_status_and_message_are_stable_and_pending_is_released(client, monkeypatch):
    intent = _approved_intent(client)
    calls = []

    def failing_search(*args, **kwargs):
        calls.append("failed")
        raise ShoppingProviderError("invalid_scope", "The requested airport scope is outside the approved set.")

    monkeypatch.setattr("app.shopping_provider.search_flights", failing_search)
    failed = _shopping(client, intent, origin_airports=["LHR"])
    assert failed.status_code == 422
    assert failed.json() == {
        "detail": "The requested airport scope is outside the approved set.",
        "error": {
            "code": "invalid_scope",
            "message": "The requested airport scope is outside the approved set.",
        },
    }
    assert calls == ["failed"]

    # The failed request must not leave a lease that blocks a later search.
    monkeypatch.setattr("app.shopping_provider.search_flights", lambda *args, **kwargs: _quote_result())
    recovered = _shopping(client, intent)
    assert recovered.status_code == 200, recovered.text


def test_external_results_never_become_signed_offers_or_purchasable_decisions(client, monkeypatch):
    intent = _approved_intent(client)
    option_id = "kiwi-external-123456"
    monkeypatch.setattr(
        "app.shopping_provider.search_flights",
        lambda *args, **kwargs: _quote_result(option_id=option_id),
    )

    response = _shopping(client, intent)
    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["verification_status"] == "external_unverified"

    state = get_store().read(client.cookies.get("ij_session"))
    assert option_id not in state.get("offers", {})
    assert state.get("decisions", {}) == {}

    # The external identifier is not an offer id or decision id in either
    # state machine, even though the provider payload contained fake JWT text.
    checked = client.post("/api/check", json={"intent_id": intent["id"], "offer_id": option_id})
    assert checked.status_code == 404
    purchased = client.post(
        "/api/purchase",
        json={"decision_id": option_id, "idempotency_key": "external-option-1"},
    )
    assert purchased.status_code == 404


def test_revision_change_during_provider_call_is_rejected_and_lease_released(client, monkeypatch):
    intent = _approved_intent(client)
    sid = client.cookies.get("ij_session")

    def search_then_change_revision(*args, **kwargs):
        def change(state):
            state["drafts"][intent["id"]]["revision"] += 1

        get_store().mutate(sid, change)
        return _quote_result()

    monkeypatch.setattr("app.shopping_provider.search_flights", search_then_change_revision)
    changed = _shopping(client, intent)
    assert changed.status_code == 409
    assert "requirements changed during this search" in changed.json()["detail"]

    state = get_store().read(sid)
    assert "_shopping_pending" not in state


def test_pending_and_rate_limits_are_enforced_before_provider_call(client, monkeypatch):
    intent = _approved_intent(client)
    sid = client.cookies.get("ij_session")
    calls = []

    def should_not_run(*args, **kwargs):
        calls.append(True)
        return _quote_result()

    monkeypatch.setattr("app.shopping_provider.search_flights", should_not_run)
    get_store().mutate(
        sid,
        lambda state: state.update({"_shopping_pending": {"token": "other", "started_at": time.time()}}),
    )
    pending = _shopping(client, intent)
    assert pending.status_code == 409
    assert "already running" in pending.json()["detail"]
    assert calls == []

    get_store().mutate(
        sid,
        lambda state: state.update(
            {
                "_shopping_pending": {},
                "_shopping_requests": [time.time() for _ in range(8)],
            }
        ),
    )
    limited = _shopping(client, intent)
    assert limited.status_code == 429
    assert "eight live searches" in limited.json()["detail"]
    assert calls == []


def test_environment_is_exposed_in_health_and_session(client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")

    health = client.get("/api/health")
    session = client.get("/api/session")

    assert health.status_code == 200
    assert health.json()["environment"] == "development"
    assert health.json()["shopping_provider"] == "kiwi"
    assert session.status_code == 200
    assert session.json()["environment"] == "development"
