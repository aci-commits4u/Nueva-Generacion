"""Regression coverage for bounded, multi-airport clarification state."""

from copy import deepcopy

from app.adaptive_intent import normalize_plan
import pytest

from app.conversation import (
    _question_airport_options_are_current,
    apply_adaptive_plan,
    merge_revision_state,
    question_contract_current,
    validate_structured_airport_answer,
)
from tests.test_enforcement import client
from app.store import get_store


def _draft():
    return {
        "domain": "flight",
        "mode": "live",
        "pipeline": "adaptive",
        "fields": {
            "max_total_cents": 29999,
            "destination_airports": ["YYZ"],
            "departure_date": "2026-11-12",
        },
        "sources": {
            "max_total_cents": "under $300",
            "destination_airports": "Toronto",
            "departure_date": "2026-11-12",
        },
        "clarifications": [],
        "unsupported": [],
        "messages": [
            {
                "role": "user",
                "content": "Book a nonstop flight from London to Toronto on 2026-11-12 under $300.",
            },
        ],
    }


def _question(text, *, question_id=None):
    question = {
        "criterion_key": "origin_airports",
        "field": "origin_airports",
        "text": text,
        "why": "The route cannot be searched until the departure airport choices are recorded.",
        "answer_kind": "multi",
        "answer_semantics": None,
        "options": [
            {"label": "London City · LCY", "value": "LCY"},
            {"label": "London Heathrow · LHR", "value": "LHR"},
        ],
    }
    if question_id:
        question["id"] = question_id
        question["question_id"] = question_id
    return question


def _extraction(question, *, fields, sources, status="needs_clarification"):
    return {
        "mode": "live",
        "pipeline": "adaptive",
        "model": "test",
        "fields": deepcopy(fields),
        "sources": deepcopy(sources),
        "clarifications": [],
        "unsupported": [],
        "explanation": "Review the captured route.",
        "adaptive_plan": {
            "action": "ask_user",
            "assistant_message": "I need one route detail before I review offers.",
            "question": question,
            "criteria": [{
                "key": "origin_airports",
                "field": "origin_airports",
                "text": "acceptable departure airports",
                "source_quote": "London",
                "kind": "ambiguity",
                "verification": "supported",
                "status": status,
            }],
            "offer_observations": [],
        },
        "agent_tools": [],
    }


def test_answered_multi_airport_set_survives_reviewer_rewording():
    """A valid origin set must not be narrowed to one airport by a later pass."""
    draft = _draft()
    first = apply_adaptive_plan(
        draft,
        _extraction(
            _question("Which London departure airports work for you?"),
            fields=draft["fields"],
            sources=draft["sources"],
        ),
    )
    answered = deepcopy(first)
    answered["messages"].append({
        "role": "user",
        "content": "Depart from LCY or LHR.",
        "reply_to": first["questions"][0],
    })
    answered["fields"]["origin_airports"] = ["LCY", "LHR"]
    answered["sources"]["origin_airports"] = "Depart from LCY or LHR."

    second = apply_adaptive_plan(
        answered,
        _extraction(
            _question("Which specific London airport would you like?", question_id="q_reworded"),
            fields=answered["fields"],
            sources=answered["sources"],
            status="needs_clarification",  # stale reviewer metadata
        ),
    )

    assert second["fields"]["origin_airports"] == ["LCY", "LHR"]
    assert second["sources"]["origin_airports"] == "Depart from LCY or LHR."
    assert second["questions"] == []


def test_airport_question_cannot_bind_one_field_to_a_combined_route_prompt():
    """A route question must not send destination choices into origin state."""
    source = "Book a nonstop flight from London to Toronto on 2026-11-12 under $300."
    raw = {
        "action": "ask_user",
        "assistant_message": "Which London airport would you like to depart from and which Toronto airport would you like to arrive at?",
        "question": {
            "criterion_key": "origin_airports",
            "field": "origin_airports",
            "text": "Which London airport would you like to depart from and which Toronto airport would you like to arrive at?",
            "why": "The route cannot be searched until the airport choices are recorded.",
            "answer_kind": "multi",
            "options": [
                {"label": "London City · LCY", "value": "LCY"},
                {"label": "Toronto Pearson · YYZ", "value": "YYZ"},
            ],
        },
        "criteria": [{
            "key": "origin_airports",
            "field": "origin_airports",
            "text": "acceptable departure airports",
            "source_quote": "London",
            "kind": "ambiguity",
            "status": "needs_clarification",
            "verification": "supported",
        }],
        "fields": {"max_total_cents": 29999, "departure_date": "2026-11-12"},
        "sources": {"max_total_cents": "under $300", "departure_date": "2026-11-12"},
        "unsupported": [],
        "clarifications": [],
        "explanation": "Review the route.",
        "offer_observations": [],
    }

    result = normalize_plan(raw, domain="flight", source_text=source)

    assert result["action"] == "review_required"
    assert result["question"] is None


def test_bound_airport_answer_cannot_be_narrowed_by_model_source_substring():
    """The full typed choice set wins over a reviewer quoting only one code."""
    current = _draft()
    question = _question("Which London departure airports work for you?")
    current["fields"]["origin_airports"] = ["LCY", "LHR"]
    current["sources"]["origin_airports"] = "Depart from LCY or LHR."
    current["messages"].append({
        "role": "user",
        "content": "Depart from LCY or LHR.",
        "reply_to": question,
    })

    merged = merge_revision_state(
        "flight",
        current,
        {
            "fields": {"origin_airports": ["LCY"]},
            "sources": {"origin_airports": "Depart from LCY"},
            "clarifications": [],
        },
        "Depart from LCY or LHR.",
        current["messages"],
    )

    assert merged["fields"]["origin_airports"] == ["LCY", "LHR"]
    assert merged["sources"]["origin_airports"] == "Depart from LCY or LHR."


def test_airport_question_options_are_server_scoped_and_multi_select():
    draft = _draft()
    result = apply_adaptive_plan(
        draft,
        _extraction(
            _question("Which route airports should I use?"),
            fields=draft["fields"],
            sources=draft["sources"],
        ),
    )
    question = result["questions"][0]
    codes = {option["value"] for option in question["options"]}
    assert {"LCY", "LHR", "LGW", "LTN", "STN", "LYX"} & codes
    assert not codes & {"YYZ", "YTZ"}
    assert question["allow_multiple"] is True
    assert all("·" in option["label"] for option in question["options"])


def test_structured_airport_answer_rejects_forged_binding_and_message():
    question = {
        "id": "q_airport",
        "question_id": "q_airport",
        "field": "origin_airports",
    }
    with pytest.raises(ValueError):
        validate_structured_airport_answer(
            question,
            {"question_id": "q_other", "field": "origin_airports", "values": ["LCY"]},
            "Depart from LCY.",
        )
    with pytest.raises(ValueError):
        validate_structured_airport_answer(
            question,
            {"question_id": "q_airport", "field": "origin_airports", "values": ["LCY", "LHR"]},
            "Depart from LCY.",
        )


def test_structured_airport_answer_is_bound_as_one_complete_choice():
    question = {
        "id": "q_airport",
        "question_id": "q_airport",
        "field": "origin_airports",
    }
    answer = validate_structured_airport_answer(
        question,
        {"question_id": "q_airport", "field": "origin_airports", "values": ["LCY", "LHR"]},
        "Depart from LCY or LHR.",
    )
    merged = merge_revision_state(
        "flight",
        _draft(),
        {"fields": {"origin_airports": ["LCY"]}, "sources": {"origin_airports": "Depart from LCY"}, "clarifications": []},
        answer["source_quote"],
        [{"role": "user", "content": answer["source_quote"], "reply_to": question}],
        structured_answer=answer,
    )
    assert merged["fields"]["origin_airports"] == ["LCY", "LHR"]
    assert merged["sources"]["origin_airports"] == answer["source_quote"]


def _api_proposal(*, origin=None, origin_source=None, action="ask_user"):
    fields = {
        "destination_airports": ["YYZ", "YTZ"],
        "departure_date": "2026-11-12",
        "max_total_cents": 29999,
        "nonstop": True,
    }
    sources = {
        "destination_airports": "Toronto",
        "departure_date": "2026-11-12",
        "max_total_cents": "under $300",
        "nonstop": "nonstop",
    }
    if origin is not None:
        fields["origin_airports"] = origin
        sources["origin_airports"] = origin_source or "London"
    return {
        "fields": fields,
        "sources": sources,
        "unsupported": [],
        "clarifications": [],
        "explanation": "Review the route.",
        "mode": "live",
        "model": "test",
        "pipeline": "adaptive",
        "trace": [],
        "adaptive_plan": {
            "action": action,
            "assistant_message": "Choose the departure airports you accept.",
            "question": None if action != "ask_user" else {
                "criterion_key": "origin_airports",
                "field": "origin_airports",
                "question": "Which London departure airports work for you?",
                "why": "The route cannot be searched until departure airports are recorded.",
                "answer_kind": "multi",
                "options": [{"label": "bad mixed option", "value": "YYZ"}],
            },
            "criteria": [{
                "key": "origin_airports",
                "field": "origin_airports",
                "text": "London departure airports",
                "source_quote": "London",
                "kind": "ambiguity",
                "verification": "supported",
                "status": "needs_clarification" if origin is None else "captured",
            }],
            "offer_observations": [],
        },
        "agent_tools": [],
    }


def test_api_forged_airport_selection_fails_before_provider_or_budget(client, monkeypatch):
    monkeypatch.setattr(
        "app.foundry_client.extract",
        lambda *args, **kwargs: _api_proposal(),
    )
    draft = client.post("/api/intents", json={
        "domain": "flight",
        "mode": "live",
        "message": "Book a nonstop flight from London to Toronto on 2026-11-12 under $300.",
    }).json()
    calls = []
    monkeypatch.setattr(
        "app.foundry_client.extract",
        lambda *args, **kwargs: calls.append(True) or pytest.fail("invalid typed answer must not call AI"),
    )
    question = draft["questions"][0]
    response = client.post(f"/api/intents/{draft['id']}/clarify", json={
        "revision": draft["revision"],
        "message": "Depart from LCY.",
        "structured_answer": {
            "question_id": "q_forged",
            "field": "origin_airports",
            "values": ["LCY"],
        },
    })
    assert response.status_code == 422
    assert calls == []
    assert client.get(f"/api/intents/{draft['id']}").json()["revision"] == draft["revision"]
    assert question["field"] == "origin_airports"


def test_api_typed_choice_survives_narrow_reviewer_response(client, monkeypatch):
    monkeypatch.setattr(
        "app.foundry_client.extract",
        lambda *args, **kwargs: _api_proposal(),
    )
    draft = client.post("/api/intents", json={
        "domain": "flight",
        "mode": "live",
        "message": "Book a nonstop flight from London to Toronto on 2026-11-12 under $300.",
    }).json()
    question = draft["questions"][0]
    monkeypatch.setattr(
        "app.foundry_client.extract",
        lambda *args, **kwargs: _api_proposal(
            origin=["LCY"], origin_source="Depart from LCY.", action="review_required"
        ),
    )
    response = client.post(f"/api/intents/{draft['id']}/clarify", json={
        "revision": draft["revision"],
        "message": "Depart from LCY or LHR.",
        "structured_answer": {
            "question_id": question["question_id"],
            "field": "origin_airports",
            "values": ["LCY", "LHR"],
        },
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["fields"]["origin_airports"] == ["LCY", "LHR"]
    assert result["sources"]["origin_airports"] == "Depart from LCY or LHR."
    assert result["structured_answers"][-1]["question"]["question_id"] == question["question_id"]
    assert result["messages"][-1]["structured_answer"]["values"] == ["LCY", "LHR"]
    reloaded = client.get(f"/api/intents/{draft['id']}").json()
    assert reloaded["messages"][-1]["structured_answer"]["question_id"] == question["question_id"]
    assert reloaded["fields"]["origin_airports"] == ["LCY", "LHR"]


def test_question_contract_detects_legacy_plan_split_without_mutating_draft():
    draft = _draft()
    draft.update({
        "mode": "live",
        "pipeline": "adaptive",
        "adaptive_plan": {
            "action": "ask_user",
            "question": {
                "id": "q_plan",
                "question_id": "q_plan",
                "field": "origin_airports",
                "criterion_key": "origin_airports",
                "question": "Which departure airport works?",
                "options": [],
            },
        },
        "questions": [{
            "id": "q_legacy",
            "question_id": "q_legacy",
            "field": "origin_airports",
            "criterion_key": "origin_airports",
            "question": "Which departure airport works?",
            "options": [],
        }],
    })
    before = deepcopy(draft)
    assert question_contract_current(draft) is False
    assert draft == before


def test_question_contract_rejects_adaptive_question_with_empty_authoritative_list():
    draft = _draft()
    draft.update({
        "mode": "live",
        "pipeline": "adaptive",
        "adaptive_plan": {"action": "ask_user", "question": {
            "id": "q_plan", "question_id": "q_plan", "field": "origin_airports",
            "criterion_key": "origin_airports", "question": "Which departure airport works?",
            "options": [],
        }},
        "questions": [],
    })
    assert question_contract_current(draft) is False


def test_stored_mixed_route_question_is_stale_even_with_clean_options():
    draft = _draft()
    question = {
        "field": "origin_airports",
        "question": "Which London airport should you depart from and which Toronto airport should you arrive at?",
        "options": [
            {"label": "London Heathrow · LHR", "value": "LHR"},
            {"label": "London City · LCY", "value": "LCY"},
        ],
    }
    assert _question_airport_options_are_current(question, draft) is False


def test_get_marks_malformed_live_contract_stale_without_provider_or_write(client, monkeypatch):
    monkeypatch.setattr("app.foundry_client.extract", lambda *args, **kwargs: _api_proposal())
    draft = client.post("/api/intents", json={
        "domain": "flight", "mode": "live",
        "message": "Book a nonstop flight from London to Toronto on 2026-11-12 under $300.",
    }).json()
    sid = client.cookies["ij_session"]
    get_store().mutate(sid, lambda state: state["drafts"][draft["id"]].update(
        adaptive_plan={"action": "ask_user", "question": "legacy malformed"},
    ))
    calls = []
    monkeypatch.setattr("app.foundry_client.extract", lambda *args, **kwargs: calls.append(True))
    response = client.get(f"/api/intents/{draft['id']}")
    assert response.status_code == 200
    assert response.json()["clarification_current"] is False
    assert response.json()["refresh_required"] is True
    assert calls == []
    stored = get_store().read(sid)["drafts"][draft["id"]]
    assert stored["adaptive_plan"]["question"] == "legacy malformed"


def test_refresh_stale_clarification_revokes_old_approval_and_binds_new_question(client, monkeypatch):
    monkeypatch.setattr("app.foundry_client.extract", lambda *args, **kwargs: _api_proposal())
    draft = client.post("/api/intents", json={
        "domain": "flight", "mode": "live",
        "message": "Book a nonstop flight from London to Toronto on 2026-11-12 under $300.",
    }).json()
    sid = client.cookies["ij_session"]
    get_store().mutate(sid, lambda state: state["drafts"][draft["id"]].update(
        adaptive_plan={"action": "ask_user", "question": "legacy malformed"},
        approved={"id": draft["id"], "revision": 1},
        offer_views=[{"id": "old-offer"}],
    ))
    response = client.post(f"/api/intents/{draft['id']}/refresh-profile", json={
        "revision": draft["revision"], "time_zone": "UTC",
    })
    assert response.status_code == 200, response.text
    refreshed = response.json()
    assert not refreshed.get("approved")
    assert not refreshed.get("offer_views")
    assert refreshed["clarification_current"] is True
    assert refreshed["adaptive_plan"]["question"]["field"] == "origin_airports"
    assert refreshed["questions"][0]["question_id"] == refreshed["adaptive_plan"]["question"]["question_id"]
    events = get_store().read(sid)["events"]
    assert any(event["kind"] == "authorization_revoked_by_reinterpretation" for event in events)


def test_refresh_stale_contract_keeps_completed_receipt_immutable_and_skips_provider(client, monkeypatch):
    from tests.test_enforcement import decision, prepare

    draft, offers = prepare(client)
    checked = decision(client, draft, offers[0])
    receipt = client.post("/api/purchase", json={
        "decision_id": checked["id"], "idempotency_key": "legacy-contract-receipt",
    }).json()
    sid = client.cookies["ij_session"]
    before = deepcopy(get_store().read(sid)["drafts"][draft["id"]])
    get_store().mutate(sid, lambda state: state["drafts"][draft["id"]].update(
        mode="live", pipeline="adaptive",
        adaptive_plan={"action": "ask_user", "question": "legacy malformed"},
    ))
    before_stale = deepcopy(get_store().read(sid)["drafts"][draft["id"]])
    calls = []
    monkeypatch.setattr("app.foundry_client.extract", lambda *args, **kwargs: calls.append(True))
    response = client.post(f"/api/intents/{draft['id']}/refresh-profile", json={
        "revision": draft["revision"], "time_zone": "UTC",
    })
    assert response.status_code == 409
    assert calls == []
    assert get_store().read(sid)["drafts"][draft["id"]] == before_stale
    assert client.get(f"/api/purchases/{receipt['id']}/evidence").json()["purchase"]["id"] == receipt["id"]

