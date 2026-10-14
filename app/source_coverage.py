"""Bounded literal coverage checks for the latest adaptive customer turn.

This module does not interpret a literal as a booking value.  It only detects
explicit money/date tokens in the verified latest customer message and checks
whether the grounded output keeps the same source-backed identity visible.
Unrepresented literals are retained as exact customer clauses so the review
gate cannot lose them between the two model roles.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import re
from typing import Any

from app.adaptive_intent import source_quote_is_customer


MAX_COVERAGE_FLAGS = 20
MAX_COVERAGE_BYTES = 6000

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2,
    "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}
_MONTH_PATTERN = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
    r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
_NATURAL_DATE = re.compile(
    rf"(?P<month>{_MONTH_PATTERN})\.?\s+"
    r"(?P<day>\d{1,2})(?:st|nd|rd|th)?"
    r"(?:,?\s+(?P<year>(?:19|20)\d{2}))?",
    re.IGNORECASE,
)
_ISO_DATE = re.compile(
    r"\b(?P<year>(?:19|20)\d{2})[-/](?P<month>\d{1,2})[-/](?P<day>\d{1,2})\b"
)
_CURRENCY = r"(?:USD|EUR|GBP|JPY|CNY|RMB|CAD|AUD|INR|CHF|MXN|BRL|KRW|SEK|NOK|DKK|PLN|\$|€|£|¥)"
_MONEY_PREFIX = re.compile(
    rf"(?P<currency>{_CURRENCY})\s*(?P<amount>\d(?:[\d,]*\d)?(?:\.\d{{1,2}})?)",
    re.IGNORECASE,
)
_MONEY_SUFFIX = re.compile(
    rf"(?P<amount>\d(?:[\d,]*\d)?(?:\.\d{{1,2}})?)\s*(?P<currency>{_CURRENCY})\b",
    re.IGNORECASE,
)
_UNIT_PATTERNS = (
    ("nightly", re.compile(r"(?i)(?:per\s*[-/]?\s*night|nightly|/\s*night|a\s+night|each\s+night)")),
    ("person", re.compile(r"(?i)(?:per\s*[-/]?\s*(?:person|travell?er|guest|adult)|/\s*(?:person|travell?er|guest|adult)|each\s+(?:person|travell?er|guest|adult))")),
    ("room", re.compile(r"(?i)(?:per\s*[-/]?\s*room|/\s*room|each\s+room)")),
    ("item", re.compile(r"(?i)(?:per\s*[-/]?\s*(?:item|unit)|/\s*(?:item|unit)|each\s+(?:item|unit))")),
    ("daily", re.compile(r"(?i)(?:per\s*[-/]?\s*day|daily|/\s*day|each\s+day)")),
    ("weekly", re.compile(r"(?i)(?:per\s*[-/]?\s*week|weekly|/\s*week|each\s+week)")),
    ("monthly", re.compile(r"(?i)(?:per\s*[-/]?\s*month|monthly|/\s*month|each\s+month)")),
    ("total", re.compile(r"(?i)(?:all[- ]?in|total|entire\s+(?:stay|trip|purchase)|whole\s+(?:stay|trip|purchase)|for\s+the\s+(?:stay|trip|purchase))")),
)
_OPTIONAL_DATE = re.compile(
    r"(?i)(?:option|optional|extend|extension|if\s+needed|might|may|alternative)"
)
_SUPERSEDED = re.compile(r"(?i)(?:instead\s+of|rather\s+than|replac(?:e|ed)|not)\s*$")
_CORRECTION_FROM = re.compile(
    r"(?is)\b(?:change|changed|move|moved|shift|shifted|switch|switched|"
    r"update|updated|correct|corrected|replace|replaced)\b"
    r"[^.!?;\n]{0,96}\bfrom\s*$"
)


def _currency(value: str) -> str:
    value = value.upper()
    return {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY"}.get(value, value)


def _amount(value: str) -> str:
    try:
        return format(Decimal(value.replace(",", "")).normalize(), "f")
    except (InvalidOperation, ValueError):
        return value.replace(",", "")


def _context(text: str, start: int, end: int, before: int = 64, after: int = 96) -> str:
    return text[max(0, start - before):min(len(text), end + after)]


def _clause_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    """Find a local clause without borrowing a neighboring literal's unit."""
    # A comma between a natural date's day and year is part of that date, not
    # a clause boundary (``April 3, 2027``).  Leave it available to the local
    # clause splitter so the date's neighboring conjunction can do the work.
    punctuation = []
    for index, mark in enumerate(text[:start]):
        if mark != ",":
            if mark in ".?!;\n":
                punctuation.append(index)
            continue
        if not re.match(r"\s*(?:19|20)\d{2}\b", text[index + 1:]):
            punctuation.append(index)
    left = max(punctuation) + 1 if punctuation else 0
    right_edges = []
    for index, mark in enumerate(text[end:], start=end):
        if mark != ",":
            if mark in ".?!;\n":
                right_edges.append(index)
            continue
        if not re.match(r"\s*(?:19|20)\d{2}\b", text[index + 1:]):
            right_edges.append(index)
    right = min(right_edges) if right_edges else len(text)
    # Commas inside ``April 3, 2027`` are before the literal's end and cannot
    # become a right boundary. Split conjunctions only when the next phrase
    # starts a new date/money/extension clause.
    segment = text[left:right]
    local_start, local_end = start - left, end - left
    heads = (
        r"check\s*(?:in|out)|arriv(?:e|al)|depart(?:ure)?|option|extend|"
        r"the\s+option|with\s+the\s+option|(?:USD|EUR|GBP|JPY|CNY|RMB|CAD|AUD|INR|CHF|"
        r"MXN|BRL|KRW|SEK|NOK|DKK|PLN)|[$€£¥]|(?:19|20)\d{2}[-/]"
        rf"|{_MONTH_PATTERN}\.?\s+\d{{1,2}}"
    )
    conjunction = re.compile(rf"\s+(?:and|or|but|with)\s+(?=(?:{heads}))", re.IGNORECASE)
    base_left = left
    for match in conjunction.finditer(segment):
        if match.end() <= local_start:
            left = base_left + match.end()
        elif match.start() >= local_end:
            right = base_left + match.start()
            break
    return left, right


def _money_unit(text: str, start: int, end: int) -> str:
    left, right = _clause_bounds(text, start, end)
    context = text[left:right]
    # A phrase such as "$175 all-in nightly" must remain nightly.  Check
    # specific units before the broad all-in/total wording.
    for unit, pattern in _UNIT_PATTERNS:
        if unit == "total":
            continue
        if pattern.search(context):
            return unit
    if dict(_UNIT_PATTERNS)["total"].search(context):
        return "total"
    return "unspecified"


def _superseded(text: str, start: int) -> bool:
    context = text[max(0, start - 112):start]
    return bool(_SUPERSEDED.search(context) or _CORRECTION_FROM.search(context))


def _optional_date(text: str, start: int, end: int) -> bool:
    left, right = _clause_bounds(text, start, end)
    return bool(_OPTIONAL_DATE.search(text[left:right]))


def _valid_date(year: int | None, month: int, day: int) -> bool:
    try:
        date(year or 2000, month, day)
    except ValueError:
        return False
    return True


def _date_atom(*, start: int, end: int, month: int, day: int,
               year: int | None, optional: bool, superseded: bool) -> dict[str, Any]:
    return {
        "kind": "date",
        "start": start,
        "end": end,
        "month": month,
        "day": day,
        "year": year,
        "optional": optional,
        "superseded": superseded,
    }


def _money_atom(*, start: int, end: int, currency: str, amount: str,
                unit: str, superseded: bool) -> dict[str, Any]:
    return {
        "kind": "money",
        "start": start,
        "end": end,
        "currency": currency,
        "amount": amount,
        "unit": unit,
        "superseded": superseded,
    }


def extract_literals(text: str) -> list[dict[str, Any]]:
    """Extract bounded, identity-only date and currency literals."""
    if not isinstance(text, str) or not text:
        return []
    atoms: list[dict[str, Any]] = []
    seen_spans: set[tuple[str, int, int]] = set()
    for match in _MONEY_PREFIX.finditer(text):
        raw_currency = match.group("currency")
        amount = _amount(match.group("amount"))
        span = ("money", match.start(), match.end())
        if span in seen_spans:
            continue
        seen_spans.add(span)
        atoms.append(_money_atom(
            start=match.start(), end=match.end(), currency=_currency(raw_currency),
            amount=amount, unit=_money_unit(text, match.start(), match.end()),
            superseded=_superseded(text, match.start()),
        ))
    for match in _MONEY_SUFFIX.finditer(text):
        # A prefix match for "$175 USD" is the same literal; dedupe by the
        # normalized span identity rather than by raw text.
        start, end = match.start(), match.end()
        if any(atom["kind"] == "money" and abs(atom["start"] - start) <= 1
               and abs(atom["end"] - end) <= 5 for atom in atoms):
            continue
        atoms.append(_money_atom(
            start=start, end=end, currency=_currency(match.group("currency")),
            amount=_amount(match.group("amount")), unit=_money_unit(text, start, end),
            superseded=_superseded(text, start),
        ))
    date_spans: set[tuple[int, int]] = set()
    for match in _ISO_DATE.finditer(text):
        month, day, year = int(match.group("month")), int(match.group("day")), int(match.group("year"))
        if not 1 <= month <= 12 or not _valid_date(year, month, day):
            continue
        date_spans.add((match.start(), match.end()))
        atoms.append(_date_atom(
            start=match.start(), end=match.end(), month=month, day=day, year=year,
            optional=_optional_date(text, match.start(), match.end()),
            superseded=_superseded(text, match.start()),
        ))
    for match in _NATURAL_DATE.finditer(text):
        if any(start <= match.start() < end for start, end in date_spans):
            continue
        month = _MONTHS[match.group("month").casefold().rstrip(".")]
        day = int(match.group("day"))
        year = int(match.group("year")) if match.group("year") else None
        if not _valid_date(year, month, day):
            continue
        atoms.append(_date_atom(
            start=match.start(), end=match.end(), month=month, day=day, year=year,
            optional=_optional_date(text, match.start(), match.end()),
            superseded=_superseded(text, match.start()),
        ))
    return sorted(atoms, key=lambda item: (item["start"], item["end"], item["kind"]))


def _date_identity(atom: dict[str, Any]) -> tuple[int, int, int | None, bool]:
    return atom["month"], atom["day"], atom.get("year"), bool(atom.get("optional"))


def _money_identity(atom: dict[str, Any]) -> tuple[str, str, str]:
    return atom["currency"], atom["amount"], atom["unit"]


def _date_matches(expected: dict[str, Any], represented: dict[str, Any]) -> bool:
    if bool(expected.get("optional")) != bool(represented.get("optional")):
        return False
    if expected["month"] != represented["month"] or expected["day"] != represented["day"]:
        return False
    left_year, right_year = expected.get("year"), represented.get("year")
    return left_year is None or right_year is None or left_year == right_year


def _money_matches(expected: dict[str, Any], represented: dict[str, Any]) -> bool:
    return _money_identity(expected) == _money_identity(represented)


def _iter_quote_values(data: Any):
    if not isinstance(data, dict):
        return
    for field, value in (data.get("fields") or {}).items():
        sources = data.get("sources") or {}
        quote = sources.get(field)
        if isinstance(quote, str):
            yield quote
        if field in {"checkin_date", "checkout_date", "departure_date"} and isinstance(value, str):
            yield value
    for key in ("unsupported",):
        for value in data.get(key) or []:
            if isinstance(value, str):
                yield value
    for key in ("clarifications", "criteria", "generic_criteria"):
        values = data.get(key) or []
        if not isinstance(values, list):
            continue
        for item in values:
            if isinstance(item, dict) and isinstance(item.get("source_quote"), str):
                yield item["source_quote"]


def _represented_literals(data_groups: list[Any], source_text: str,
                          source_messages: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for data in data_groups:
        for quote in _iter_quote_values(data):
            if not source_quote_is_customer(quote, source_text, source_messages):
                continue
            result.extend(extract_literals(quote))
    return result


def _clause_for_atom(text: str, atom: dict[str, Any]) -> str:
    """Return a small exact source clause containing one literal."""
    start, end = atom["start"], atom["end"]
    left, right = _clause_bounds(text, start, end)
    if atom.get("kind") == "date" and re.search(
        r"(?i)with\s+$", text[max(0, left - 16):left]
    ):
        # ``with the option to extend ...`` is one customer clause.  The
        # conjunction splitter starts after ``with`` to keep the selected
        # date's optional flag local, so restore that exact leading word only
        # when returning the retained source phrase.
        left -= len(re.search(
            r"(?i)with\s+$", text[max(0, left - 16):left]
        ).group())
    return text[left:right].strip(" ,")


def audit_latest_turn(latest_turn: str, *, source_text: str,
                      source_messages: list[dict[str, Any]] | None,
                      current_draft: dict[str, Any] | None,
                      candidate: dict[str, Any] | None,
                      final: dict[str, Any] | None,
                      final_raw: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return exact missing clauses plus fixed-code diagnostics.

    The returned ``flags`` are customer phrases intended for the existing
    bounded unsupported merge. Diagnostics contain counts and stable codes;
    they never contain model/customer prose.
    """
    literals = extract_literals(latest_turn)
    # Candidate/final raw model proposals are deliberately excluded.  A
    # rejected profile criterion must not certify its own literal.  Generic
    # criteria emitted by the model are already merged into ``final`` as
    # source-backed unsupported conditions before this guard runs.
    represented = _represented_literals(
        [current_draft, final], source_text, source_messages,
    )
    missing: list[str] = []
    missing_money = 0
    missing_dates = 0
    for atom in literals:
        if atom.get("superseded"):
            continue
        covered = (
            any(_money_matches(atom, item) for item in represented if item["kind"] == "money")
            if atom["kind"] == "money"
            else any(_date_matches(atom, item) for item in represented if item["kind"] == "date")
        )
        if covered:
            continue
        clause = _clause_for_atom(latest_turn, atom)
        if clause and clause not in missing:
            missing.append(clause)
            if atom["kind"] == "money":
                missing_money += 1
            else:
                missing_dates += 1
    if len(missing) > MAX_COVERAGE_FLAGS or sum(len(item.encode()) for item in missing) > MAX_COVERAGE_BYTES:
        raise ValueError("Too many latest-turn literal coverage flags for a reviewable request.")
    codes = []
    if missing_money:
        codes.append("latest_turn_unrepresented_money")
    if missing_dates:
        codes.append("latest_turn_unrepresented_date")
    return {
        "flags": missing,
        "diagnostics": {
            "codes": codes,
            "money_literals": sum(item["kind"] == "money" for item in literals),
            "date_literals": sum(item["kind"] == "date" for item in literals),
            "unrepresented_money": missing_money,
            "unrepresented_dates": missing_dates,
            "flags_added": len(missing),
        },
    }
