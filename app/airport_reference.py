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
try:
    import pycountry
except ImportError:  # pragma: no cover - requirements install the ISO dataset
    pycountry = None


AIRPORTS_DATA_VERSION = "20260905"
AIRPORTS_DATA_SOURCE_URL = "https://pypi.org/project/airportsdata/"
AIRPORTS_DATA_JSON_URL = "https://pypi.org/pypi/airportsdata/json"
AIRPORTS_DATA_REPOSITORY_URL = "https://github.com/mborsetti/airportsdata"
AIRPORTS_DATA_LICENSE = "MIT"

MAX_SEARCH_RESULTS = 25
MAX_CONTEXT_RESULTS = 30
MAX_FIELD_CONTEXT_RESULTS = 16
_DEFAULT_SEARCH_LIMIT = 12

_WORD_RE = re.compile(r"\b[\w]+(?:[’'][\w]+)*\b", re.UNICODE)
# Codes are conventionally written uppercase.  Requiring that form prevents
# ordinary words such as "and" from becoming an airport just because a code
# with the same letters exists.
_IATA_RE = re.compile(r"(?<![A-Za-z0-9])([A-Z]{3})(?![A-Za-z0-9])")
_PAREN_RE = re.compile(r"\([^()]*\)")

_FIELD_ORIGIN_MARKER = re.compile(
    r"\b(?:from|depart(?:ing|ed)?(?:\s+from)?|leav(?:e|es|ed|ing)?(?:\s+from)?|"
    r"origin(?:\s+airport)?(?:\s+is)?)\b", re.I
)
_FIELD_DESTINATION_MARKER = re.compile(
    r"\b(?:to|arriv(?:e|es|ed|ing)?(?:\s+(?:at|in))?|"
    r"destination(?:\s+airport)?(?:\s+is)?)\b", re.I
)
_FIELD_ORIGIN_END = re.compile(
    r"\b(?:to|arriv(?:e|es|ing)?(?:\s+(?:at|in))?|destination(?:\s+airport)?|"
    r"on|under|below|at\s+most|up\s+to|for|with|between|via|return|round\s+trip)\b|[.;!?]",
    re.I,
)
_FIELD_DESTINATION_END = re.compile(
    r"\b(?:on|under|below|at\s+most|up\s+to|for|with|between|via|return|"
    r"round\s+trip|from|depart(?:ing)?|leave(?:s|d|ing)?)\b|[.;!?]",
    re.I,
)
_FIELD_ARROW = re.compile(r"(?:→|->|➝|⟶|—>|–>)")
_ROUTE_FILLER_WORDS = frozenset(
    {
        "a", "an", "the", "book", "find", "me", "i", "need", "want",
        "please", "flight", "flights", "fly", "trip", "travel", "from",
        "to", "arrive", "at", "in", "airport", "airports", "actually",
        "can", "could", "would", "like", "for", "my", "one", "way",
    }
)
_CONVERSATION_META_WORDS = frozenset(
    {
        "already", "gave", "given", "said", "mentioned", "told", "answered",
        "answer", "above", "before", "earlier", "previous", "prior", "that",
        "this", "what", "which", "you", "we", "it",
    }
)
_ROUTE_SIGNAL_WORDS = frozenset(
    {"book", "find", "flight", "flights", "fly", "flying", "trip", "travel", "need", "want", "depart", "leave", "origin", "destination", "arrive"}
)

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
    # A city can occur in an airport's name while the catalogue's ``city``
    # field contains the municipality.  Toronto Pearson is the useful example:
    # its record city is Mississauga, but a customer saying "Toronto" should
    # still see YYZ alongside YTZ.  Only reuse tokens that are themselves
    # represented as a catalogue city, which keeps generic name words such as
    # "international" from turning into a global airport search.
    city_tokens = {
        normalized
        for record in _catalog().values()
        for normalized in (_normalise(record["city"]),)
        if len(normalized) >= 4
        and " " not in normalized
        and normalized not in _GENERIC_NAME_PHRASES
        and normalized not in _DATE_WORDS
    }
    for code, record in _catalog().items():
        # Match a metro token only when it begins the public airport name.
        # This keeps "Groton-New London Airport" from contaminating the
        # exact London city group while still resolving Toronto Pearson.
        name_tokens = _normalise(record["name"]).split()
        for token in name_tokens[:1]:
            if token in city_tokens and code not in index[token]:
                index[token].append(code)
    # Common usage often shortens "London Heathrow Airport" to "Heathrow".
    # Accept only distinctive literal name tokens, never a fuzzy abbreviation
    # or a generic word such as "airport".
    for token, codes in _distinctive_name_tokens().items():
        if token in city_tokens:
            continue
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
    # Some catalogue rows use a nearby municipality in ``city`` while the
    # airport's public name contains the requested metro city (for example,
    # Toronto Pearson is catalogued under Mississauga).  Reuse only a
    # single-token city that exists as an exact catalogue city; this avoids
    # treating a word inside "Groton (New London)" as a standalone city.
    exact_city_tokens = {
        _normalise(item["city"])
        for item in _catalog().values()
        if " " not in _normalise(item["city"])
        and len(_normalise(item["city"])) >= 4
        and _normalise(item["city"]) not in _GENERIC_NAME_PHRASES
    }
    name_tokens = set(_normalise(record["name"]).split())
    return any(
        token in exact_city_tokens and _phrase_in_text(token, quote)
        for token in name_tokens
    ) or any(
        _phrase_in_text(token, quote)
        for token, codes in _distinctive_name_tokens().items()
        if canonical in codes
    )


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
    # Full state names are ordinary case-insensitive words.  Two-letter
    # abbreviations require an uppercase token so common words such as ``me``
    # (the pronoun) and ``or`` cannot silently turn a request into regional
    # airport context.  The previous lowercased scan treated "Book me ..."
    # as Maine and injected AUG/BGR/BHB/CAR into unrelated requests.
    normalized = _normalise(text)
    full_names = {
        alias: code
        for alias, code in _US_STATE_ALIASES.items()
        if len(alias) > 2
    }
    for alias, code in sorted(full_names.items(), key=lambda item: (-len(item[0]), item[0])):
        if re.search(rf"(?<![\w]){re.escape(alias)}(?![\w])", normalized):
            return code
    for match in re.finditer(r"(?<![A-Za-z0-9])([A-Z]{2})(?![A-Za-z0-9])", text):
        code = _US_STATE_ALIASES.get(match.group(1).casefold())
        if code:
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

    # Include airport names whose distinctive location token was supplied as
    # a city word.  The exact city/name index above keeps this bounded and
    # prevents words such as "airport" or "international" from matching the
    # entire catalogue.  This also makes Toronto resolve to both YTZ and YYZ
    # instead of leaking one airport through model-side guessing.
    for token in source_tokens:
        if len(token) < 4 or token in _GENERIC_NAME_TOKENS or token in _DATE_WORDS:
            continue
        for code in _place_index().get(token, ()):
            add(code)

    state_code = _state_code_in_text(text)
    if state_code:
        for code in _region_context(text, state_code):
            add(code)

    return [dict(records[code]) for code in ordered_codes[:limit]]


def airport_field_scope(text: str, field: str) -> str:
    """Return the route clause belonging to one airport field.

    This is a lexical boundary helper, not an intent decision.  It lets a
    caller inspect ``London`` for ``origin_airports`` and ``Toronto`` for
    ``destination_airports`` in a sentence such as ``from London to Toronto``.
    If the text is a standalone airport answer, it is returned unchanged.
    """
    if field not in {"origin_airports", "destination_airports"}:
        raise ValueError("field must be origin_airports or destination_airports")
    if not isinstance(text, str) or not text.strip():
        return text
    text = text.strip()

    # Conversation state is serialized as newline-separated customer turns.
    # Prefer the newest clause that explicitly addresses this endpoint. A
    # departure correction must not erase the earlier arrival route, and an
    # arrival correction must not recycle itself as a departure.
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 1:
        for line in reversed(lines):
            scoped = _airport_field_scope_clause(line, field, allow_compact=False)
            if scoped is not None:
                return scoped

    scoped = _airport_field_scope_clause(text, field, allow_compact=True)
    if scoped is not None:
        return scoped
    # The text explicitly addresses the opposite endpoint; do not recycle it
    # as a suggestion for this field.  A completely marker-free standalone
    # airport answer remains available to the caller unchanged.
    if _FIELD_ORIGIN_MARKER.search(text) or _FIELD_DESTINATION_MARKER.search(text):
        return ""
    return text


def _airport_field_scope_clause(text: str, field: str, *, allow_compact: bool) -> str | None:
    """Scope one route clause, returning ``None`` when it addresses neither endpoint."""
    # A short arrow route is a first-class route expression.  Handle it before
    # generic ``to`` matching so prose such as ``I want to go to Toronto`` does
    # not leave the earlier ``to`` as the destination marker.
    arrow = _FIELD_ARROW.search(text)
    if arrow:
        before = text[:arrow.start()].strip(" \t,:-")
        after = text[arrow.end():]
        end_match = _FIELD_DESTINATION_END.search(after)
        if end_match:
            after = after[:end_match.start()]
        after = after.strip(" \t,:-")
        if field == "origin_airports":
            return _trim_route_scope(before) if before and _route_prefix_is_plausible(before) else None
        return _trim_route_scope(after) if after else None

    origin_matches = list(_FIELD_ORIGIN_MARKER.finditer(text))
    destination_matches = list(_FIELD_DESTINATION_MARKER.finditer(text))
    # The final directional marker is the endpoint marker in natural language
    # such as ``I want to go to Toronto from London`` (the first ``to`` is
    # ordinary prose).  Explicit ``arrive``/``destination`` markers naturally
    # win because they occur at the endpoint too.
    origin = origin_matches[-1] if origin_matches else None
    destination = destination_matches[-1] if destination_matches else None

    def plausible_prefix(prefix: str, *, compact: bool = False) -> bool:
        return _route_prefix_is_plausible(prefix, compact=compact)

    if field == "origin_airports" and origin:
        end_match = _FIELD_ORIGIN_END.search(text, origin.end())
        end = end_match.start() if end_match else len(text)
        scoped = _trim_route_scope(text[origin.end():end])
        marker = text[origin.start():origin.end()].casefold()
        prefix = text[:origin.start()]
        if marker == "from" and not destination and prefix.strip() and not plausible_prefix(prefix):
            return None
        return scoped or text
    if field == "destination_airports" and destination:
        end_match = _FIELD_DESTINATION_END.search(text, destination.end())
        end = end_match.start() if end_match else len(text)
        scoped = _trim_route_scope(text[destination.end():end])
        marker = text[destination.start():destination.end()].casefold()
        prefix = text[:destination.start()]
        if marker == "to" and not origin and not plausible_prefix(prefix, compact=True):
            return None
        return scoped or text
    if destination:
        if field == "origin_airports":
            scoped = _trim_route_scope(text[:destination.start()])
            # "Arrive at MCO" has no origin clause.  An empty result tells a
            # caller that this field has no evidence instead of recycling the
            # destination airport as an origin suggestion.
            return scoped if plausible_prefix(scoped, compact=True) else None
        else:
            end_match = _FIELD_DESTINATION_END.search(text, destination.end())
            end = end_match.start() if end_match else len(text)
            scoped = _trim_route_scope(text[destination.end():end])
        return scoped or None
    if origin and field == "destination_airports":
        # The converse case: a departure-only answer is not destination
        # evidence.
        return None
    if origin or destination:
        return None
    return text if allow_compact else None


def _trim_route_scope(value: str) -> str:
    """Remove route punctuation and conjunctions left before a marker."""
    value = value.strip(" \t,:-")
    # ``leaving London and arriving Toronto`` leaves ``and`` immediately
    # before the arrival marker.  It is grammar, not part of the place.
    while re.search(r"\s+(?:and|then)\s*$", value, re.I):
        value = re.sub(r"\s+(?:and|then)\s*$", "", value, flags=re.I)
    return value.strip(" \t,:-")


def _route_prefix_is_plausible(prefix: str, *, compact: bool = True) -> bool:
    tokens = _normalise(prefix).split()
    if any(token in _CONVERSATION_META_WORDS for token in tokens):
        return False
    if not tokens:
        return compact
    if any(token in _ROUTE_SIGNAL_WORDS for token in tokens):
        return True
    # A compact ``London to Toronto`` route has a place token before the
    # marker and no route verb.  A bare ``to`` in conversational prose does
    # not get this latitude unless this is the compact route form.
    return compact and any(token not in _ROUTE_FILLER_WORDS for token in tokens)


def _place_codes_from_scope(scope: str) -> list[str]:
    """Collect exact city/name candidates from a short route scope."""
    candidates = list(codes_for_place(scope))
    if candidates:
        return candidates
    # A scoped phrase may combine a broad city with a distinctive airport
    # name, e.g. ``London Heathrow`` or ``Toronto Pearson``.  Prefer a unique
    # name token over the city's whole metro set so a customer naming an
    # airport is not forced through a city-level ambiguity question.
    distinctive: list[str] = []
    for token in _normalise(scope).split():
        if len(token) < 4 or token in _GENERIC_NAME_TOKENS or token in _DATE_WORDS:
            continue
        token_codes = codes_for_place(token)
        if len(token_codes) == 1:
            distinctive.extend(token_codes)
    if distinctive:
        return list(dict.fromkeys(distinctive))
    for token in _normalise(scope).split():
        if len(token) < 4 or token in _GENERIC_NAME_TOKENS or token in _DATE_WORDS:
            continue
        candidates.extend(codes_for_place(token))
    return list(dict.fromkeys(candidates))


@lru_cache(maxsize=1)
def _iso_country_aliases() -> dict[str, str]:
    """Map ISO country names and alpha codes to canonical alpha-2 values."""
    aliases: dict[str, str] = {}
    if pycountry is not None:
        for country in pycountry.countries:
            code = str(getattr(country, "alpha_2", "") or "").upper()
            if not re.fullmatch(r"[A-Z]{2}", code):
                continue
            for field in ("name", "official_name", "common_name", "alpha_2", "alpha_3"):
                value = getattr(country, field, None)
                if isinstance(value, str) and value.strip():
                    aliases[_normalise(value)] = code
    # UK is the common travel abbreviation; ISO assigns GB as its alpha-2
    # code.  The rest of the map comes from pycountry rather than a city list.
    aliases.setdefault("uk", "GB")
    aliases.setdefault("u k", "GB")
    return aliases


def _explicit_geography_filters(scope: str, candidates: list[str]) -> tuple[set[str], set[str], bool]:
    """Extract explicit country/region qualifiers from a short place scope.

    The boolean records whether a qualifier-like token was present but could
    not be resolved.  That distinction prevents the unqualified-city ranking
    heuristic from silently choosing the largest country group for a misspelt
    or unknown qualifier.
    """
    normalized = _normalise(scope)
    countries: set[str] = set()
    for alias, code in _iso_country_aliases().items():
        # Short ISO alpha codes must retain their conventional uppercase
        # spelling.  Matching lower-case ``to``/``in``/``us`` would turn route
        # grammar into Tonga/India/United States qualifiers.
        if len(alias) <= 3:
            if re.search(rf"(?<![A-Za-z0-9]){re.escape(alias.upper())}(?![A-Za-z0-9])", scope):
                countries.add(code)
        elif re.search(rf"(?<![\w]){re.escape(alias)}(?![\w])", normalized):
            countries.add(code)

    suffix = re.search(r"(?:,|;|\()\s*([^;()]+)", scope)
    qualifier_text = suffix.group(1).strip() if suffix else ""
    candidate_cities = {
        _normalise(_catalog()[code]["city"])
        for code in candidates
        if code in _catalog() and _catalog()[code]["city"].strip()
    }
    regions = {
        _normalise(_catalog()[code]["region"])
        for code in candidates
        if code in _catalog()
        and _catalog()[code]["region"].strip()
        and (
            _normalise(_catalog()[code]["region"]) not in candidate_cities
            or (
                qualifier_text
                and re.search(
                    rf"(?<![\w]){re.escape(_normalise(_catalog()[code]['region']))}(?![\w])",
                    _normalise(qualifier_text),
                )
            )
        )
    }
    matched_regions = {
        region
        for region in regions
        if region and re.search(
            rf"(?<![\w]){re.escape(region)}(?![\w])",
            _normalise(qualifier_text) if qualifier_text else normalized,
        )
    }

    # Any comma/semicolon/parenthetical suffix after the place is an explicit
    # qualifier even when it is not in the ISO list.  For an unqualified route
    # there is no suffix and the normal dominant-city behavior remains valid.
    unresolved = bool(qualifier_text) and not countries and not matched_regions
    return countries, matched_regions, unresolved


def airport_context_for_field(
    text: str,
    field: str,
    limit: int = MAX_FIELD_CONTEXT_RESULTS,
) -> list[dict[str, str]]:
    """Return bounded, field-scoped airport identity suggestions.

    Suggestions are reference identities only.  Explicit IATA codes remain
    valid as written.  For an ambiguous city, the dominant country group is
    used only when it is decisively larger than every other group; ties stay
    ambiguous and are returned together for customer choice.  This is a
    reusable catalog heuristic, rather than a city-specific allowlist.
    """
    limit = _validate_limit(limit, maximum=MAX_FIELD_CONTEXT_RESULTS)
    scope = airport_field_scope(text, field)
    if not isinstance(scope, str) or not scope.strip():
        return []
    candidates = _place_codes_from_scope(scope)
    if candidates:
        records = [_catalog()[code] for code in candidates if code in _catalog()]
        countries, regions, unresolved_qualifier = _explicit_geography_filters(scope, candidates)
        if countries or regions:
            filtered = [
                code for code in candidates
                if (
                    (not countries or _catalog()[code]["country"].upper() in countries)
                    and (not regions or _normalise(_catalog()[code]["region"]) in regions)
                )
            ]
            # A recognized qualifier that produces no catalog matches is a
            # contradiction/ambiguity, not permission to select another
            # country.  Keep the candidates visible for customer correction.
            if filtered:
                candidates = filtered
        elif not unresolved_qualifier:
            groups: defaultdict[str, list[str]] = defaultdict(list)
            for record in records:
                groups[record["country"].upper()].append(record["code"])
            if len(groups) > 1:
                counts = sorted(((len(codes), country) for country, codes in groups.items()), reverse=True)
                if counts[0][0] > counts[1][0]:
                    allowed = {country for count, country in counts if count == counts[0][0]}
                    candidates = [code for code in candidates if _catalog()[code]["country"].upper() in allowed]
    if candidates:
        return [dict(_catalog()[code]) for code in candidates[:limit]]
    return airport_context(scope, limit=limit)

