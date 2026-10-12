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
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

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
class ExtractBody(BaseModel):
    text: str


class ApproveBody(BaseModel):
    draft_requirements: dict
    answers: dict = {}
    source_text: str = ""


class CheckBody(BaseModel):
    requirement_set_id: str
    offer_id: str  # letter key ("B") or offer_id ("OFFER-B-3STOP")
    tamper: Literal["l2", "checkout_sig"] | None = None  # demo/test toggles (scenario 12)
    note: str | None = None  # text planted inside merchant data (prompt-injection scenario)


class ExceptionBody(BaseModel):
    decision_id: str
    check_ids: list[str]
    traveler_statement: str


class PurchaseBody(BaseModel):
    decision_id: str


class DisputeBody(BaseModel):
    purchase_id: str
    claim: str


# --------------------------------------------------------------------------- routes
@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


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


@app.post("/api/intent/approve")
def approve(body: ApproveBody) -> dict:
    """Traveler approves the exact list; it is signed into the VI L2 mandate as a custom constraint."""
    server_controlled = {"requirement_set_id", "approved_by_traveler", "approved_at", "source_text"}
    merged = {
        k: v for k, v in {**body.draft_requirements, **body.answers}.items()
        if v is not None and k not in server_controlled
    }
    try:
        req = ApprovedRequirements(
            **merged,
            requirement_set_id=f"req-{uuid.uuid4().hex[:8]}",
            source_text=body.source_text,
            approved_by_traveler=True,
            approved_at=datetime.now().astimezone(),
        )
    except ValidationError as exc:
        raise HTTPException(422, f"Requirements incomplete: {[e['loc'][0] for e in exc.errors()]}")
    bundle = vi.issue_credentials(req)
    store.requirements[req.requirement_set_id] = req
    store.bundles[req.requirement_set_id] = bundle
    return {
        "requirement_set_id": req.requirement_set_id,
        "requirements": req.model_dump(mode="json"),
        "vi_l2_summary": {
            "mode": "AUTONOMOUS",
            "constraint": vi.CONSTRAINT_TYPE,
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
    decision: Decision = rules.evaluate(req, offer, verified.vi_chain_valid, verified.merchant_signature_valid)

    explain_info = {"traveler_message": None, "suggested_next_step": "none", "llm_fallback": True}
    foundry = _optional_dep("foundry_client")
    if foundry is not None:
        try:
            explained = foundry.explain(decision, req)
            explain_info = explained.model_dump(mode="json") if hasattr(explained, "model_dump") else dict(explained)
            decision = decision.model_copy(update={"explanation": explain_info.get("traveler_message")})
        except Exception:  # display-only text must never break a decision
            pass

    store.decisions[decision.decision_id] = decision
    store.offers[decision.decision_id] = offer
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
                accepted_at=datetime.now().astimezone(),
            )
        )
    existing = store.exceptions.setdefault(decision.decision_id, [])
    existing[:] = [e for e in existing if e.check_id not in body.check_ids] + accepted
    return {"exceptions": [e.model_dump(mode="json") for e in existing]}


@app.post("/api/purchase")
def purchase(body: PurchaseBody):
    """The ONLY path that creates a purchase; rules_engine.can_purchase decides, we enforce with 409."""
    decision = _get(store.decisions, body.decision_id, "decision_id")
    rules = _dep("rules_engine")
    allowed, reason, uncovered = rules.can_purchase(decision, store.exceptions.get(decision.decision_id, []))
    if not allowed:
        return JSONResponse(status_code=409, content={"reason": reason, "uncovered_checks": uncovered})
    existing = next((p for p in store.purchases.values() if p.decision_id == decision.decision_id), None)
    if existing is None:
        existing = Purchase(f"pur-{uuid.uuid4().hex[:8]}", decision.decision_id, decision.requirement_set_id, decision.offer_hash)
        store.purchases[existing.purchase_id] = existing
    return JSONResponse(status_code=201, content={"purchase_id": existing.purchase_id, "offer_hash": existing.offer_hash})


@app.post("/api/disputes")
def dispute(body: DisputeBody) -> dict:
    purchase_row = _get(store.purchases, body.purchase_id, "purchase_id")
    evidence = _dep("evidence")
    decision = store.decisions[purchase_row.decision_id]
    packet = evidence.build_packet(
        purchase_row, body.claim, decision, store.requirements[decision.requirement_set_id],
        store.offers[decision.decision_id], store.exceptions.get(decision.decision_id, []),
    )
    foundry = _optional_dep("foundry_client")
    if foundry is not None:
        try:
            packet = packet.model_copy(update={"narrative": foundry.evidence_narrative(packet)})
        except Exception:
            pass
    return packet.model_dump(mode="json")


# Mounted last so /api/* routes win.
app.mount("/", StaticFiles(directory=Path(__file__).parent.parent / "web", html=True), name="web")
