"""Routing/enforcement wiring tests.

These use FAKE stand-ins for Victor's modules (rules_engine, evidence, foundry_client) injected only here,
so we can prove main.py calls them in the right order and enforces 409 on can_purchase's answer.
The fakes are NOT deciders for the product; real behaviour is covered by Victor's rules tests and,
after merge, test_enforcement.py / test_scenarios.py.
"""
import sys
import uuid
from datetime import datetime
from types import ModuleType

import pytest
from fastapi.testclient import TestClient

from app.fixtures_loader import base_requirements
from app.main import app
from app.models import CheckResult, Decision, EvidencePacket
from app.store import store


def _fake_rules() -> ModuleType:
    m = ModuleType("app.rules_engine")

    def evaluate(req, offer, vi_chain_valid, merchant_signature_valid):
        checks, result = [], "PASS"
        if not (vi_chain_valid and merchant_signature_valid):
            result = "BLOCK"
        elif len(offer.segments) > 1:
            result = "HOLD"
            checks = [CheckResult(check_id="STOPS", requirement="Nonstop", offer_value="3 connections",
                                  status="fail", message="You asked for nonstop. This itinerary has 3 connections.")]
        return Decision(decision_id=str(uuid.uuid4()), requirement_set_id=req.requirement_set_id,
                        offer_hash=offer.offer_hash, result=result, vi_chain_valid=vi_chain_valid,
                        merchant_signature_valid=merchant_signature_valid, checks=checks, created_at=datetime.now().astimezone())

    def can_purchase(decision, exceptions):
        if decision.result == "BLOCK":
            return False, "blocked", []
        if decision.result == "PASS":
            return True, "ok", []
        covered = {e.check_id for e in exceptions if e.offer_hash == decision.offer_hash and e.decision_id == decision.decision_id}
        need = [c.check_id for c in decision.checks if c.status in ("fail", "missing")]
        uncovered = [c for c in need if c not in covered]
        return (not uncovered), ("ok" if not uncovered else "unresolved checks"), uncovered

    m.evaluate, m.can_purchase = evaluate, can_purchase
    return m


def _fake_evidence() -> ModuleType:
    m = ModuleType("app.evidence")

    def build_packet(purchase, claim, decision, req, offer, exceptions, narrative=None):
        return EvidencePacket(purchase_id=purchase.purchase_id, dispute_claim=claim, vi_chain_valid=decision.vi_chain_valid,
                              merchant_signature_valid=decision.merchant_signature_valid, approved_requirements=req,
                              merchant_offer=offer, checks=decision.checks, exceptions=exceptions, suggested_reason_code="none",
                              recommended_responsibility="traveler", rationale="fake")

    m.build_packet = build_packet
    return m


def _fake_foundry(explain_text="This is approved!") -> ModuleType:
    m = ModuleType("app.foundry_client")
    m.explain = lambda decision, req: {"traveler_message": explain_text, "suggested_next_step": "none", "llm_fallback": False}
    m.evidence_narrative = lambda packet: "narrative"
    m.extract_requirements = lambda text, today: {"draft_requirements": {}, "questions": ["Which airports?"], "notes": "", "llm_fallback": False}
    return m


@pytest.fixture
def client(monkeypatch):
    store.reset()
    for name, mod in (("rules_engine", _fake_rules()), ("evidence", _fake_evidence()), ("foundry_client", _fake_foundry())):
        monkeypatch.setitem(sys.modules, f"app.{name}", mod)
    return TestClient(app)


def approve(client):
    draft = base_requirements().model_dump(mode="json")
    for k in ("requirement_set_id", "approved_by_traveler", "approved_at"):
        draft.pop(k)
    r = client.post("/api/intent/approve", json={"draft_requirements": draft, "source_text": draft["source_text"]})
    assert r.status_code == 200, r.text
    return r.json()["requirement_set_id"]


def check(client, rid, offer, **kw):
    r = client.post("/api/check", json={"requirement_set_id": rid, "offer_id": offer, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def test_scenarios_endpoint(client):
    data = client.get("/api/scenarios").json()
    assert len(data["scenarios"]) == 12 and {o["key"] for o in data["offers"]} == set("ABCDEFGH")


def test_approve_signs_requirements_and_rejects_incomplete(client):
    assert approve(client).startswith("req-")
    assert client.post("/api/intent/approve", json={"draft_requirements": {"origin_airports": ["JFK"]}}).status_code == 422


def test_extract_calls_foundry(client):
    assert client.post("/api/intent/extract", json={"text": "NYC to Florida"}).json()["questions"] == ["Which airports?"]


def test_pass_purchase_and_dispute(client):
    rid = approve(client)
    body = check(client, rid, "A")
    assert body["decision"]["result"] == "PASS"
    assert client.post("/api/purchase", json={"decision_id": body["decision"]["decision_id"]}).status_code == 201


def test_hold_is_409_until_specific_exception_then_201_and_dispute(client):
    rid = approve(client)
    body = check(client, rid, "B")
    did = body["decision"]["decision_id"]
    assert body["decision"]["result"] == "HOLD"
    # The explanation text says "approved" - it must carry no authority.
    assert body["decision"]["explanation"] == "This is approved!"
    r = client.post("/api/purchase", json={"decision_id": did})
    assert r.status_code == 409 and r.json()["uncovered_checks"] == ["STOPS"]

    ex = client.post("/api/exceptions", json={"decision_id": did, "check_ids": ["STOPS"], "traveler_statement": "I accept 3 connections"})
    assert ex.status_code == 200 and ex.json()["exceptions"][0]["offer_hash"] == body["decision"]["offer_hash"]
    p = client.post("/api/purchase", json={"decision_id": did})
    assert p.status_code == 201

    packet = client.post("/api/disputes", json={"purchase_id": p.json()["purchase_id"], "claim": "I didn't want layovers"})
    assert packet.status_code == 200 and packet.json()["final_decision"] == "dispute analyst"
    assert packet.json()["narrative"] == "narrative"


def test_exception_does_not_carry_to_a_new_check_of_the_same_offer(client):
    rid = approve(client)
    first = check(client, rid, "B")["decision"]["decision_id"]
    client.post("/api/exceptions", json={"decision_id": first, "check_ids": ["STOPS"], "traveler_statement": "ok"})
    second = check(client, rid, "B")["decision"]["decision_id"]
    assert client.post("/api/purchase", json={"decision_id": second}).status_code == 409


def test_exception_only_for_failed_checks(client):
    rid = approve(client)
    did = check(client, rid, "B")["decision"]["decision_id"]
    assert client.post("/api/exceptions", json={"decision_id": did, "check_ids": ["PRICE"], "traveler_statement": "x"}).status_code == 409


@pytest.mark.parametrize("tamper", ["l2", "checkout_sig"])
def test_tampering_blocks_and_cannot_be_excepted(client, tamper):
    rid = approve(client)
    body = check(client, rid, "B", tamper=tamper)
    did = body["decision"]["decision_id"]
    assert body["decision"]["result"] == "BLOCK"
    if tamper == "checkout_sig":  # forged merchant JWT: nothing is read from the unverified payload
        assert body["offer"]["segments"] == []
    assert body["decision"]["merchant_signature_valid"] is (tamper != "checkout_sig")
    assert client.post("/api/exceptions", json={"decision_id": did, "check_ids": ["STOPS"], "traveler_statement": "x"}).status_code == 409
    assert client.post("/api/purchase", json={"decision_id": did}).status_code == 409


def test_unknown_ids_404(client):
    assert client.post("/api/purchase", json={"decision_id": "nope"}).status_code == 404
    assert client.post("/api/check", json={"requirement_set_id": "nope", "offer_id": "A"}).status_code == 404
    assert client.post("/api/disputes", json={"purchase_id": "nope", "claim": "x"}).status_code == 404


def test_reset_clears_state(client):
    rid = approve(client)
    client.post("/api/reset")
    assert client.post("/api/check", json={"requirement_set_id": rid, "offer_id": "A"}).status_code == 404


def test_missing_rules_engine_is_501_not_a_decision(monkeypatch):
    store.reset()
    monkeypatch.setitem(sys.modules, "app.rules_engine", None)  # simulates "module not merged yet"
    c = TestClient(app)
    rid = approve(c)
    r = c.post("/api/check", json={"requirement_set_id": rid, "offer_id": "A"})
    assert r.status_code == 501 and "nothing was decided" in r.json()["detail"]
    assert store.decisions == {}


def test_foundry_failure_does_not_change_the_decision(client, monkeypatch):
    broken = _fake_foundry()
    broken.explain = lambda d, r: (_ for _ in ()).throw(RuntimeError("timeout"))
    monkeypatch.setitem(sys.modules, "app.foundry_client", broken)
    rid = approve(client)
    body = check(client, rid, "B")
    assert body["decision"]["result"] == "HOLD" and body["explanation"]["llm_fallback"] is True
