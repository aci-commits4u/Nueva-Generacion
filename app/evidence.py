"""Assemble copied application evidence; only a human analyst decides a dispute."""
from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from app.models import ApprovedRequirements, CheckResult, Decision, EvidencePacket, ExceptionAcceptance, FlightOffer


_ABSENT = object()
_CLAIM_CHECKS = {
    "APPROVAL": r"\b(?:approve|approved|approval|authorize|authorized)\b",
    "ORIGIN": r"\b(?:origin|depart(?:ure)? from|from airport)\b",
    "DESTINATION": r"\b(?:destination|arrive at|to airport)\b",
    "DATE": r"\b(?:date|day)\b",
    "DEPART_WINDOW": r"\b(?:morning|afternoon|evening|departure time|depart_window)\b",
    "ARRIVE_BY": r"\b(?:arrive by|arrival time|arrive_by)\b",
    "STOPS": r"\b(?:nonstop|non-stop|layovers?|connections?|stops)\b",
    "PRICE": r"\b(?:price|budget|cost|total|expensive)\b",
    "CURRENCY": r"\b(?:currency|usd|eur|dollars?|euros?)\b",
    "CABIN": r"\b(?:cabin|economy|business|first class)\b",
    "REFUNDABLE": r"\b(?:refundable|non-refundable|nonrefundable)\b",
    "PASSENGERS": r"\b(?:passengers?|travelers?)\b",
}
_DELIVERY_CLAIM = re.compile(
    r"\b(?:deliver(?:ed|y)?|actually|flew|flown|cancel(?:led|ed|lation)|received|"
    r"never arrived|not provided|failed to provide|refund(?:ed|s)?)\b|\b(?:paid|booked)\b.*\bgot\b",
    re.IGNORECASE,
)
_BYPASS_CLAIM = re.compile(r"\b(?:bypass(?:ed)?|outside (?:the|our) flow|different offer)\b", re.IGNORECASE)
_PREFERENCE_CLAIM = re.compile(
    r"\bi (?:wanted|required|requested|asked for|approved|expected|(?:did not|didn't) want)\b",
    re.IGNORECASE,
)


def _record_value(record: Any, key: str) -> Any:
    return record.get(key, _ABSENT) if isinstance(record, Mapping) else getattr(record, key, _ABSENT)


def _required_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value


def _validate_records(purchase: Any, decision: Decision, req: ApprovedRequirements, offer: FlightOffer) -> str:
    """Do not join unrelated records or ambiguous checks into apparent evidence."""
    purchase_id = _required_id(_record_value(purchase, "purchase_id"), "purchase_id")
    _required_id(decision.decision_id, "decision_id")
    _required_id(req.requirement_set_id, "requirement_set_id")
    _required_id(offer.offer_hash, "offer_hash")
    unbound_integrity_block = (
        decision.result == "BLOCK" and decision.vi_chain_valid is False
        and decision.merchant_signature_valid is True and decision.offer_hash == ""
    )
    if (decision.requirement_set_id != req.requirement_set_id
            or (decision.offer_hash != offer.offer_hash and not unbound_integrity_block)):
        raise ValueError("Decision must identify these requirements and this signed offer hash")
    for key, expected in (
        ("decision_id", decision.decision_id),
        ("requirement_set_id", req.requirement_set_id),
        ("offer_hash", offer.offer_hash),
        ("offer_id", offer.offer_id),
    ):
        value = _record_value(purchase, key)
        if value is not _ABSENT and value != expected:
            raise ValueError(f"Purchase {key} does not match its evidence records")
    check_ids = [check.check_id for check in decision.checks]
    if len(check_ids) != len(set(check_ids)):
        raise ValueError("Duplicate check ids make exception evidence ambiguous")
    return purchase_id


def _aware_timestamp(value: Any) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _statement_checks(statement: str, checks: list[CheckResult]) -> set[str]:
    """Match the checkout consent grammar completely, with check-specific clauses."""
    if not isinstance(statement, str) or not statement.strip():
        return set()
    covered: set[str] = set()
    offer_labels: set[str] = set()
    for raw_clause in statement.split(";"):
        clause = raw_clause.strip()
        matched = False
        for check in checks:
            value, check_id = re.escape(check.offer_value), re.escape(check.check_id)
            if re.fullmatch(rf"I accept {check_id}: {value}\.?", clause, re.IGNORECASE):
                matched = True
            elif (check.check_id == "STOPS" and check.status != "missing"
                  and re.fullmatch(rf"I accept {value} on this itinerary\.?", clause, re.IGNORECASE)):
                matched = True
            else:
                ui_match = re.fullmatch(
                    rf"I accept {value} \({check_id}\) on offer ([A-Za-z0-9_-]+)\.?", clause, re.IGNORECASE,
                )
                if ui_match:
                    matched = True
                    offer_labels.add(ui_match.group(1))
            if matched:
                covered.add(check.check_id)
                break
        if not matched:
            return set()
    return covered if len(offer_labels) <= 1 else set()


def _matching_exceptions(
    purchase: Any, decision: Decision, req: ApprovedRequirements, exceptions: list[ExceptionAcceptance],
) -> list[ExceptionAcceptance]:
    """Consent must match literal stored values and precede a recorded purchase."""
    if (decision.vi_chain_valid is not True or decision.merchant_signature_valid is not True
            or decision.result != "HOLD"):
        return []
    check_ids = set(_CLAIM_CHECKS) - {"APPROVAL"}
    mandatory = {"ORIGIN", "DESTINATION", "DATE", "PRICE", "CURRENCY", "PASSENGERS"}
    if (len(decision.checks) != len(check_ids) or {check.check_id for check in decision.checks} != check_ids
            or any(not all(isinstance(value, str) and value.strip()
                           for value in (check.requirement, check.offer_value, check.message))
                   or check.status not in {"pass", "fail", "missing", "not_required"}
                   or (check.check_id in mandatory and check.status == "not_required")
                   for check in decision.checks)):
        return []
    checks = {check.check_id: check for check in decision.checks}
    bad_checks = [check for check in decision.checks if check.status in {"fail", "missing"}]
    now = datetime.now(timezone.utc)
    matched = []
    for exception in exceptions:
        check = checks.get(exception.check_id)
        if (
            check is None or check.check_id == "APPROVAL" or check.status not in {"fail", "missing"}
            or exception.decision_id != decision.decision_id or exception.offer_hash != decision.offer_hash
            or exception.accepted_value != check.offer_value
            or check.check_id not in _statement_checks(exception.traveler_statement, bad_checks)
            or not _aware_timestamp(exception.accepted_at) or not _aware_timestamp(decision.created_at)
            or not decision.created_at <= exception.accepted_at <= now
            or not req.approved_by_traveler or not _aware_timestamp(req.approved_at)
            or exception.accepted_at < req.approved_at
        ):
            continue
        valid_timing = True
        for key in ("created_at", "purchased_at"):
            purchased_at = _record_value(purchase, key)
            if purchased_at is not _ABSENT:
                if isinstance(purchased_at, str):
                    try:
                        purchased_at = datetime.fromisoformat(purchased_at)
                    except ValueError:
                        valid_timing = False
                        break
                if not _aware_timestamp(purchased_at) or exception.accepted_at > purchased_at:
                    valid_timing = False
                    break
        if valid_timing:
            matched.append(exception.model_copy(deep=True))
    return matched


def _recommendation(
    claim: str, decision: Decision, req: ApprovedRequirements, exceptions: list[ExceptionAcceptance],
) -> tuple[str, str, str]:
    """Use recorded checks, not allegations or model explanations, as authority."""
    if not decision.vi_chain_valid or not decision.merchant_signature_valid:
        return "fraud_path", "4837", "Credential or merchant-signature integrity failed; review the fraud path."
    if decision.result == "BLOCK":
        return "agent_platform", "4853", "A purchase is recorded against a BLOCK decision; review the enforcement bypass."
    if not req.approved_by_traveler:
        return "agent_platform", "4853", "A purchase is recorded without traveler approval of the requirements."
    accepted = {exception.check_id for exception in exceptions}
    uncovered = [check.check_id for check in decision.checks
                 if check.status in {"fail", "missing"} and check.check_id not in accepted]
    if uncovered:
        return "agent_platform", "4853", (
            f"The recorded purchase has uncovered failed or missing checks ({', '.join(uncovered)}); "
            "review the enforcement bypass."
        )
    if _DELIVERY_CLAIM.search(claim):
        return "unclear", "none", (
            "The claim concerns delivery, but the signed offer and application consent do not prove what was delivered."
        )
    if _BYPASS_CLAIM.search(claim):
        return "unclear", "none", "The allegation of bypass or a different offer is not supported by these recorded checks."
    named_check = claim.strip().upper()
    if not _PREFERENCE_CLAIM.search(claim) and named_check not in _CLAIM_CHECKS:
        return "unclear", "none", "The claim is not a recognized approved-requirement preference; further evidence is needed."
    disputed = [check_id for check_id, pattern in _CLAIM_CHECKS.items()
                if re.search(pattern, claim, re.IGNORECASE) or named_check == check_id]
    checks = {check.check_id: check for check in decision.checks}
    if not disputed or any(check_id not in checks for check_id in disputed):
        return "unclear", "none", "There is insufficient recorded check evidence to assess this dispute claim."
    if decision.result == "HOLD" and not any(check.status in {"fail", "missing"} for check in decision.checks):
        return "unclear", "none", "The HOLD record lacks check evidence explaining whether purchase was allowed."
    if any(checks[check_id].status not in {"pass", "not_required"} and check_id not in accepted
           for check_id in disputed):
        return "unclear", "none", "The disputed checks do not establish approved or accepted purchase terms."
    excepted = [check_id for check_id in disputed if check_id in accepted]
    if excepted:
        return "traveler", "none", (
            f"The disputed deviations ({', '.join(excepted)}) have exact matching traveler exception records."
        )
    not_required = [check_id for check_id in disputed if checks[check_id].status == "not_required"]
    if not_required:
        return "traveler", "none", (
            f"The disputed preferences ({', '.join(not_required)}) were not required in the approved snapshot."
        )
    return "traveler", "none", f"The disputed approved requirements ({', '.join(disputed)}) passed the recorded checks."


def build_packet(
    purchase: Any,
    dispute_claim: str,
    decision: Decision,
    req: ApprovedRequirements,
    offer: FlightOffer,
    exceptions: list[ExceptionAcceptance],
    narrative: str | None = None,
) -> EvidencePacket:
    """Keep recommendations deterministic and source snapshots independent of callers."""
    if not isinstance(dispute_claim, str):
        raise TypeError("dispute_claim must be text")
    if narrative is not None and not isinstance(narrative, str):
        raise TypeError("narrative must be display-only text or None")
    purchase_id = _validate_records(purchase, decision, req, offer)
    matching = _matching_exceptions(purchase, decision, req, exceptions)
    responsibility, reason_code, rationale = _recommendation(dispute_claim, decision, req, matching)
    rationale += (
        " Recommendations and prototype reason codes are advisory; final decision belongs to the dispute analyst."
        " Exceptions are unsigned application records, not new VI authorizations."
    )
    return EvidencePacket(
        purchase_id=purchase_id,
        dispute_claim=dispute_claim,
        vi_chain_valid=decision.vi_chain_valid,
        merchant_signature_valid=decision.merchant_signature_valid,
        approved_requirements=req.model_copy(deep=True),
        merchant_offer=offer.model_copy(deep=True),
        checks=[check.model_copy(deep=True) for check in decision.checks],
        exceptions=matching,
        suggested_reason_code=reason_code,
        recommended_responsibility=responsibility,
        rationale=rationale,
        narrative=narrative,
        final_decision="dispute analyst",
    )
