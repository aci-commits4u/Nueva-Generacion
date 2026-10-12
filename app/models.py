"""Shared contract between rules_engine (Victor) and vi_adapter/main (Jossue).

Taken from docs/05-architecture.md. Changes from the doc (flag to Victor before freeze):
  * `category` (default "flight") on ApprovedRequirements and FlightOffer: the product is
    category-neutral, flights are the demo (Plan 3, "C0-lite"). Class names are unchanged on purpose.
  * CheckResult.check_id also allows "APPROVAL" (docs/07 step 2 emits it).
  * FlightOffer.offer_hash defaults to "" so rules tests can build offers from fixtures
    without VI; vi_adapter always sets it from the signed checkout_jwt.
  * ExtractResult / ExplainResult added for the foundry_client signatures in Plan 1 section 4.
Money is integer cents. Times are ISO-8601 with offsets; compare in local airport time as given.
"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel


class TimeWindow(BaseModel):
    earliest: time
    latest: time


class ApprovedRequirements(BaseModel):
    requirement_set_id: str
    category: str = "flight"  # flights are the demo category; the contract is category-neutral (Plan 3)
    origin_airports: list[str]
    destination_airports: list[str]
    depart_date: date
    depart_window: TimeWindow | None = None
    arrive_by: time | None = None
    max_stops: int | None = None  # 0 = nonstop
    max_total_cents: int
    currency: str = "USD"
    cabin: Literal["economy", "premium_economy", "business", "first"] | None = None
    refundable_required: bool | None = None
    passengers: int = 1
    source_text: str = ""  # traveler's original words (evidence only, never used to decide)
    approved_by_traveler: bool
    approved_at: datetime


class Segment(BaseModel):
    carrier: str
    flight_number: str
    from_airport: str
    to_airport: str
    depart_local: datetime
    arrive_local: datetime


class FlightOffer(BaseModel):
    """Extracted ONLY from the verified merchant-signed checkout_jwt."""

    category: str = "flight"
    offer_id: str
    merchant_id: str
    merchant_name: str
    segments: list[Segment]
    total_cents: int | None = None  # None => missing
    currency: str = "USD"
    cabin: str | None = None
    refundable: bool | None = None
    passengers: int | None = None
    offer_hash: str = ""  # B64U(SHA-256(checkout_jwt)) == VI checkout_hash


CheckId = Literal[
    "APPROVAL", "ORIGIN", "DESTINATION", "DATE", "DEPART_WINDOW", "ARRIVE_BY",
    "STOPS", "PRICE", "CURRENCY", "CABIN", "REFUNDABLE", "PASSENGERS",
]


class CheckResult(BaseModel):
    check_id: CheckId
    requirement: str
    offer_value: str
    status: Literal["pass", "fail", "missing", "not_required"]
    message: str  # plain English for the traveler


class Decision(BaseModel):
    decision_id: str
    requirement_set_id: str
    offer_hash: str
    result: Literal["PASS", "HOLD", "BLOCK"]
    vi_chain_valid: bool
    merchant_signature_valid: bool
    checks: list[CheckResult]
    explanation: str | None = None  # LLM text; display only, never used for logic
    created_at: datetime


class ExceptionAcceptance(BaseModel):
    decision_id: str
    offer_hash: str
    check_id: str
    accepted_value: str
    traveler_statement: str  # e.g. "I accept 3 connections on this itinerary"
    accepted_at: datetime


class EvidencePacket(BaseModel):
    purchase_id: str
    dispute_claim: str
    vi_chain_valid: bool
    merchant_signature_valid: bool
    approved_requirements: ApprovedRequirements
    merchant_offer: FlightOffer
    checks: list[CheckResult]
    exceptions: list[ExceptionAcceptance]
    suggested_reason_code: Literal["4837", "4853", "none"]
    recommended_responsibility: Literal["traveler", "agent_platform", "merchant", "fraud_path", "unclear"]
    rationale: str
    narrative: str | None = None  # LLM summary; display only
    final_decision: Literal["dispute analyst"] = "dispute analyst"


class ExtractResult(BaseModel):
    draft_requirements: dict  # NOT approved; becomes ApprovedRequirements only via /api/intent/approve
    questions: list[str] = []
    notes: str = ""
    llm_fallback: bool = False


class ExplainResult(BaseModel):
    traveler_message: str
    suggested_next_step: Literal["choose_another", "accept_exception", "none"] = "none"
    llm_fallback: bool = False
