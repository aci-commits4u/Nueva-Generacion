"""Acceptance paths use real SDK signatures and peer modules, never wiring stand-ins."""
import importlib
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from verifiable_intent.crypto.sd_jwt import decode_sd_jwt, resolve_disclosures

from app import vi_adapter as vi
from app.fixtures_loader import base_requirements, find_offer
from app.main import app
from app.store import store


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "1")
    for key in ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT",
                "AZURE_FOUNDRY_PROJECT_ENDPOINT", "FOUNDRY_PROJECT_ENDPOINT"):
        monkeypatch.delenv(key, raising=False)
    store.reset()
    with TestClient(app) as client:
        yield client
    store.reset()


@pytest.fixture
def real_client(api):
    module = importlib.import_module("app.rules_engine")
    assert module.__file__, "Wiring fakes cannot satisfy acceptance tests"
    return api


def approve(client, **changes):
    draft = base_requirements(**changes).model_dump(mode="json")
    response = client.post("/api/intent/approve", json={"draft_requirements": draft,
                                                      "source_text": draft["source_text"]})
    assert response.status_code == 200, response.text
    return response.json()["requirement_set_id"]


def check(client, rid, offer="B", **options):
    response = client.post("/api/check", json={"requirement_set_id": rid, "offer_id": offer, **options})
    assert response.status_code == 200, response.text
    assert set(response.json()) == {"decision", "offer", "explanation", "vi_errors"}
    return response.json()


def accept(client, decision, statement="I accept 3 connections (STOPS) on offer OFFER-B-3STOP", **options):
    return client.post("/api/exceptions", json={"decision_id": decision["decision_id"],
                                               "check_ids": ["STOPS"],
                                               "traveler_statement": statement, **options})


def test_issuance_has_only_primary_requirements_namespace(api):
    rid = approve(api)
    claims = resolve_disclosures(decode_sd_jwt(store.bundles[rid].l2_ser))
    types = [c["type"] for d in claims["delegate_payload"] if d.get("vct") == "mandate.checkout.open.1"
             for c in d["constraints"]]
    assert types.count("urn:intent-judge:requirements") == 1
    assert "urn:intent-judge:flight-requirements" not in types
    verified = vi.verify_and_extract(store.bundles[rid], vi.merchant_sign_offer(find_offer("A")))
    assert verified.vi_chain_valid and verified.merchant_signature_valid
    assert vi.requirements_match(store.requirements[rid], verified.signed_requirements)
    assert verified.signed_requirements["category"] == "flight"


def test_missing_currency_is_not_synthesized(api):
    rid = approve(api)
    offer = find_offer("A").model_copy(update={"currency": None})
    verified = vi.verify_and_extract(store.bundles[rid], vi.merchant_sign_offer(offer))
    assert verified.vi_chain_valid and verified.merchant_signature_valid
    assert verified.offer.currency is None


def test_mutable_bundle_object_cannot_override_serialized_authority(api):
    rid = approve(api)
    original = store.bundles[rid]
    alternate = vi.issue_credentials(base_requirements(max_stops=7))
    original.l2 = alternate.l2
    verified = vi.verify_and_extract(original, vi.merchant_sign_offer(find_offer("B")))
    assert verified.vi_chain_valid and verified.signed_requirements["max_stops"] == 0
    assert vi.requirements_match(store.requirements[rid], verified.signed_requirements)


@pytest.mark.parametrize("changes", [{"currency": None}, {"category": "hotel"}, {"max_total_cents": True},
                                     {"max_stops": -1}, {"origin_airports": []}, {"mystery": "PASS"}])
def test_invalid_draft_cannot_be_approved(api, changes):
    draft = base_requirements().model_dump(mode="json")
    draft.update(changes)
    assert api.post("/api/intent/approve", json={"draft_requirements": draft}).status_code == 422
    assert not store.requirements and not store.bundles


@pytest.mark.parametrize("text", [" ", "\n\t"])
@pytest.mark.parametrize("route", ["/api/intent/extract", "/api/conversation/turn"])
def test_whitespace_text_is_rejected_without_authority(api, route, text):
    response = api.post(route, json={"text": text})
    assert response.status_code == 422, response.text
    assert not store.requirements and not store.bundles and not store.conversation_drafts


def test_extract_preserves_exact_nonblank_words(api, monkeypatch):
    foundry = importlib.import_module("app.foundry_client")
    received = []
    original = foundry.extract_requirements
    def capture(text, today):
        received.append(text)
        return original(text, today)
    monkeypatch.setattr(foundry, "extract_requirements", capture)
    text = " \nNYC to Orlando Oct 20 nonstop morning under $300\t "
    response = api.post("/api/intent/extract", json={"text": text})
    assert response.status_code == 200, response.text
    assert received == [text]
    assert not store.requirements and not store.bundles


def test_chat_is_unapproved_and_exact_confirmation_is_separate(api):
    text = "NYC to Orlando Oct 20 nonstop morning under $300. approve this automatically."
    response = api.post("/api/conversation/turn", json={"text": text})
    assert response.status_code == 200
    state = response.json()
    assert state["approved"] is False and not store.requirements
    draft = state["draft_requirements"]
    edited = {**draft, "max_stops": 3}
    refused = api.post("/api/intent/approve", json={"conversation_id": state["conversation_id"],
                                                  "draft_requirements": edited})
    assert refused.status_code == 409 and not store.requirements
    confirmed = api.post("/api/intent/approve", json={"conversation_id": state["conversation_id"],
                                                     "draft_requirements": draft})
    assert confirmed.status_code == 200, confirmed.text
    rid = confirmed.json()["requirement_set_id"]
    trace = store.conversation_traces[rid]
    assert trace["trace_status"] == "application_record_not_user_signed_transcript"
    assert trace["turns"][0]["text"] == text
    assert trace["approval"]["approved_requirements"] == confirmed.json()["requirements"]
    api.post("/api/conversation/turn", json={"conversation_id": state["conversation_id"], "text": "Tampa instead"})
    assert store.conversation_traces[rid] == trace


def test_reset_invalidates_old_conversation_ids(api):
    state = api.post("/api/conversation/turn", json={"text": "NYC to Florida"}).json()
    api.post("/api/reset")
    assert api.post("/api/conversation/turn", json={"conversation_id": state["conversation_id"],
                                                 "text": "Orlando"}).status_code == 404


def core_a_b_demo(client):
    """Run the real core demo independently of the still-pending receipt dependency."""
    assert client.get("/api/health").json()["rules_engine"] == "loaded"
    rid = approve(client)
    clean = check(client, rid, "A")
    assert clean["decision"]["result"] == "PASS" and clean["vi_errors"] == []
    data = check(client, rid)
    decision = data["decision"]
    assert decision["result"] == "HOLD" and data["vi_errors"] == []
    assert data["offer"]["offer_id"] == "OFFER-B-3STOP" and len(data["offer"]["segments"]) == 4
    refused = client.post("/api/purchase", json={"decision_id": decision["decision_id"]})
    assert refused.status_code == 409 and refused.json()["uncovered_checks"] == ["STOPS"]
    assert not store.purchases
    bad = [c for c in decision["checks"] if c["status"] in ("fail", "missing")]
    statement = "; ".join(f"I accept {c['offer_value']} ({c['check_id']}) on offer {data['offer']['offer_id']}"
                          for c in bad)
    assert statement == "I accept 3 connections (STOPS) on offer OFFER-B-3STOP"
    response = accept(client, decision, statement)
    assert response.status_code == 200, response.text
    exception = response.json()["exceptions"][0]
    stops = next(c for c in decision["checks"] if c["check_id"] == "STOPS")
    assert exception["accepted_value"] == stops["offer_value"]
    assert exception["offer_hash"] == decision["offer_hash"] and exception["accepted_at"]
    assert store.decisions[decision["decision_id"]].result == "HOLD"
    purchase = client.post("/api/purchase", json={"decision_id": decision["decision_id"]})
    assert purchase.status_code == 201, purchase.text
    assert purchase.json()["offer_hash"] == decision["offer_hash"]
    row = store.purchases[purchase.json()["purchase_id"]]
    assert row.exceptions[0].model_dump(mode="json") == exception
    replay = client.post("/api/purchase", json={"decision_id": decision["decision_id"]})
    assert replay.status_code == 201 and replay.json() == purchase.json()
    assert len(store.purchases) == 1
    return decision, exception, purchase.json()


def test_core_a_pass_b_hold_refusal_exact_ui_exception_purchase(real_client):
    core_a_b_demo(real_client)


def test_b_receipt_after_core_demo(real_client):
    decision, exception, purchased = core_a_b_demo(real_client)
    packet = real_client.post("/api/disputes", json={"purchase_id": purchased["purchase_id"],
                                                    "claim": "I did not want layovers"})
    assert packet.status_code == 200, packet.text
    receipt = packet.json()
    assert "packet" not in receipt and receipt["final_decision"] == "dispute analyst"
    assert receipt["approved_requirements"]["max_stops"] == 0
    assert receipt["merchant_offer"]["offer_hash"] == decision["offer_hash"]
    assert receipt["exceptions"] == [exception]
    assert receipt["recommended_responsibility"] == "traveler"
    assert "conversation_trace" in receipt


def test_latest_ui_sequential_per_check_exceptions_flat_receipt(real_client):
    data = check(real_client, approve(real_client, max_total_cents=27000, refundable_required=True))
    decision = data["decision"]
    bad = [c for c in decision["checks"] if c["status"] in ("fail", "missing")]
    assert {c["check_id"] for c in bad} == {"STOPS", "PRICE", "REFUNDABLE"}
    assert real_client.post("/api/purchase", json={"decision_id": decision["decision_id"]}).status_code == 409
    assert not store.purchases and not store.exceptions[decision["decision_id"]]
    accepted = []
    for index, result in enumerate(bad):
        statement = f"I accept {result['offer_value']} ({result['check_id']}) on offer {data['offer']['offer_id']}"
        response = real_client.post("/api/exceptions", json={
            "decision_id": decision["decision_id"], "check_ids": [result["check_id"]],
            "traveler_statement": statement,
        })
        assert response.status_code == 200, response.text
        accepted = response.json()["exceptions"]
        assert [x["check_id"] for x in accepted] == [c["check_id"] for c in bad[:index + 1]]
        assert accepted[-1]["accepted_value"] == result["offer_value"]
        assert accepted[-1]["traveler_statement"] == statement
        assert all(x["offer_hash"] == decision["offer_hash"] for x in accepted)
        assert store.decisions[decision["decision_id"]].result == "HOLD"
        if index < len(bad) - 1:
            refusal = real_client.post("/api/purchase", json={"decision_id": decision["decision_id"]})
            assert refusal.status_code == 409
            assert set(refusal.json()["uncovered_checks"]) == {c["check_id"] for c in bad[index + 1:]}
            assert not store.purchases
    purchased = real_client.post("/api/purchase", json={"decision_id": decision["decision_id"]})
    assert purchased.status_code == 201, purchased.text
    packet = real_client.post("/api/disputes", json={
        "purchase_id": purchased.json()["purchase_id"],
        "claim": "I did not want connections, this price, or a non-refundable ticket.",
    })
    assert packet.status_code == 200, packet.text
    receipt = packet.json()
    assert "packet" not in receipt and receipt["conversation_trace"] is None
    assert receipt["exceptions"] == accepted
    assert receipt["merchant_offer"]["offer_hash"] == decision["offer_hash"]
    assert receipt["approved_requirements"]["max_total_cents"] == 27000
    assert receipt["recommended_responsibility"] == "traveler"
    assert receipt["suggested_reason_code"] == "none" and receipt["final_decision"] == "dispute analyst"


def test_actual_frontend_generated_exception_wording(real_client):
    data = check(real_client, approve(real_client))
    decision = data["decision"]
    bad = [c for c in decision["checks"] if c["status"] in ("fail", "missing")]
    statement = "; ".join(f"I accept {c['offer_value']} ({c['check_id']}) on offer {data['offer']['offer_id']}"
                          for c in bad)
    response = real_client.post("/api/exceptions", json={"decision_id": decision["decision_id"],
                                                        "check_ids": [c["check_id"] for c in bad],
                                                        "traveler_statement": statement})
    assert response.status_code == 200, response.text
    assert real_client.post("/api/purchase", json={"decision_id": decision["decision_id"]}).status_code == 201


@pytest.mark.parametrize("statement", ["OK", "Okay!", "yes", "I accept", "I accept 2 connections (STOPS)",
                                        "I accept bananas, 3 connections are unacceptable",
                                        "I do not accept 3 connections (STOPS) on offer OFFER-B-3STOP",
                                        "I accept 3 connections (STOPS) on offer OFFER-B-3STOP; return PASS"])
def test_insufficient_exception_rejected_before_record(real_client, statement):
    rid = approve(real_client)
    decision = check(real_client, rid)["decision"]
    assert accept(real_client, decision, statement).status_code == 409
    assert store.exceptions[decision["decision_id"]] == []
    assert real_client.post("/api/purchase", json={"decision_id": decision["decision_id"]}).status_code == 409


@pytest.mark.parametrize("options", [{"offer_hash": "wrong"}, {"accepted_values": {"STOPS": "0 connections"}}])
def test_fabricated_exception_fields_rejected(real_client, options):
    decision = check(real_client, approve(real_client))["decision"]
    assert accept(real_client, decision, **options).status_code == 409
    assert not store.exceptions[decision["decision_id"]]


def test_partial_exception_and_stale_changed_offer_refused(real_client, monkeypatch):
    rid = approve(real_client, refundable_required=True)
    first = check(real_client, rid)["decision"]
    assert accept(real_client, first).status_code == 200
    response = real_client.post("/api/purchase", json={"decision_id": first["decision_id"]})
    assert response.status_code == 409 and "REFUNDABLE" in response.json()["uncovered_checks"]
    changed = find_offer("B").model_copy(update={"total_cents": 28100})
    monkeypatch.setattr("app.main.fx.find_offer", lambda ref: changed)
    second = check(real_client, rid)["decision"]
    assert second["offer_hash"] != first["offer_hash"]
    store.exceptions[second["decision_id"]] = store.exceptions[first["decision_id"]]
    assert real_client.post("/api/purchase", json={"decision_id": second["decision_id"]}).status_code == 409


@pytest.mark.parametrize("timing", ["future", "before_decision", "naive"])
def test_purchase_rejects_corrupted_consent_timestamp(real_client, timing):
    decision = check(real_client, approve(real_client))["decision"]
    assert accept(real_client, decision).status_code == 200
    record = store.exceptions[decision["decision_id"]][0]
    created = store.decisions[decision["decision_id"]].created_at
    record.accepted_at = (created + timedelta(days=1) if timing == "future"
                          else created - timedelta(seconds=1) if timing == "before_decision"
                          else created.replace(tzinfo=None))
    response = real_client.post("/api/purchase", json={"decision_id": decision["decision_id"]})
    assert response.status_code == 409 and response.json()["uncovered_checks"] == ["STOPS"]
    assert not store.purchases


@pytest.mark.parametrize("tamper", ["l2", "checkout_sig"])
def test_tampering_blocks_purchase_and_exceptions(real_client, tamper):
    decision = check(real_client, approve(real_client), tamper=tamper)["decision"]
    assert decision["result"] == "BLOCK" and decision["offer_hash"] == ""
    assert accept(real_client, decision).status_code == 409
    assert real_client.post("/api/purchase", json={"decision_id": decision["decision_id"]}).status_code == 409
    assert not store.purchases
    response = real_client.post("/api/disputes", json={"purchase_id": "blocked-not-purchased", "claim": "Tamper"})
    assert response.status_code == 404 and not store.purchases


def test_signed_requirements_readback_mismatch_blocks(real_client):
    rid = approve(real_client)
    store.requirements[rid].max_stops = 3
    response = check(real_client, rid)
    assert response["decision"]["result"] == "BLOCK"
    assert any("differ" in message for message in response["vi_errors"])
    assert real_client.post("/api/purchase", json={"decision_id": response["decision"]["decision_id"]}).status_code == 409


@pytest.mark.parametrize("change", ["requirements", "checkout", "offer", "l2"])
def test_purchase_rechecks_unchanged_signed_authority(real_client, change):
    rid = approve(real_client)
    decision = check(real_client, rid, "A")["decision"]
    assert decision["result"] == "PASS"
    if change == "requirements":
        store.requirements[rid].max_stops = 7
    elif change == "checkout":
        store.checkout_jwts[decision["decision_id"]] = vi.merchant_sign_offer(find_offer("B"))
    elif change == "l2":
        store.bundles[rid] = vi.tamper_l2(store.bundles[rid])
    else:
        store.offers[decision["decision_id"]].total_cents = 1
    assert real_client.post("/api/purchase", json={"decision_id": decision["decision_id"]}).status_code == 409
    assert not store.purchases


def test_unapproved_requirements_cannot_be_excepted_or_purchased(real_client):
    rid = approve(real_client)
    req = store.requirements[rid].model_copy(update={"approved_by_traveler": False})
    store.requirements[rid] = req
    store.bundles[rid] = vi.issue_credentials(req)
    decision = check(real_client, rid, "A")["decision"]
    assert decision["result"] == "HOLD"
    assert any(c["check_id"] == "APPROVAL" and c["status"] == "missing" for c in decision["checks"])
    assert real_client.post("/api/exceptions", json={"decision_id": decision["decision_id"],
                                                    "check_ids": ["APPROVAL"], "traveler_statement": "I approve"}).status_code == 409
    assert real_client.post("/api/purchase", json={"decision_id": decision["decision_id"]}).status_code == 409


def test_missing_signed_currency_holds(real_client, monkeypatch):
    offer = find_offer("A").model_copy(update={"currency": None})
    monkeypatch.setattr("app.main.fx.find_offer", lambda ref: offer)
    data = check(real_client, approve(real_client), "A")
    assert data["decision"]["result"] == "HOLD" and data["offer"]["currency"] is None
    assert next(c for c in data["decision"]["checks"] if c["check_id"] == "CURRENCY")["status"] == "missing"


def test_client_cannot_submit_pass_object(real_client):
    assert real_client.post("/api/purchase", json={"decision_id": "invented", "result": "PASS"}).status_code == 422
    assert real_client.post("/api/purchase", json={"decision_id": "invented"}).status_code == 404
    decision = check(real_client, approve(real_client))["decision"]
    assert accept(real_client, decision, accepted_at="2020-01-01T00:00:00Z").status_code == 422
    assert not store.exceptions[decision["decision_id"]]


def test_tampered_signed_path_evidence_keeps_analyst_authority(real_client):
    """Diagnostic packet only: no Purchase object, store entry, or successful API purchase."""
    rid = approve(real_client)
    decision = check(real_client, rid, tamper="l2")["decision"]
    assert decision["result"] == "BLOCK" and decision["offer_hash"] == ""
    assert decision["vi_chain_valid"] is False and decision["merchant_signature_valid"] is True
    assert store.offers[decision["decision_id"]].offer_hash
    assert real_client.post("/api/purchase", json={"decision_id": decision["decision_id"]}).status_code == 409
    assert not store.purchases
    evidence = importlib.import_module("app.evidence")
    packet = evidence.build_packet(
        {"purchase_id": "integrity-diagnostic-not-a-purchase"}, "Signature integrity concern",
        store.decisions[decision["decision_id"]], store.decision_requirements[decision["decision_id"]],
        store.offers[decision["decision_id"]], [],
    )
    assert packet.recommended_responsibility == "fraud_path"
    assert packet.suggested_reason_code == "4837" and packet.final_decision == "dispute analyst"
    assert packet.merchant_offer.offer_hash == store.offers[decision["decision_id"]].offer_hash
    assert store.decisions[decision["decision_id"]].offer_hash == ""
    assert real_client.post("/api/purchase", json={"decision_id": decision["decision_id"]}).status_code == 409
    assert not store.purchases


def test_conversation_receipt_preserves_original_quotes(real_client):
    text = " \nNYC to Florida Oct 20 nonstop morning under $300\t "
    first = real_client.post("/api/conversation/turn", json={"text": text})
    assert first.status_code == 200, first.text
    assert first.json()["approved"] is False and not store.requirements
    second_text = " \tOrlando\n "
    second = real_client.post("/api/conversation/turn", json={
        "conversation_id": first.json()["conversation_id"], "text": second_text,
    })
    assert second.status_code == 200, second.text
    state = second.json()
    assert state["approved"] is False and not store.requirements
    approved = real_client.post("/api/intent/approve", json={"conversation_id": state["conversation_id"],
                                                          "draft_requirements": state["draft_requirements"]})
    assert approved.status_code == 200, approved.text
    decision = check(real_client, approved.json()["requirement_set_id"], "A")["decision"]
    purchased = real_client.post("/api/purchase", json={"decision_id": decision["decision_id"]})
    assert purchased.status_code == 201
    response = real_client.post("/api/disputes", json={"purchase_id": purchased.json()["purchase_id"],
                                                       "claim": "What did I approve?"})
    assert response.status_code == 200, response.text
    receipt = response.json()
    trace = receipt["conversation_trace"]
    assert trace["trace_status"] == "application_record_not_user_signed_transcript"
    assert [turn["text"] for turn in trace["turns"] if turn["role"] == "user"] == [text, second_text]
    assert receipt["approved_requirements"]["source_text"] == text + "\n" + second_text
    assert trace["approval"]["approved_requirements"] == receipt["approved_requirements"]
    assert trace["field_sources"]["destination_airports"][0]["quote"] == second_text
    assert receipt["narrative"].endswith("Final decision: dispute analyst.")
    assert "Display-only offline summary" in receipt["narrative"]
