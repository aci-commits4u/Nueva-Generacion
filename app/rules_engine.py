"""Deterministic flight checks and offer-specific application consent.

Callers must supply requirements from verified L2 and the verified merchant
checkout payload. Signatures are checked by the adapter, not by this pure module.
No model explanation, source text, or shopping-agent description has authority.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
from uuid import uuid4

from app.models import ApprovedRequirements, CheckResult, Decision, ExceptionAcceptance, FlightOffer


CHECK_IDS = (
    "ORIGIN", "DESTINATION", "DATE", "DEPART_WINDOW", "ARRIVE_BY", "STOPS",
    "PRICE", "CURRENCY", "CABIN", "REFUNDABLE", "PASSENGERS",
)
MANDATORY_IDS = {"ORIGIN", "DESTINATION", "DATE", "PRICE", "CURRENCY", "PASSENGERS"}
MISSING = "Not stated"


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _money(cents: int) -> str:
    return f"${cents // 100}.{cents % 100:02d}"


def _check(check_id: str, requirement: str, value: str | None, matches: bool,
           applies: bool = True) -> CheckResult:
    if not applies:
        return CheckResult(check_id=check_id, requirement="No preference approved",
                           offer_value=value if value is not None else MISSING,
                           status="not_required", message=f"No {check_id.lower().replace('_', ' ')} preference was approved.")
    if value is None:
        status = "missing"
        message = f"The merchant offer doesn't state {check_id.lower().replace('_', ' ')}, so we can't confirm your requirement ({requirement})."
    elif matches:
        status = "pass"
        message = f"{value} matches your approved requirement: {requirement}."
    else:
        status = "fail"
        message = f"This offer has {value}; you approved {requirement}."
    return CheckResult(check_id=check_id, requirement=requirement, offer_value=value if value is not None else MISSING,
                       status=status, message=message)


def evaluate(req: ApprovedRequirements, offer: FlightOffer | None,
             vi_chain_valid: bool, merchant_signature_valid: bool) -> Decision:
    """Compare all eleven approved fields, using airport-local wall clocks.

    Integrity failures return before even reading the untrusted offer. Optional
    preferences are not invented. Missing signed fields never become defaults.
    """
    metadata = dict(decision_id=str(uuid4()), requirement_set_id=req.requirement_set_id,
                    vi_chain_valid=vi_chain_valid, merchant_signature_valid=merchant_signature_valid,
                    created_at=datetime.now(timezone.utc))
    if vi_chain_valid is not True or merchant_signature_valid is not True:
        return Decision(**metadata, offer_hash="", result="BLOCK", checks=[],
                        explanation="Purchase blocked: Verifiable Intent chain or merchant signature is invalid.")
    offer_hash = offer.offer_hash if offer is not None else ""
    if req.approved_by_traveler is not True:
        return Decision(**metadata, offer_hash=offer_hash, result="HOLD", checks=[
            CheckResult(check_id="APPROVAL", requirement="Traveler-approved requirements",
                        offer_value="Not approved", status="missing", message="Requirements not approved by traveler.")
        ], explanation="Please explicitly approve your requirements before checkout.")

    segments = offer.segments if offer is not None else []
    first, last = (segments[0], segments[-1]) if segments else (None, None)
    origin = first.from_airport if first is not None and _nonempty(first.from_airport) else None
    destination = last.to_airport if last is not None and _nonempty(last.to_airport) else None
    departure = first.depart_local if first is not None and _aware(first.depart_local) else None
    arrival = last.arrive_local if last is not None and _aware(last.arrive_local) else None
    # datetime.time() is the given airport clock, deliberately not converted to UTC.
    depart_time = departure.time().replace(tzinfo=None) if departure is not None else None
    depart_date = departure.date() if departure is not None else None
    arrival_time = arrival.time().replace(tzinfo=None) if arrival is not None else None
    stops = len(segments) - 1 if segments else None
    total = offer.total_cents if offer is not None else None
    total = total if type(total) is int and total >= 0 else None
    # Older shared models default missing merchant currency to USD; field presence
    # keeps that default from becoming authoritative. Also supports currency=None.
    currency = offer.currency if offer is not None and "currency" in offer.model_fields_set and _nonempty(offer.currency) else None
    cabin = offer.cabin if offer is not None and _nonempty(offer.cabin) else None
    refundable = offer.refundable if offer is not None else None
    refundable = refundable if type(refundable) is bool else None
    passengers = offer.passengers if offer is not None else None
    passengers = passengers if type(passengers) is int and passengers > 0 else None
    window = req.depart_window
    window_match = window is not None and depart_time is not None and window.earliest.replace(tzinfo=None) <= depart_time <= window.latest.replace(tzinfo=None)
    arrival_match = req.arrive_by is not None and arrival is not None and arrival.date() == req.depart_date and arrival_time <= req.arrive_by.replace(tzinfo=None)

    checks = [
        _check("ORIGIN", " or ".join(req.origin_airports), origin, origin in req.origin_airports),
        _check("DESTINATION", " or ".join(req.destination_airports), destination, destination in req.destination_airports),
        _check("DATE", req.depart_date.isoformat(), depart_date.isoformat() if depart_date is not None else None, depart_date == req.depart_date),
        _check("DEPART_WINDOW", f"Departure between {window.earliest.isoformat()} and {window.latest.isoformat()}" if window else "No preference approved",
               depart_time.isoformat() if depart_time is not None else None, window_match, window is not None),
        _check("ARRIVE_BY", f"Arrival on {req.depart_date.isoformat()} by {req.arrive_by.isoformat()}" if req.arrive_by is not None else "No preference approved",
               arrival.isoformat() if arrival is not None else None, arrival_match, req.arrive_by is not None),
        _check("STOPS", "Nonstop (0 connections)" if req.max_stops == 0 else f"At most {req.max_stops} connections",
               f"{stops} {'connection' if stops == 1 else 'connections'}" if stops is not None else None,
               stops is not None and req.max_stops is not None and stops <= req.max_stops, req.max_stops is not None),
        _check("PRICE", f"Total up to {_money(req.max_total_cents)} including taxes and fees", _money(total) if total is not None else None,
               total is not None and total <= req.max_total_cents),
        _check("CURRENCY", req.currency, currency, currency == req.currency),
        _check("CABIN", req.cabin or "No preference approved", cabin,
               cabin is not None and req.cabin is not None and cabin.casefold() == req.cabin.casefold(), req.cabin is not None),
        _check("REFUNDABLE", "Refundable fare", "Refundable" if refundable is True else "Non-refundable" if refundable is False else None,
               refundable is True, req.refundable_required is True),
        _check("PASSENGERS", f"{req.passengers} {'passenger' if req.passengers == 1 else 'passengers'}",
               f"{passengers} {'passenger' if passengers == 1 else 'passengers'}" if passengers is not None else None, passengers == req.passengers),
    ]
    unresolved = [check.check_id for check in checks if check.status in {"fail", "missing"}]
    return Decision(**metadata, offer_hash=offer_hash, result="HOLD" if unresolved else "PASS", checks=checks,
                    explanation=f"Specific traveler acceptance is required for: {', '.join(unresolved)}." if unresolved else "The merchant offer matches your approved requirements.")


def _statement_checks(statement: str, checks: list[CheckResult]) -> set[str]:
    """Recognize explicit consent grammars, never arbitrary chat or instructions.

    Josue's UI joins clauses with '; '. Every clause must be specific. The UI's
    offer label is display text; binding uses the separately recorded exact hash
    and decision id because the shared Decision contract has no offer_id field.
    """
    if not _nonempty(statement):
        return set()
    covered: set[str] = set()
    offer_labels: set[str] = set()
    for raw_clause in statement.split(";"):
        clause = raw_clause.strip()
        matched = False
        for check in checks:
            value, check_id = re.escape(check.offer_value), re.escape(check.check_id)
            structured = rf"I accept {check_id}: {value}\.?"
            if re.fullmatch(structured, clause, re.IGNORECASE):
                matched = True
            elif check.check_id == "STOPS" and check.status != "missing" and re.fullmatch(
                    rf"I accept {value} on this itinerary\.?", clause, re.IGNORECASE):
                matched = True
            else:
                ui_match = re.fullmatch(
                    rf"I accept {value} \({check_id}\) on offer ([A-Za-z0-9_-]+)\.?", clause, re.IGNORECASE)
                if ui_match:
                    matched = True
                    offer_labels.add(ui_match.group(1))
            if matched:
                covered.add(check.check_id)
                break
        if not matched:
            # Reject appended negations, 'OK', model claims, or injected commands.
            return set()
    return covered if len(offer_labels) <= 1 else set()


def can_purchase(decision: Decision, exceptions: list[ExceptionAcceptance]) -> tuple[bool, str, list[str]]:
    """Return (allowed, reason, uncovered ids) using only stored structured facts.

    PASS still needs intact metadata and all eleven consistent checks. HOLD is
    purchasable only with exact, timestamped application exceptions for every
    mismatch. This does not create a new signed VI mandate or prove HTTP status.
    """
    if not isinstance(decision, Decision) or not isinstance(decision.checks, list):
        return False, "Purchase refused: malformed decision.", []
    records = decision.checks
    unresolved = [check.check_id for check in records if isinstance(check, CheckResult) and check.status in {"fail", "missing"}]
    if decision.result == "BLOCK":
        return False, "Purchase blocked: credential or merchant signature invalid.", unresolved
    if any(isinstance(check, CheckResult) and check.check_id == "APPROVAL" for check in records):
        return False, "Traveler must approve the requirements; approval cannot be excepted.", unresolved
    now = datetime.now(timezone.utc)
    if (decision.vi_chain_valid is not True or decision.merchant_signature_valid is not True
            or not all(_nonempty(value) for value in [decision.offer_hash, decision.decision_id, decision.requirement_set_id])
            or not _aware(decision.created_at) or decision.created_at > now):
        return False, "Purchase refused: verified offer hash, identity, integrity, and decision time are required.", unresolved
    if (len(records) != len(CHECK_IDS)
            or not all(isinstance(check, CheckResult) for check in records)
            or {check.check_id for check in records} != set(CHECK_IDS)
            or not all(check.status in {"pass", "fail", "missing", "not_required"}
                       and _nonempty(check.requirement) and _nonempty(check.offer_value) and _nonempty(check.message)
                       and not (check.check_id in MANDATORY_IDS and check.status == "not_required")
                       for check in records)):
        return False, "Purchase refused: complete, consistent flight checks are required.", unresolved
    if decision.result == "PASS":
        if unresolved:
            return False, "Purchase refused: PASS contradicts failed or missing checks.", unresolved
        return True, "The verified merchant offer matches the approved requirements.", []
    if decision.result != "HOLD" or not unresolved:
        return False, "Purchase refused: decision result contradicts its checks.", unresolved
    bad_checks = [check for check in records if check.status in {"fail", "missing"}]
    covered: set[str] = set()
    for record in exceptions if isinstance(exceptions, list) else []:
        if (not isinstance(record, ExceptionAcceptance)
                or record.decision_id != decision.decision_id or record.offer_hash != decision.offer_hash
                or not _aware(record.accepted_at) or not decision.created_at <= record.accepted_at <= now):
            continue
        check = next((check for check in bad_checks if check.check_id == record.check_id), None)
        if (check is not None and record.accepted_value == check.offer_value
                and check.check_id in _statement_checks(record.traveler_statement, bad_checks)):
            covered.add(check.check_id)
    uncovered = [check_id for check_id in unresolved if check_id not in covered]
    if uncovered:
        return False, f"Specific traveler acceptance is required for: {', '.join(uncovered)}.", uncovered
    return True, "Every failed or missing check has a specific recorded traveler exception for this exact offer.", []
