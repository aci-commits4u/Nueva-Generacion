"""Small, deterministic helpers for grounding natural-language dates.

This module intentionally answers a narrow question: *what dates does this
quoted customer phrase name when paired with a trusted message date?*  It does
not inspect a whole conversation, infer a destination, or decide whether an
offer passes.  Callers should keep the returned value source-linked and leave
``None`` as a clarification when the phrase is too soft or underspecified.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import re
from typing import Iterable


_MONTHS = {
    name.casefold(): number
    for number, name in enumerate(
        (
            "",
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        )
    )
    if name
}
_MONTHS.update({name[:3].casefold(): number for name, number in list(_MONTHS.items())})
_MONTHS["sept"] = 9
_MONTH_PATTERN = (
    r"January|February|March|April|May|June|July|August|September|October|"
    r"November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)
_YEAR_PATTERN = r"(?:19|20)\d{2}"
_DATE_WORD = rf"(?P<month>{_MONTH_PATTERN})\.?\s+(?P<day>\d{{1,2}})"
_ORDINAL = r"(?:st|nd|rd|th)?"
_DATE_TOKEN = rf"{_DATE_WORD}{_ORDINAL}(?:\s*,?\s*(?P<year>{_YEAR_PATTERN}))?"
_NATURAL_DATE = re.compile(rf"(?i)\b{_DATE_TOKEN}\b")
_ISO_DATE = re.compile(rf"\b(?P<iso>{_YEAR_PATTERN}-\d{{1,2}}-\d{{1,2}})\b")
_NATURAL_TOKEN_TEXT = (
    rf"(?:{_MONTH_PATTERN})\.?\s+\d{{1,2}}{_ORDINAL}"
    rf"(?:\s*,?\s*{_YEAR_PATTERN})?"
)
_NATURAL_RANGE_SPAN = re.compile(
    rf"(?i)\b(?:between\s+)?{_NATURAL_TOKEN_TEXT}\s*"
    rf"(?:through|to|-)\s*(?:(?:{_MONTH_PATTERN})\.?\s+)?"
    rf"\d{{1,2}}{_ORDINAL}(?:\s*,?\s*{_YEAR_PATTERN})?\b"
)
_NATURAL_BETWEEN_SPAN = re.compile(
    rf"(?i)\bbetween\s+{_NATURAL_TOKEN_TEXT}\s+and\s+"
    rf"(?:(?:{_MONTH_PATTERN})\.?\s+)?\d{{1,2}}{_ORDINAL}"
    rf"(?:\s*,?\s*{_YEAR_PATTERN})?\b"
)
_NATURAL_DISCRETE_SPAN = re.compile(
    rf"(?i)\b{_NATURAL_TOKEN_TEXT}(?:\s+or\s+"
    rf"(?:(?:{_MONTH_PATTERN})\.?\s+)?\d{{1,2}}{_ORDINAL}"
    rf"(?:\s*,?\s*{_YEAR_PATTERN})?\b)+"
)
_ISO_TOKEN_TEXT = rf"{_YEAR_PATTERN}-\d{{1,2}}-\d{{1,2}}"
_ISO_RANGE_SPAN = re.compile(
    rf"(?i)\b(?:between\s+)?{_ISO_TOKEN_TEXT}\s*"
    rf"(?:through|to|-)\s*{_ISO_TOKEN_TEXT}\b"
)
_ISO_BETWEEN_SPAN = re.compile(
    rf"(?i)\bbetween\s+{_ISO_TOKEN_TEXT}\s+and\s+{_ISO_TOKEN_TEXT}\b"
)
_ISO_DISCRETE_SPAN = re.compile(
    rf"(?i)\b{_ISO_TOKEN_TEXT}(?:\s*(?:or|,)\s*{_ISO_TOKEN_TEXT})+\b"
)
_NUMERIC_DATE = re.compile(
    rf"\b(?P<a>\d{{1,2}})/(?P<b>\d{{1,2}})/(?P<year>{_YEAR_PATTERN})\b"
)
_CLOCK_TOKEN = re.compile(
    r"(?ix)(?<!\d)(?:"
    r"(?P<hour12>0?[1-9]|1[0-2])(?:\:(?P<minute12>[0-5][0-9]))?\s*"
    r"(?P<meridiem>[ap]\s*\.??\s*m\s*\.?)"
    r"|"
    r"(?P<hour24>0?[0-9]|1[0-9]|2[0-3]):(?P<minute24>[0-5][0-9])"
    r"(?!\s*[ap]\s*\.?\s*m\s*\.?)"
    r")(?!(?:\d|[A-Za-z]))"
)

# A date phrase marked as soft/approximate is useful review context but is not
# safe enough to turn into a hard date.  This check runs before parsing so
# phrases such as "preferably Oct 14" never become a false requirement.
_SOFT_OR_NEGATED = re.compile(
    r"(?i)\b(?:not|no|never|preferably|prefer|maybe|perhaps|about|around|"
    r"approximately|approx\.?|roughly|early|late|mid(?:-|\s+)month)\b"
)


@dataclass(frozen=True)
class _DatePart:
    month: int
    day: int
    year: int | None


def _normalize_quote(value: str) -> str:
    """Normalize punctuation that has the same date-range role."""

    return (
        value.translate(
            str.maketrans(
                {
                    "\u2010": "-",
                    "\u2011": "-",
                    "\u2012": "-",
                    "\u2013": "-",
                    "\u2014": "-",
                    "\u2015": "-",
                    "\u2212": "-",
                    "\u00a0": " ",
                    "\u2009": " ",
                    "\u202f": " ",
                }
            )
        )
        .strip()
    )


def _reference(value: str | date | None) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _part(month: str, day: str, year: str | None) -> _DatePart | None:
    month_number = _MONTHS.get(month.casefold())
    if month_number is None:
        return None
    try:
        day_number = int(day)
        year_number = int(year) if year else None
        # Use a leap-safe placeholder when the year is not supplied.  February
        # 29 remains valid until a trusted year can be selected below.
        date(year_number or 2000, month_number, day_number)
    except (TypeError, ValueError):
        return None
    return _DatePart(month_number, day_number, year_number)


def _numeric_to_date(match: re.Match[str]) -> date | None:
    """Parse only an unambiguous slash date; never choose a locale silently."""

    try:
        first = int(match.group("a"))
        second = int(match.group("b"))
        year = int(match.group("year"))
        if first > 12 and second <= 12:
            return date(year, second, first)
        if second > 12 and first <= 12:
            return date(year, first, second)
    except (TypeError, ValueError):
        return None
    return None


def extract_clock_times(quote: str) -> list[str]:
    """Return canonical ``HH:MM`` times explicitly written in a quote.

    Both machine-style ``20:00`` and human-style ``8 p.m.`` are accepted. A
    bare number is deliberately ignored so dates and prices cannot become
    times by accident.
    """

    if not isinstance(quote, str) or not quote.strip() or len(quote) > 500:
        return []
    result: list[str] = []
    for match in _CLOCK_TOKEN.finditer(quote):
        if match.group("hour24") is not None:
            hour = int(match.group("hour24"))
            minute = int(match.group("minute24"))
        else:
            hour = int(match.group("hour12"))
            minute = int(match.group("minute12") or "00")
            if match.group("meridiem").casefold().replace(" ", "").replace(".", "") == "pm" and hour != 12:
                hour += 12
            elif match.group("meridiem").casefold().replace(" ", "").replace(".", "") == "am" and hour == 12:
                hour = 0
        normalized = f"{hour:02d}:{minute:02d}"
        if normalized not in result:
            result.append(normalized)
    return result


def clock_time_in_quote(value: str, quote: str) -> bool:
    """Check whether a canonical ``HH:MM`` requirement is source-grounded."""

    if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        return False
    return value in extract_clock_times(quote)


def _iso(value: date) -> str:
    return value.isoformat()


def _date_for_part(part: _DatePart, anchor: date | None) -> date | None:
    """Resolve one yearless date to its next occurrence from ``anchor``."""

    if part.year is not None:
        try:
            return date(part.year, part.month, part.day)
        except ValueError:
            return None
    if anchor is None:
        return None
    year = anchor.year
    try:
        candidate = date(year, part.month, part.day)
    except ValueError:
        # Feb 29 has no occurrence in a non-leap year.  Pick the next leap
        # year rather than silently changing the customer's date.
        candidate = None
        while candidate is None and year <= anchor.year + 8:
            year += 1
            try:
                candidate = date(year, part.month, part.day)
            except ValueError:
                continue
        if candidate is None:
            return None
    if candidate < anchor:
        try:
            return date(year + 1, part.month, part.day)
        except ValueError:
            year += 1
            while year <= anchor.year + 8:
                try:
                    return date(year, part.month, part.day)
                except ValueError:
                    year += 1
    return candidate


def _range_dates(first: _DatePart, second: _DatePart, anchor: date | None) -> tuple[date, date] | None:
    """Resolve a range, sharing a year and handling a calendar-year wrap."""

    if first.year is not None:
        start = _date_for_part(first, anchor)
        if start is None:
            return None
        if second.year is not None:
            end = _date_for_part(second, anchor)
        else:
            try:
                end = date(start.year, second.month, second.day)
            except ValueError:
                return None
    elif second.year is not None:
        try:
            end = date(second.year, second.month, second.day)
        except ValueError:
            return None
        year = end.year if (first.month, first.day) <= (second.month, second.day) else end.year - 1
        try:
            start = date(year, first.month, first.day)
        except ValueError:
            return None
    else:
        if anchor is None:
            return None
        # Use the anchor year's calendar first.  A range whose *end* is still
        # behind the anchor is the next occurrence of the whole range.  This
        # prevents a request in January for "Dec 30–Jan 2" from landing in the
        # past while keeping an upcoming cross-year range intact.
        try:
            start = date(anchor.year, first.month, first.day)
            end_year = anchor.year + (1 if (second.month, second.day) < (first.month, first.day) else 0)
            end = date(end_year, second.month, second.day)
        except ValueError:
            return None
        if end < anchor:
            start_year = start.year + 1
            try:
                start = date(start_year, first.month, first.day)
                end = date(start_year + (1 if (second.month, second.day) < (first.month, first.day) else 0), second.month, second.day)
            except ValueError:
                return None

    if end < start or (end - start).days > 366:
        return None
    return start, end


def _relative(quote: str, anchor: date | None) -> str | dict | None:
    if anchor is None:
        return None
    lowered = quote.casefold()
    if re.fullmatch(r"today", lowered):
        return _iso(anchor)
    if re.fullmatch(r"tomorrow", lowered):
        return _iso(anchor + timedelta(days=1))
    if re.fullmatch(r"(?:within\s+the\s+next\s+week|within\s+the\s+next\s+7\s+days|next\s+7\s+days)", lowered):
        return {"start": _iso(anchor + timedelta(days=1)), "end": _iso(anchor + timedelta(days=7))}
    if re.fullmatch(r"next\s+week", lowered):
        next_monday = anchor - timedelta(days=anchor.weekday()) + timedelta(days=7)
        return {"start": _iso(next_monday), "end": _iso(next_monday + timedelta(days=6))}
    weekdays = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    match = re.fullmatch(r"(next|this)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)", lowered)
    if match:
        offset = (weekdays[match.group(2)] - anchor.weekday()) % 7
        if match.group(1) == "next" and offset == 0:
            offset = 7
        return _iso(anchor + timedelta(days=offset))
    return None


def _parse_range(quote: str) -> tuple[_DatePart, _DatePart] | None:
    # The second endpoint may omit its month/year: "Nov 7–10".  The optional
    # comma before a shared year is accepted for "Nov 7–10, 2026".
    pattern = re.compile(
        rf"(?i)\b(?P<m1>{_MONTH_PATTERN})\.?\s+(?P<d1>\d{{1,2}}){_ORDINAL}"
        rf"(?:\s*,?\s*(?P<y1>{_YEAR_PATTERN}))?\s*"
        rf"(?:through|to|-)\s*"
        rf"(?:(?P<m2>{_MONTH_PATTERN})\.?\s+)?(?P<d2>\d{{1,2}}){_ORDINAL}"
        rf"(?:\s*,?\s*(?P<y2>{_YEAR_PATTERN}))?\b"
    )
    match = pattern.search(quote)
    if match:
        month2 = match.group("m2") or match.group("m1")
        first = _part(match.group("m1"), match.group("d1"), match.group("y1"))
        second = _part(month2, match.group("d2"), match.group("y2") or match.group("y1"))
        return (first, second) if first and second else None
    between = re.compile(
        rf"(?i)\bbetween\s+(?P<m1>{_MONTH_PATTERN})\.?\s+(?P<d1>\d{{1,2}}){_ORDINAL}"
        rf"(?:\s*,?\s*(?P<y1>{_YEAR_PATTERN}))?\s+and\s+"
        rf"(?:(?P<m2>{_MONTH_PATTERN})\.?\s+)?(?P<d2>\d{{1,2}}){_ORDINAL}"
        rf"(?:\s*,?\s*(?P<y2>{_YEAR_PATTERN}))?\b"
    ).search(quote)
    if not between:
        return None
    month2 = between.group("m2") or between.group("m1")
    first = _part(between.group("m1"), between.group("d1"), between.group("y1"))
    second = _part(month2, between.group("d2"), between.group("y2") or between.group("y1"))
    return (first, second) if first and second else None


def _parse_discrete(quote: str) -> list[_DatePart] | None:
    """Parse ``Oct 14 or 21`` and bounded chains such as ``Oct 14 or 21 or 28``."""

    first_match = _NATURAL_DATE.search(quote)
    if not first_match:
        return None
    first = _part(first_match.group("month"), first_match.group("day"), first_match.group("year"))
    if first is None:
        return None
    values = [first]
    inherited_month = first_match.group("month")
    inherited_year = first_match.group("year")
    continuation = re.compile(
        rf"(?i)^\s+or\s+(?:(?P<month>{_MONTH_PATTERN})\.?\s+)?"
        rf"(?P<day>\d{{1,2}}){_ORDINAL}"
        rf"(?:\s*,?\s*(?P<year>{_YEAR_PATTERN}))?\b"
    )
    remainder = quote[first_match.end():]
    while len(values) < 20:
        match = continuation.match(remainder)
        if not match:
            break
        month = match.group("month") or inherited_month
        year = match.group("year") or inherited_year
        parsed = _part(month, match.group("day"), year)
        if parsed is None:
            return None
        values.append(parsed)
        inherited_month = month
        inherited_year = year
        remainder = remainder[match.end():]
    return values if len(values) > 1 and not remainder.strip(" \t.,!?") else None


def resolve_date_choice(quote: str, reference_date: str | date | None = None) -> str | dict | None:
    """Resolve one quoted date phrase into a bounded, source-linked value.

    ``reference_date`` is a trusted calendar anchor, normally the customer's
    local calendar date on the message that supplied ``quote``.  Without it,
    only explicit yearful dates can be resolved.  Ranges are capped at 366
    days and discrete alternatives at 20 entries to keep this helper
    predictable.
    """

    if not isinstance(quote, str) or not quote.strip() or len(quote) > 500:
        return None
    text = _normalize_quote(quote)
    if _SOFT_OR_NEGATED.search(text):
        return None
    anchor = _reference(reference_date)

    relative = _relative(text, anchor)
    if relative is not None:
        return relative

    iso_matches = list(_ISO_DATE.finditer(text))
    if len(iso_matches) == 1 and not _NATURAL_DATE.search(text):
        try:
            return _iso(date.fromisoformat(iso_matches[0].group("iso")))
        except ValueError:
            return None
    if len(iso_matches) > 1:
        parsed = []
        for item in iso_matches:
            try:
                parsed.append(date.fromisoformat(item.group("iso")))
            except ValueError:
                return None
        gaps = [
            text[left.end():right.start()]
            for left, right in zip(iso_matches, iso_matches[1:])
        ]
        prefix = text[:iso_matches[0].start()]
        between = gaps[0] if gaps else ""
        explicit_between = bool(
            re.search(r"(?i)\bbetween\b", prefix)
            and re.search(r"(?i)\band\b", between)
        )
        explicit_range = len(parsed) == 2 and bool(
            re.search(r"(?i)\b(?:through|to)\b|(?<!\d)-(?!\d)", between)
        )
        if len(parsed) == 2 and (explicit_range or explicit_between):
            start, end = parsed
            if end < start or (end - start).days > 366:
                return None
            return {"start": _iso(start), "end": _iso(end)}
        comma_or_list = len(parsed) <= 20 and all(
            re.fullmatch(r"(?i)\s*(?:,|or)\s*", gap) for gap in gaps
        )
        if comma_or_list:
            return {"dates": [_iso(item) for item in parsed]}
        return None

    numeric_matches = list(_NUMERIC_DATE.finditer(text))
    if len(numeric_matches) == 1 and not _NATURAL_DATE.search(text):
        numeric = _numeric_to_date(numeric_matches[0])
        return _iso(numeric) if numeric else None

    date_range = _parse_range(text)
    if date_range:
        resolved = _range_dates(*date_range, anchor)
        if resolved is None:
            return None
        return {"start": _iso(resolved[0]), "end": _iso(resolved[1])}

    discrete = _parse_discrete(text)
    if discrete:
        values: list[str] = []
        for part in discrete[:20]:
            resolved = _date_for_part(part, anchor)
            if resolved is None:
                return None
            if _iso(resolved) not in values:
                values.append(_iso(resolved))
        return {"dates": values[:20]} if values else None

    natural = list(_NATURAL_DATE.finditer(text))
    if len(natural) != 1:
        return None
    match = natural[0]
    part = _part(match.group("month"), match.group("day"), match.group("year"))
    if part is None:
        return None
    resolved = _date_for_part(part, anchor)
    return _iso(resolved) if resolved else None


def _quote_occurrences(quote: str, customer_text: str) -> list[tuple[int, int]]:
    """Find quote spans after the same punctuation normalization used by parsing."""

    haystack = _normalize_quote(customer_text).casefold()
    needle = _normalize_quote(quote).strip().casefold()
    if not needle:
        return []
    spans: list[tuple[int, int]] = []
    start = 0
    while True:
        found = haystack.find(needle, start)
        if found < 0:
            return spans
        spans.append((found, found + len(needle)))
        start = found + 1


def _span_contains(span: tuple[int, int], occurrence: tuple[int, int]) -> bool:
    return span[0] <= occurrence[0] and span[1] >= occurrence[1]


def expand_date_quote(quote: str, customer_text: str) -> str | None:
    """Expand a short model quote to one unique date phrase from source text.

    A model may quote only ``Oct 14th`` even though the customer wrote
    ``Oct 14th through Oct 21st``.  This returns the smallest actual range or
    alternatives span containing that quote.  It never invents source text and
    returns ``None`` when multiple source occurrences are ambiguous.
    """

    if (
        not isinstance(quote, str)
        or not isinstance(customer_text, str)
        or not quote.strip()
        or not customer_text.strip()
        or len(quote) > 250
    ):
        return None
    if _SOFT_OR_NEGATED.search(_normalize_quote(quote)):
        return None
    occurrences = _quote_occurrences(quote, customer_text)
    if not occurrences:
        return None
    normalized_source = _normalize_quote(customer_text)
    expanded_patterns = (
        _NATURAL_BETWEEN_SPAN,
        _NATURAL_RANGE_SPAN,
        _NATURAL_DISCRETE_SPAN,
        _ISO_BETWEEN_SPAN,
        _ISO_RANGE_SPAN,
        _ISO_DISCRETE_SPAN,
    )
    expanded: set[tuple[int, int]] = set()
    for pattern in expanded_patterns:
        for match in pattern.finditer(normalized_source):
            candidate = match.span()
            if any(_span_contains(candidate, occurrence) for occurrence in occurrences):
                expanded.add(candidate)

    # A unique containing range wins over its standalone endpoint. Two
    # different containing ranges remain ambiguous and are rejected.
    if len(expanded) == 1:
        start, end = next(iter(expanded))
        return customer_text[start:end]
    if len(expanded) > 1:
        return None

    standalone_patterns = (_NATURAL_DATE, _ISO_DATE, _NUMERIC_DATE)
    standalone: set[tuple[int, int]] = set()
    for pattern in standalone_patterns:
        for match in pattern.finditer(normalized_source):
            candidate = match.span()
            if any(_span_contains(candidate, occurrence) for occurrence in occurrences):
                standalone.add(candidate)
    if len(standalone) != 1:
        return None
    start, end = next(iter(standalone))
    return customer_text[start:end]


def _timestamp_date(value: object) -> tuple[datetime, str] | None:
    if not isinstance(value, str):
        return None
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        return None
    return parsed, parsed.date().isoformat()


def reference_for_quote(quote: str, messages: Iterable[dict] | None) -> str | None:
    """Return the most recent trusted message date containing an exact quote.

    Only customer/user messages are eligible.  A valid local ``reference_date``
    wins; otherwise the UTC date from an ISO timestamp is used. Assistant
    questions, including interface wording stored in ``reply_to``, never
    provide an anchor.
    """

    if not isinstance(quote, str) or not quote.strip() or not messages:
        return None
    wanted = quote.strip().casefold()
    matches: list[tuple[datetime, int, str]] = []
    for index, message in enumerate(messages):
        if not isinstance(message, dict) or message.get("role") not in {"user", "customer"}:
            continue
        content = message.get("content")
        if not isinstance(content, str) or wanted not in content.casefold():
            continue
        stamp = _timestamp_date(message.get("timestamp"))
        if stamp is None:
            continue
        parsed, day = stamp
        trusted_reference = _reference(message.get("reference_date"))
        matches.append((parsed, index, _iso(trusted_reference) if trusted_reference else day))
    if not matches:
        return None
    return max(matches, key=lambda item: (item[0], item[1]))[2]

