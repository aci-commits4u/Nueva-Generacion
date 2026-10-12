"""FastAPI entrypoint: thin orchestration only.

Victor's modules (rules_engine, evidence, foundry_client) are imported lazily so the server and demo
page run before they are merged. A missing rules_engine/evidence yields HTTP 501 - never a stand-in
decision (AGENTS rule 1: only rules_engine.py decides). foundry_client output is display-only, so if it
is missing or fails we continue and flag `llm_fallback`.
"""
from __future__ import annotations

import importlib
import os
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app import fixtures_loader as fx
from app import vi_adapter as vi
from app.models import ApprovedRequirements, Decision, ExceptionAcceptance, FlightOffer
from app.store import Purchase, store

load_dotenv()
app = FastAPI(title="Intent Judge")

DEMO_TODAY = os.getenv("DEMO_TODAY", "2026-10-12")  # fixed so extraction is repeatable on stage


def _dep(name: str) -> ModuleType:
    """Import a teammate module at call time; 501 if it has not been merged yet."""
    try:
        return importlib.import_module(f"app.{name}")
    except ModuleNotFoundError as exc:
        if exc.name != f"app.{name}":
            raise
        raise HTTPException(501, f"app.{name} is not available yet (owned by Victor); nothing was decided.")


def _optional_dep(name: str) -> ModuleType | None:
    try:
        return _dep(name)
    except HTTPException:
        return None


def _get(mapping: dict, key: str, what: str):
    if key not in mapping:
        raise HTTPException(404, f"Unknown {what}: {key}")
    return mapping[key]


# --------------------------------------------------------------------------- request bodies
class RequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExtractBody(RequestBody):
    text: str = Field(min_length=1, max_length=12000)


class ConversationBody(ExtractBody):
    conversation_id: str | None = None


class ApproveBody(RequestBody):
    draft_requirements: dict
    answers: dict = Field(default_factory=dict)
    source_text: str = ""
    conversation_id: str | None = None


class CheckBody(RequestBody):
    requirement_set_id: str
    offer_id: str  # letter key ("B") or offer_id ("OFFER-B-3STOP")
    tamper: Literal["l2", "checkout_sig"] | None = None  # demo/test toggles (scenario 12)
    note: str | None = None  # text planted inside merchant data (prompt-injection scenario)


class ExceptionBody(RequestBody):
    decision_id: str
    check_ids: list[str]
    traveler_statement: str
    offer_hash: str | None = None
    accepted_values: dict[str, str] | None = None


class PurchaseBody(RequestBody):
    decision_id: str


class DisputeBody(RequestBody):
    purchase_id: str
    claim: str


# --------------------------------------------------------------------------- routes
@app.get("/api/health")
def health() -> dict:
    """`rules_engine` tells the UI whether decisions are real: loaded | fake (dev stand-in) | missing."""
    try:
        mod = importlib.import_module("app.rules_engine")
        engine = "loaded" if getattr(mod, "__file__", None) else "fake"
    except ModuleNotFoundError:
        engine = "missing"
    return {"status": "ok", "rules_engine": engine}


@app.get("/api/scenarios")
def scenarios() -> dict:
    offers = {
        key: {"key": key, **o.model_dump(mode="json")}
        for key in "ABCDEFGH"
        if (o := fx.find_offer(key))
    }
    return {
        "base_requirements": fx.base_requirements().model_dump(mode="json"),
        "offers": list(offers.values()),
        "scenarios": fx.scenarios(),
    }


@app.post("/api/reset")
def reset() -> dict:
    store.reset()
    return {"status": "reset"}


@app.post("/api/intent/extract")
def extract(body: ExtractBody) -> dict:
    """LLM (or mock) drafts requirements + questions. The draft is NOT approved and decides nothing."""
    foundry = _dep("foundry_client")
    result = foundry.extract_requirements(body.text, DEMO_TODAY)
    return result.model_dump(mode="json") if hasattr(result, "model_dump") else result


@app.post("/api/conversation/turn")
def conversation_turn(body: ConversationBody) -> dict:
    """Return an unapproved conversation draft; chat never calls the approval handler."""
    conversation = _dep("conversation")
    if body.conversation_id is not None:
        _get(store.conversation_drafts, body.conversation_id, "conversation_id")
    try:
        state = conversation.conversation_turn(body.conversation_id, body.text, DEMO_TODAY)
        store.conversation_drafts[state["conversation_id"]] = deepcopy(state)
        return state
    except KeyError:
        raise HTTPException(404, "Unknown conversation_id")
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.post("/api/intent/approve")
def approve(body: ApproveBody) -> dict:
    """Traveler approves the exact list; it is signed into the VI L2 mandate as a custom constraint."""
    server_controlled = {"requirement_set_id", "approved_by_traveler", "approved_at", "source_text"}
    merged = {
        k: v for k, v in {**body.draft_requirements, **body.answers}.items()
        if k not in server_controlled
    }
    unknown = set(merged) - set(ApprovedRequirements.model_fields)
    if unknown:
        raise HTTPException(422, "Unsupported draft fields")
    if merged.get("category", "flight") != "flight":
        raise HTTPException(422, "Only flight requirements are implemented")
    if not merged.get("currency"):
        raise HTTPException(422, "Review and specify the budget currency")
    for field in ("max_total_cents", "passengers", "max_stops"):
        value = merged.get(field)
        if value is not None and (type(value) is not int or value < (0 if field == "max_stops" else 1)):
            raise HTTPException(422, f"Invalid {field}")
    source_text = body.source_text
    if body.conversation_id is not None:
        reviewed = _get(store.conversation_drafts, body.conversation_id, "conversation_id")
        source_text = "\n".join(t["text"] for t in reviewed["turns"] if t["role"] == "user")
    try:
        req = ApprovedRequirements(
            **merged,
            requirement_set_id=f"req-{uuid.uuid4().hex[:8]}",
            source_text=source_text,
            approved_by_traveler=True,
            approved_at=datetime.now(timezone.utc),
        )
    except ValidationError as exc:
        raise HTTPException(422, f"Requirements incomplete: {[e['loc'][0] for e in exc.errors()]}")
    if not req.origin_airports or not req.destination_airports:
        raise HTTPException(422, "Nonempty origin and destination airports are required")
    if len(req.currency) != 3 or not req.currency.isalpha() or not req.currency.isupper():
        raise HTTPException(422, "Specify a three-letter uppercase currency")
    if req.depart_window and (req.depart_window.earliest > req.depart_window.latest
                              or req.depart_window.earliest.tzinfo or req.depart_window.latest.tzinfo):
        raise HTTPException(422, "Use an ordered airport-local departure window")
    bundle = vi.issue_credentials(req)
    trace = None
    if body.conversation_id is not None:
        conversation = _dep("conversation")
        try:
            trace = conversation.record_approval(body.conversation_id, req.model_copy(deep=True))
        except KeyError:
            raise HTTPException(404, "Unknown conversation_id")
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        store.conversation_traces[req.requirement_set_id] = deepcopy(trace)
    store.requirements[req.requirement_set_id] = req.model_copy(deep=True)
    store.bundles[req.requirement_set_id] = bundle
    return {
        "requirement_set_id": req.requirement_set_id,
        "requirements": req.model_dump(mode="json"),
        "vi_l2_summary": {
            "mode": "AUTONOMOUS",
            "constraint": vi.CONSTRAINT_TYPE,
            "authority_constraint": vi.CONSTRAINT_TYPE,
            "category": req.category,
            "signed_by": "traveler (demo key)",
            "approved_at": req.approved_at.isoformat(),
        },
    }


@app.post("/api/check")
def check(body: CheckBody) -> dict:
    req = _get(store.requirements, body.requirement_set_id, "requirement_set_id")
    bundle = store.bundles[body.requirement_set_id]
    fixture = fx.find_offer(body.offer_id)
    if fixture is None:
        raise HTTPException(404, f"Unknown offer: {body.offer_id}")
    rules = _dep("rules_engine")

    if body.tamper == "l2":
        bundle = vi.tamper_l2(bundle)
    checkout_jwt = vi.merchant_sign_offer(
        fixture, signer=vi.AGENT if body.tamper == "checkout_sig" else None, note=body.note
    )
    verified = vi.verify_and_extract(bundle, checkout_jwt)
    # Never carry data from an unverified payload into the decision: use an empty placeholder instead.
    offer = verified.offer or FlightOffer(
        offer_id="unverified", merchant_id="unverified", merchant_name="unverified",
        segments=[], offer_hash=vi.checkout_hash(checkout_jwt),
    )
    authority_valid = verified.vi_chain_valid and vi.requirements_match(req, verified.signed_requirements)
    if verified.vi_chain_valid and not authority_valid:
        verified.errors.append("Stored approved requirements differ from verified signed requirements")
    decision: Decision = rules.evaluate(req.model_copy(deep=True), offer.model_copy(deep=True),
                                       authority_valid, verified.merchant_signature_valid)

    explain_info = {"traveler_message": None, "suggested_next_step": "none", "llm_fallback": True}
    foundry = _optional_dep("foundry_client")
    if foundry is not None:
        try:
            explained = foundry.explain(decision.model_copy(deep=True), req.model_copy(deep=True))
            explain_info = explained.model_dump(mode="json") if hasattr(explained, "model_dump") else dict(explained)
            decision = decision.model_copy(update={"explanation": explain_info.get("traveler_message")})
        except Exception:  # display-only text must never break a decision
            pass

    store.decisions[decision.decision_id] = decision.model_copy(deep=True)
    store.offers[decision.decision_id] = offer.model_copy(deep=True)
    store.checkout_jwts[decision.decision_id] = checkout_jwt
    store.decision_requirements[decision.decision_id] = req.model_copy(deep=True)
    store.exceptions.setdefault(decision.decision_id, [])
    return {
        "decision": decision.model_dump(mode="json"),
        "offer": offer.model_dump(mode="json"),
        "explanation": explain_info,
        "vi_errors": verified.errors,
    }


@app.post("/api/exceptions")
def add_exceptions(body: ExceptionBody) -> dict:
    """Record a specific exception: which check, what value, which exact offer, when."""
    decision = _get(store.decisions, body.decision_id, "decision_id")
    if decision.result == "BLOCK":
        raise HTTPException(409, "Blocked: credential or merchant signature invalid. Exceptions cannot apply.")
    if not body.check_ids or len(set(body.check_ids)) != len(body.check_ids):
        raise HTTPException(422, "Select distinct failed or missing checks")
    if body.traveler_statement.strip().lower().strip(".! ") in {"", "ok", "okay", "yes", "sure", "accept", "approved"}:
        raise HTTPException(409, "State the specific offered value you accept; bare OK is not consent")
    if body.offer_hash is not None and body.offer_hash != decision.offer_hash:
        raise HTTPException(409, "Exception offer hash does not match the stored decision")
    by_id = {c.check_id: c for c in decision.checks}
    accepted: list[ExceptionAcceptance] = []
    for check_id in body.check_ids:
        found = by_id.get(check_id)
        if found is None or found.status not in ("fail", "missing") or check_id == "APPROVAL":
            raise HTTPException(409, f"{check_id} cannot be accepted as an exception.")
        accepted.append(
            ExceptionAcceptance(
                decision_id=decision.decision_id, offer_hash=decision.offer_hash, check_id=check_id,
                accepted_value=found.offer_value, traveler_statement=body.traveler_statement,
                accepted_at=datetime.now(timezone.utc),
            )
        )
    derived = {e.check_id: e.accepted_value for e in accepted}
    if body.accepted_values is not None and body.accepted_values != derived:
        raise HTTPException(409, "Accepted values must equal the stored verified check values")
    existing = store.exceptions.get(decision.decision_id, [])
    proposed = [e for e in existing if e.check_id not in body.check_ids] + accepted
    rules = _dep("rules_engine")
    allowed, reason, uncovered = rules.can_purchase(decision.model_copy(deep=True), deepcopy(proposed))
    if (not allowed and not uncovered) or set(body.check_ids) & set(uncovered):
        raise HTTPException(409, f"Specific consent required: {reason}")
    store.exceptions[decision.decision_id] = proposed
    return {"exceptions": [e.model_dump(mode="json") for e in proposed]}


@app.post("/api/purchase")
def purchase(body: PurchaseBody):
    """The ONLY path that creates a purchase; rules_engine.can_purchase decides, we enforce with 409."""
    decision = _get(store.decisions, body.decision_id, "decision_id")
    rules = _dep("rules_engine")
    req = _get(store.decision_requirements, decision.decision_id, "decision requirements")
    checkout_jwt = _get(store.checkout_jwts, decision.decision_id, "signed checkout")
    verified = vi.verify_and_extract(store.bundles[decision.requirement_set_id], checkout_jwt)
    offer = store.offers[decision.decision_id]
    if (not verified.vi_chain_valid or not verified.merchant_signature_valid
            or not vi.requirements_match(req, verified.signed_requirements)
            or not vi.requirements_match(store.requirements[decision.requirement_set_id], verified.signed_requirements)
            or verified.offer is None or verified.offer != offer
            or decision.offer_hash != verified.offer.offer_hash):
        return JSONResponse(status_code=409, content={"reason": "Signed authorization or offer changed; check again",
                                                     "uncovered_checks": []})
    accepted = store.exceptions.get(decision.decision_id, [])
    allowed, reason, uncovered = rules.can_purchase(decision.model_copy(deep=True), deepcopy(accepted))
    if not allowed:
        return JSONResponse(status_code=409, content={"reason": reason, "uncovered_checks": uncovered})
    existing = next((p for p in store.purchases.values() if p.decision_id == decision.decision_id), None)
    if existing is None:
        existing = Purchase(f"pur-{uuid.uuid4().hex[:8]}", decision.decision_id, decision.requirement_set_id,
                            decision.offer_hash, exceptions=deepcopy(accepted))
        store.purchases[existing.purchase_id] = existing
    return JSONResponse(status_code=201, content={"purchase_id": existing.purchase_id, "offer_hash": existing.offer_hash})


@app.post("/api/disputes")
def dispute(body: DisputeBody) -> dict:
    purchase_row = _get(store.purchases, body.purchase_id, "purchase_id")
    evidence = _dep("evidence")
    decision = store.decisions[purchase_row.decision_id]
    packet = evidence.build_packet(
        deepcopy(purchase_row), body.claim, decision.model_copy(deep=True),
        store.decision_requirements[decision.decision_id].model_copy(deep=True),
        store.offers[decision.decision_id].model_copy(deep=True), deepcopy(purchase_row.exceptions),
    )
    foundry = _optional_dep("foundry_client")
    if foundry is not None:
        try:
            packet = packet.model_copy(update={"narrative": foundry.evidence_narrative(packet.model_copy(deep=True))})
        except Exception:
            pass
    response = packet.model_dump(mode="json")
    response["conversation_trace"] = deepcopy(store.conversation_traces.get(decision.requirement_set_id))
    return response


# Mounted last so /api/* routes win.
app.mount("/", StaticFiles(directory=Path(__file__).parent.parent / "web", html=True), name="web")
