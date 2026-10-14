"""Deterministic airport reference data for intent interpretation.

The application uses this module to turn a clearly named place into *possible*
airport records.  It never chooses one airport for an ambiguous place.  The
catalogue is supplied by the pinned :mod:`airportsdata` package and loaded
locally, so interpretation remains available when the network is unavailable.

This is reference identity data only.  It is not merchant offer data, flight
availability, or proof that an airport serves a requested itinerary.
"""

from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
import re
import unicodedata
from typing import Any

import airportsdata


AIRPORTS_DATA_VERSION = "20260905"
AIRPORTS_DATA_SOURCE_URL = "https://pypi.org/project/airportsdata/"
AIRPORTS_DATA_JSON_URL = "https://pypi.org/pypi/airportsdata/json"
AIRPORTS_DATA_REPOSITORY_URL = "https://github.com/mborsetti/airportsdata"
AIRPORTS_DATA_LICENSE = "MIT"

MAX_SEARCH_RESULTS = 25
MAX_CONTEXT_RESULTS = 30
_DEFAULT_SEARCH_LIMIT = 12

_WORD_RE = re.compile(r"\b[\w]+(?:[’'][\w]+)*\b", re.UNICODE)
# Codes are conventionally written uppercase.  Requiring that form prevents
# ordinary words such as "and" from becoming an airport just because a code
# with the same letters exists.
_IATA_RE = re.compile(r"(?<![A-Za-z0-9])([A-Z]{3})(?![A-Za-z0-9])")
_PAREN_RE = re.compile(r"\([^()]*\)")

# Generic words occur in many airport names and should not ground every airport
# merely because a customer said "airport" or "international".
_GENERIC_NAME_PHRASES = frozenset(
    {
        "airport",
        "international airport",
        "international",
        "field",
        "airfield",
        "municipal airport",
    }
)
_GENERIC_NAME_TOKENS = frozenset(
    token for phrase in _GENERIC_NAME_PHRASES for token in phrase.split()
)
_DATE_WORDS = frozenset(
    {
        "today",
        "tomorrow",
        "yesterday",
        "next",
        "previous",
        "last",
        "within",
        "week",
        "weekend",
        "day",
        "days",
        "morning",
        "afternoon",
        "evening",
        "night",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
    }
)

# This is intentionally a small ranking hint, not a source of airport truth.
# The catalogue still supplies every record and ambiguity is retained.  These
# four widely used Florida airports make a regional context useful without
# injecting the entire state's airport catalogue into an AI prompt.
_REGION_PREFERRED_CODES: dict[str, tuple[str, ...]] = {
    "FL": ("MCO", "MIA", "TPA", "FLL"),
}

# Conservative state aliases let a broad region enrich a chooser.  They do
# not authorize a single airport; airport_context() returns several records.
_US_STATE_ALIASES: dict[str, str] = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
}
_US_STATE_ALIASES.update({code.casefold(): code for code in set(_US_STATE_ALIASES.values())})


def _strip_well_formed_parentheticals(value: str) -> str:
    """Remove balanced parenthetical qualifiers without guessing malformed text."""

    if "(" not in value and ")" not in value:
        return value
    depth = 0
    for character in value:
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth < 0:
                return value
    if depth != 0:
        return value
    while _PAREN_RE.search(value):
        value = _PAREN_RE.sub(" ", value)
    return value


def _normalise(value: str) -> str:
    """Casefold and remove diacritics while keeping word boundaries stable."""

    value = _strip_well_formed_parentheticals(value)
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    without_marks = without_marks.casefold().replace("’", "'")
    # Punctuation is a separator for matching purposes.  This makes
    # "Fort Lauderdale/Hollywood" searchable without making substrings match.
    without_marks = re.sub(r"[^\w]+", " ", without_marks, flags=re.UNICODE)
    return " ".join(without_marks.split())


def _phrase_in_text(phrase: str, text: str) -> bool:
    """Return true only for a complete, contiguous normalized phrase."""

    phrase_normalised = _normalise(phrase)
    if not phrase_normalised or phrase_normalised in _GENERIC_NAME_PHRASES or phrase_normalised in _GENERIC_NAME_TOKENS:
        return False
    text_normalised = _normalise(text)
    return bool(
        re.search(
            rf"(?<![\w]){re.escape(phrase_normalised)}(?![\w])",
            text_normalised,
            flags=re.UNICODE,
        )
    )


def _clean_record(code: str, row: dict[str, Any]) -> dict[str, str]:
    return {
        "code": code,
        "name": str(row.get("name") or "").strip(),
        "city": str(row.get("city") or "").strip(),
        "region": str(row.get("subd") or "").strip(),
        "country": str(row.get("country") or "").strip(),
    }


@lru_cache(maxsize=1)
def _catalog() -> dict[str, dict[str, str]]:
    """Load the pinned IATA catalogue once per process."""

    rows = airportsdata.load("IATA")
    records: dict[str, dict[str, str]] = {}
    for raw_code, row in rows.items():
        code = str(raw_code or "").strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", code):
            continue
        record = _clean_record(code, row)
        records[code] = record
    return dict(sorted(records.items()))


@lru_cache(maxsize=1)
def _place_index() -> dict[str, tuple[str, ...]]:
    index: defaultdict[str, list[str]] = defaultdict(list)
    for code, record in _catalog().items():
        for value in (record["city"], record["name"]):
            normalized = _normalise(value)
            if normalized and code not in index[normalized]:
                index[normalized].append(code)
    # Common usage often shortens "London Heathrow Airport" to "Heathrow".
    # Accept only distinctive literal name tokens, never a fuzzy abbreviation
    # or a generic word such as "airport".
    for token, codes in _distinctive_name_tokens().items():
        index[token].extend(code for code in codes if code not in index[token])
    return {key: tuple(sorted(codes)) for key, codes in index.items()}


@lru_cache(maxsize=1)
def _distinctive_name_tokens() -> dict[str, tuple[str, ...]]:
    """Return exact, non-generic name tokens that identify one airport."""

    index: defaultdict[str, set[str]] = defaultdict(set)
    for code, record in _catalog().items():
        name = _normalise(record["name"])
        for token in name.split():
            if len(token) < 4 or token in _GENERIC_NAME_TOKENS or token in _DATE_WORDS:
                continue
            index[token].add(code)
    return {token: tuple(sorted(codes)) for token, codes in index.items() if len(codes) == 1}


@lru_cache(maxsize=1)
def _context_phrase_index() -> tuple[dict[tuple[str, ...], tuple[tuple[int, str], ...]], int]:
    """Index complete city/name phrases for token-window context matching.

    The old implementation built a regular expression for every catalogue
    phrase on every request.  This index is built once, then context matching
    performs at most ``max_phrase_length`` dictionary lookups per source token.
    """

    index: defaultdict[tuple[str, ...], set[tuple[int, str]]] = defaultdict(set)
    max_phrase_length = 1
    for code, record in _catalog().items():
        for kind, value in ((0, record["city"]), (1, record["name"])):
            normalized = _normalise(value)
            tokens = tuple(normalized.split())
            if not tokens or normalized in _GENERIC_NAME_PHRASES:
                continue
            if kind == 0 and len(normalized.replace(" ", "")) < 4:
                continue
            index[tokens].add((kind, code))
            max_phrase_length = max(max_phrase_length, len(tokens))
    for token, codes in _distinctive_name_tokens().items():
        key = (token,)
        for code in codes:
            index[key].add((1, code))
    return (
        {key: tuple(sorted(values)) for key, values in index.items()},
        max_phrase_length,
    )


def airport_records() -> dict[str, dict[str, str]]:
    """Return IATA-keyed airport identity records from the local catalogue.

    A fresh outer and inner mapping is returned so callers cannot corrupt the
    process-wide cache.  Only nonempty three-letter IATA records are exposed.
    """

    return {code: dict(record) for code, record in _catalog().items()}


def airport_record(code: str) -> dict[str, str] | None:
    """Return one small copied identity record, or ``None`` for an unknown code."""

    if not isinstance(code, str):
        return None
    record = _catalog().get(code.strip().upper())
    return dict(record) if record is not None else None


def airport_reference_metadata() -> dict[str, str]:
    """Return provenance suitable for diagnostics or an evidence packet."""

    return {
        "package": "airportsdata",
        "version": AIRPORTS_DATA_VERSION,
        "source": AIRPORTS_DATA_SOURCE_URL,
        "repository": AIRPORTS_DATA_REPOSITORY_URL,
        "license": AIRPORTS_DATA_LICENSE,
        "offline": "true",
    }


def codes_for_place(place: str) -> list[str]:
    """Return every exact city/name match, preserving ambiguity.

    This intentionally does not perform fuzzy matching or select a preferred
    airport.  A place such as London or Tokyo can therefore return multiple
    IATA codes for the customer to review.
    """

    if not isinstance(place, str) or not place.strip():
        return []
    return list(_place_index().get(_normalise(place), ()))


def quote_supports_airport(code: str, quote: str) -> bool:
    """Check whether an exact code, city, or airport-name phrase is quoted."""

    if not isinstance(code, str) or not isinstance(quote, str):
        return False
    canonical = code.strip().upper()
    record = _catalog().get(canonical)
    if record is None:
        return False
    if _IATA_RE.search(quote) and any(
        match.group(1).upper() == canonical for match in _IATA_RE.finditer(quote)
    ):
        return True
    if _phrase_in_text(record["city"], quote) or _phrase_in_text(record["name"], quote):
        return True
    return any(_phrase_in_text(token, quote) for token, codes in _distinctive_name_tokens().items() if canonical in codes)


def _validate_limit(limit: int, *, maximum: int) -> int:
    if type(limit) is not int or not 1 <= limit <= maximum:
        raise ValueError(f"limit must be an integer between 1 and {maximum}")
    return limit


def search_airports(query: str, limit: int = _DEFAULT_SEARCH_LIMIT) -> list[dict[str, str]]:
    """Search code, city, airport name, or region with deterministic ranking."""

    limit = _validate_limit(limit, maximum=MAX_SEARCH_RESULTS)
    if not isinstance(query, str) or not query.strip():
        return []
    normalized_query = _normalise(query)
    if not normalized_query:
        return []
    ranked: list[tuple[tuple[int, str], str]] = []
    for code, record in _catalog().items():
        values = {
            "code": code.casefold(),
            "name": _normalise(record["name"]),
            "city": _normalise(record["city"]),
            "region": _normalise(record["region"]),
        }
        if normalized_query not in values["code"] and not any(
            normalized_query in values[field] for field in ("name", "city", "region")
        ):
            continue
        if normalized_query == values["code"]:
            rank = 0
        elif normalized_query == values["city"]:
            rank = 1
        elif normalized_query == values["name"]:
            rank = 2
        elif values["code"].startswith(normalized_query) or any(
            values[field].startswith(normalized_query) for field in ("name", "city", "region")
        ):
            rank = 3
        elif normalized_query == values["region"]:
            rank = 4
        else:
            rank = 5
        ranked.append(((rank, code), code))
    ranked.sort()
    return [dict(_catalog()[code]) for _, code in ranked[:limit]]


def _state_code_in_text(text: str) -> str | None:
    normalized = _normalise(text)
    for alias, code in sorted(_US_STATE_ALIASES.items(), key=lambda item: (-len(item[0]), item[0])):
        if re.search(rf"(?<![\w]){re.escape(alias)}(?![\w])", normalized):
            return code
    return None


def _region_context(text: str, state_code: str) -> list[str]:
    records = _catalog()
    regional = [
        code
        for code, record in records.items()
        if record["country"].upper() == "US"
        and (
            _normalise(record["region"]) == _normalise(state_code)
            or _US_STATE_ALIASES.get(_normalise(record["region"])) == state_code
        )
    ]
    preferred = [code for code in _REGION_PREFERRED_CODES.get(state_code, ()) if code in regional]
    remaining = sorted(code for code in regional if code not in preferred)
    return (preferred + remaining)[:4]


def airport_context(text: str, limit: int = MAX_CONTEXT_RESULTS) -> list[dict[str, str]]:
    """Return bounded airport context explicitly supported by customer text.

    Explicit IATA codes win.  Then exact city/name phrases are added.  A broad
    US state can add up to four reference suggestions for a chooser, but this
    function never turns that region into a single approved airport.
    """

    limit = _validate_limit(limit, maximum=MAX_CONTEXT_RESULTS)
    if not isinstance(text, str) or not text.strip():
        return []
    records = _catalog()
    ordered_codes: list[str] = []

    def add(code: str) -> None:
        if code in records and code not in ordered_codes and len(ordered_codes) < limit:
            ordered_codes.append(code)

    for match in _IATA_RE.finditer(text):
        add(match.group(1).upper())

    source_tokens = tuple(_normalise(text).split())
    phrase_index, max_phrase_length = _context_phrase_index()
    phrases: set[tuple[int, int, str]] = set()
    for start in range(len(source_tokens)):
        max_length = min(max_phrase_length, len(source_tokens) - start)
        for phrase_length in range(max_length, 0, -1):
            key = source_tokens[start : start + phrase_length]
            for kind, code in phrase_index.get(key, ()):
                # Longer phrases are more specific; city beats an airport name
                # on equal length; code breaks any remaining tie.
                phrases.add((-len(key), kind, code))
    for _, _, code in sorted(phrases):
        add(code)

    state_code = _state_code_in_text(text)
    if state_code:
        for code in _region_context(text, state_code):
            add(code)

    return [dict(records[code]) for code in ordered_codes[:limit]]

