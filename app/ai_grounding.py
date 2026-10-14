"""Deterministic validation and source grounding for model-proposed drafts.

The model is allowed to propose language and values.  This module decides whether
those proposals are representable by a reviewed profile and whether each value is
actually supported by customer text.  It never authorizes a purchase.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import re

from app.airport_reference import (
    airport_record,
    airport_records,
    codes_for_place,
    quote_supports_airport,
)
from app.profile_registry import get_profile, validate_fields
from app.temporal import expand_date_quote, reference_for_quote, resolve_date_choice


LEGACY_KEYS = {"fields", "sources", "unsupported", "explanation"}
EXPECTED_KEYS = LEGACY_KEYS | {"clarifications"}
CLARIFICATION_REASONS = {"ambiguous", "preference", "missing"}


class EnvelopeFailure(ValueError):
    """The provider response cannot be treated as a draft envelope."""


class GroundingFailure(ValueError):
    """A typed value or quotation is not grounded in customer text."""


_AIRPORT_ALIASES = {
    "newark": ("EWR",),
    "tampa": ("TPA",),
    "orlando": ("MCO",),
    "miami": ("MIA",),
    "boston": ("BOS",),
    "los angeles": ("LAX",),
    "san francisco": ("SFO",),
}
_AMBIGUOUS_LOCATIONS = {
    "fl",
    "florida",
    "the state of florida",
    "new england",
    "the united states",
    "united states",
    "usa",
    "chicago",
    "chi",
    "new york",
    "new york city",
    "nyc",
    "washington",
}
_IATA = re.compile(r"^[A-Z]{3}$")
_MONTHS = {name.lower(): index for index, name in enumerate(
    ("", "January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December")
) if name}
_MONTHS.update({name[:3].lower(): index for name, index in _MONTHS.items()})

_CABIN_CANONICAL = {
    "basic economy": "basic_economy",
    "economy": "economy",
    "premium economy": "premium_economy",
    "business": "business",
    "first": "first",
    "first class": "first",
}
_CABIN_SOURCE_CATEGORIES = (
    ("basic economy", "basic_economy"),
    ("premium economy", "premium_economy"),
    ("economy plus", "economy_plus"),
    ("business class", "business"),
    ("first class", "first"),
    ("economy", "economy"),
    ("business", "business"),
    ("first", "first"),
)
_ONE_WAY_QUOTE = re.compile(
    r"\bone[-\u2010-\u2015 ]way\b"
    r"|\bonly\s+(?:(?:need|want|book|require)\s+)?(?:the\s+)?outbound\b"
    r"|\boutbound\s+only\b",
    re.I,
)


# Provider JSON sometimes changes typography while copying a source quote.  The
# mapping is deliberately limited to punctuation and space characters with the
# same textual role; it does not remove punctuation, collapse whitespace, or
# perform token/semantic matching.  The original customer span is restored
# after a match so review provenance remains the customer's exact wording.
_SOURCE_TYPOGRAPHY = str.maketrans({
    "\u2018": "'",  # left single quotation mark
    "\u2019": "'",  # right single quotation mark
    "\u201a": "'",  # single low-9 quotation mark
    "\u201b": "'",  # single high-reversed-9 quotation mark
    "\u201c": '"',  # left double quotation mark
    "\u201d": '"',  # right double quotation mark
    "\u201e": '"',  # double low-9 quotation mark
    "\u201f": '"',  # double high-reversed-9 quotation mark
    "\u02bc": "'",  # modifier letter apostrophe
    "\uff07": "'",  # fullwidth apostrophe
    "\u2010": "-",  # hyphen
    "\u2011": "-",  # non-breaking hyphen
    "\u2012": "-",  # figure dash
    "\u2013": "-",  # en dash
    "\u2014": "-",  # em dash
    "\u2015": "-",  # horizontal bar
    "\u2212": "-",  # minus sign used as a text dash
    "\u00a0": " ",  # no-break space
    "\u2000": " ",  # en quad
    "\u2001": " ",  # em quad
    "\u2002": " ",  # en space
    "\u2003": " ",  # em space
    "\u2004": " ",  # three-per-em space
    "\u2005": " ",  # four-per-em space
    "\u2006": " ",  # six-per-em space
    "\u2007": " ",  # figure space
    "\u2008": " ",  # punctuation space
    "\u2009": " ",  # thin space
    "\u200a": " ",  # hair space
    "\u202f": " ",  # narrow no-break space
})


def _source_span(quote: str, text: str) -> str | None:
    """Return the original text span for a typography-equivalent quote.

    Index bookkeeping is kept alongside the normalized text so callers can
    retain exact customer punctuation.  Matching still requires a contiguous
    source substring; spelling changes, paraphrases, and omitted words do not
    qualify.
    """
    if type(quote) is not str or type(text) is not str:
        return None
    normalized_quote = quote.translate(_SOURCE_TYPOGRAPHY).casefold()
    if not normalized_quote:
        return "" if quote == "" else None
    normalized_text_parts: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    for index, character in enumerate(text):
        normalized_character = character.translate(_SOURCE_TYPOGRAPHY).casefold()
        normalized_text_parts.append(normalized_character)
        starts.extend([index] * len(normalized_character))
        ends.extend([index + 1] * len(normalized_character))
    normalized_text = "".join(normalized_text_parts)
    prefix = r'(?<!\w)' if normalized_quote[0].isalnum() else ''
    suffix = r'(?!\w)' if normalized_quote[-1].isalnum() else ''
    matches = list(re.finditer(prefix + re.escape(normalized_quote) + suffix, normalized_text))
    # Prefer the exact spelling before case/typography-equivalent recovery.
    # In particular, FL must not be restored to the letters inside "flight".
    spans = [text[starts[m.start()]:ends[m.end()-1]] for m in matches]
    return next((span for span in spans if span == quote), spans[0] if spans else None)


def _contains(quote: str, text: str) -> bool:
    return _source_span(quote, text) is not None


def _restore_source_spans(data: dict, message: str) -> dict:
    """Restore source-linked strings to exact customer spans when safe."""
    result = deepcopy(data)
    sources = result.get("sources")
    if isinstance(sources, dict):
        for key, quote in list(sources.items()):
            span = _source_span(quote, message)
            if span is not None:
                sources[key] = span
    clarifications = result.get("clarifications")
    if isinstance(clarifications, list):
        for item in clarifications:
            if not isinstance(item, dict):
                continue
            quote = item.get("source_quote")
            span = _source_span(quote, message)
            if span is not None:
                item["source_quote"] = span
    return result


def _cabin_label(value: str) -> str:
    """Normalize a cabin label for comparison without changing source text."""
    return " ".join(
        value.strip().translate(_SOURCE_TYPOGRAPHY).casefold()
        .replace("_", " ").replace("-", " ").split()
    )


def _target_phrase_negated(text: str, start: int, end: int) -> bool:
    """Check polarity immediately surrounding one matched target phrase."""
    prefix = text[max(0, start - 100):start]
    suffix = text[end:end + 60]
    # ``non-refundable`` is an explicit absence requirement.  The word
    # boundary before ``refundable`` still lets the target matcher see it, so
    # handle the compound prefix before the ordinary negation patterns.
    if re.search(r"\bnon[- ]$", prefix):
        return True
    if re.search(
        r"(?:\b(?:do|does|did)\s+not|\b(?:don't|doesn't|didn't))\s+"
        r"(?:want|need|require|prefer)\s+(?:a|an|the)?\s*$"
        r"|\bno\s+(?:preference\s+(?:for|on)?|need\s+(?:for)?|"
        r"requirement\s+(?:for)?|)\s*$"
        r"|\bwithout\s+(?:a|an|the)?\s*$"
        r"|\bnot\s+(?:a|an|the)?\s*$",
        prefix,
    ):
        return True
    return bool(re.match(
        r"^\s*(?:(?:is|are|was|were)\s+not\s+|(?:isn't|aren't|wasn't|weren't)\s+|not\s+)+"
        r"(?:required|needed|wanted|preferred|necessary|unwanted|unnecessary)\b",
        suffix,
    ))


def _canonical_cabin(domain: str, value: str) -> str:
    if type(value) is not str or not value.strip():
        raise GroundingFailure("cabin must be a nonempty supported category")
    label = _cabin_label(value)
    profile_field = get_profile(domain)["fields"].get("cabin", {})
    choices = profile_field.get("choices") or profile_field.get("enum") or profile_field.get("values")
    if isinstance(choices, list) and choices:
        for choice in choices:
            if type(choice) is str and _cabin_label(choice) == label:
                return choice.strip().casefold()
        raise GroundingFailure("cabin value is not a supported category")
    if label not in _CABIN_CANONICAL:
        raise GroundingFailure("cabin value is not a supported category")
    return _CABIN_CANONICAL[label]


def _cabin_quote_supports(value: str, quote: str, domain: str) -> bool:
    canonical = _canonical_cabin(domain, value)
    target = _cabin_label(canonical)
    normalized = _cabin_label(quote)
    occupied: list[tuple[int, int, str]] = []
    for label, category in sorted(_CABIN_SOURCE_CATEGORIES, key=lambda item: -len(item[0])):
        pattern = re.compile(rf"(?<!\w){re.escape(label)}(?!\w)")
        for match in pattern.finditer(normalized):
            if any(match.start() < end and match.end() > start for start, end, _ in occupied):
                continue
            occupied.append((match.start(), match.end(), category))
    for start, end, category in occupied:
        if category == target and not _target_phrase_negated(normalized, start, end):
            return True
    return False


def _one_way_quote_supports(quote: str) -> bool:
    if not isinstance(quote, str):
        return False
    normalized = _cabin_label(quote)
    return any(
        not _target_phrase_negated(normalized, match.start(), match.end())
        for match in _ONE_WAY_QUOTE.finditer(normalized)
    )


def one_way_quote_supported(quote: str) -> bool:
    """Public source matcher for offline/profile adapters."""
    return _one_way_quote_supports(quote)


def _field_source_scope(
    key: str,
    quote: str,
    message: str,
    source_messages: list[dict] | None = None,
) -> str:
    """Use a latest trusted field-bound customer turn as polarity scope."""
    for item in reversed(source_messages or []):
        if not isinstance(item, dict) or item.get("role") not in {"user", "customer"}:
            continue
        reply_to = item.get("reply_to")
        content = item.get("content")
        if (not isinstance(reply_to, dict) or reply_to.get("field") != key
                or not isinstance(content, str) or not content.strip()):
            continue
        if _contains(quote, content):
            return content
    return message


def _airport_source_supports(code: str, quote: str, message: str | None = None) -> bool:
    """Require catalogue identity and positive polarity in the source span."""
    record = airport_record(code)
    if record is None or not quote_supports_airport(code, quote):
        return False
    if message is None:
        return True
    if _source_span(quote, message) is None:
        return False
    normalized_quote = quote.translate(_SOURCE_TYPOGRAPHY).casefold()
    # Check explicit code occurrences first. This catches a negative code in a
    # larger source quote such as "MCO, but avoid MIA" even when the model
    # incorrectly proposes both airports.
    code_pattern = re.compile(rf"(?<!\w){re.escape(code.casefold())}(?!\w)")
    code_matches = list(code_pattern.finditer(normalized_quote))
    if code_matches:
        if any(_airport_phrase_negated(normalized_quote, match.start(), match.end()) for match in code_matches):
            return False
        # A tiny quote such as "MIA" still needs its surrounding customer
        # context checked; the quote itself cannot hide "avoid MIA".
        if normalized_quote.strip() == code.casefold():
            normalized_message = message.translate(_SOURCE_TYPOGRAPHY).casefold()
            source_pattern = re.compile(rf"(?<!\w){re.escape(code.casefold())}(?!\w)")
            occurrences = list(source_pattern.finditer(normalized_message))
            return bool(occurrences) and not any(
                _airport_phrase_negated(normalized_message, match.start(), match.end())
                for match in occurrences
            )
        return True
    # City/name phrases are also allowed evidence, including distinctive
    # shortened names such as "Heathrow". Their full source quote is checked
    # for polarity, and a tiny phrase is checked in the complete message.
    literal_matches: list[re.Match] = []
    for phrase in (record["city"], record["name"]):
        if not phrase:
            continue
        literal_matches.extend(
            re.finditer(
                rf"(?<!\w){re.escape(phrase.translate(_SOURCE_TYPOGRAPHY).casefold())}(?!\w)",
                normalized_quote,
            )
        )
    if literal_matches:
        if any(_airport_phrase_negated(normalized_quote, match.start(), match.end()) for match in literal_matches):
            return False
        return True
    normalized_message = message.translate(_SOURCE_TYPOGRAPHY).casefold()
    source_span = _source_span(quote, message)
    if source_span is None:
        return False
    source_pattern = re.compile(rf"(?<!\w){re.escape(source_span.casefold())}(?!\w)")
    occurrences = list(source_pattern.finditer(normalized_message))
    return bool(occurrences) and not any(
        _airport_phrase_negated(normalized_message, match.start(), match.end())
        for match in occurrences
    )


def _airport_phrase_negated(text: str, start: int, end: int) -> bool:
    """Reject an airport mentioned in an exclusion or negative clause."""
    prefix = text[max(0, start - 120):start]
    suffix = text[end:end + 80]
    if re.search(r"\b(?:avoid|except|excluding|exclude|skip)\s*$", prefix):
        return True
    if re.search(
        r"(?:\b(?:do|does|did)\s+not|\b(?:don't|doesn't|didn't)|\bnot)\s+"
        r"(?:want|need|prefer|use|include|take|fly\s+to|go\s+to)?\s*"
        r"(?:a|an|the)?\s*$",
        prefix,
    ):
        return True
    return bool(re.match(
        r"^\s*(?:(?:is|are|was|were)\s+not|(?:isn't|aren't|wasn't|weren't)|"
        r"not|unacceptable|excluded|off[- ]limits)\b",
        suffix,
        re.I,
    ))


def _positive_place_alternatives(
    place: str,
    candidates: list[str],
    quote: str,
    message: str | None,
) -> list[str] | None:
    """Resolve a multi-airport city only when all positive alternatives are explicit."""
    if not re.search(r"\b(?:either|any|both)\b", quote, re.I):
        return None
    if re.search(r"\b(?:avoid|except|excluding|exclude|not|don't|doesn't)\b", quote, re.I):
        return None
    if not _contains(place, quote):
        return None
    mentioned = list(dict.fromkeys(
        code for code in re.findall(r"\b[A-Z]{3}\b", quote)
        if code in candidates
    ))
    if len(mentioned) < 2:
        return None
    records = [airport_record(code) for code in mentioned]
    if any(record is None for record in records):
        return None
    identities = {(record["city"].casefold(), record["country"].upper()) for record in records}
    if len(identities) != 1:
        return None
    if not all(_airport_source_supports(code, quote, message) for code in mentioned):
        return None
    return mentioned


def _normalise_airports(
    value,
    key: str,
    quote: str,
    message: str | None = None,
    source_messages: list[dict] | None = None,
) -> tuple[list[str], bool, list[str]]:
    if type(value) is not list or not value or any(type(item) is not str for item in value):
        raise GroundingFailure(f"{key} must contain airport codes or specific city names")
    airports: list[str] = []
    ambiguous = False
    unresolved: list[str] = []
    scoped_message = (
        _field_source_scope(key, quote, message, source_messages)
        if message is not None else None
    )
    for raw in value:
        token = raw.strip()
        lower = token.casefold()
        # Metropolitan and country abbreviations are broad locations, not
        # airport authority codes in this reviewed profile. Check them before
        # the syntactic three-letter IATA test so NYC/CHI/USA remain choices
        # for clarification while explicit LHR/CDG/LIS still work.
        if lower in _AMBIGUOUS_LOCATIONS:
            ambiguous = True
            unresolved.append(token)
        elif _IATA.fullmatch(token.upper()):
            code = token.upper()
            if not _airport_source_supports(code, quote, scoped_message):
                raise GroundingFailure(f"{key} value is not supported by its source quotation")
            airports.append(code)
        elif lower in _AIRPORT_ALIASES:
            legacy_codes = list(_AIRPORT_ALIASES[lower])
            if not all(_airport_source_supports(code, quote, scoped_message) for code in legacy_codes):
                raise GroundingFailure(f"{key} value is not supported by its source quotation")
            airports.extend(legacy_codes)
        else:
            matched_codes = codes_for_place(token)
            if not matched_codes:
                # A customer-named city that is outside the catalogue is a
                # clarification need, not permission to invent an airport.
                ambiguous = True
                unresolved.append(token)
                continue
            if len(matched_codes) > 1:
                alternatives = _positive_place_alternatives(
                    token, matched_codes, quote, scoped_message
                )
                if alternatives:
                    airports.extend(alternatives)
                else:
                    ambiguous = True
                    unresolved.append(token)
                continue
            code = matched_codes[0]
            if not _airport_source_supports(code, quote, scoped_message):
                raise GroundingFailure(f"{key} value is not supported by its source quotation")
            airports.append(code)
    # A broad geography is a clarification need, never a fake airport value.
    if ambiguous:
        return [], True, unresolved
    deduped = list(dict.fromkeys(airports))
    if not deduped:
        raise GroundingFailure(f"{key} has no specific airport value")
    return deduped, False, []


def _append_guidance(text: str, guidance: list[str]) -> str:
    if not guidance:
        return text
    suffix = " ".join(guidance)
    return f"{text.rstrip()} {suffix}".strip()


_FIELD_CLARIFICATION = re.compile(
    r"^(origin|destination)(?:\s+airport)?\s+"
    r"(?:unspecified|not\s+specified|needs?\s+clarification)"
    r"(?:\s*(?:for|about|:|\()\s*([A-Za-z][A-Za-z .'-]{0,50})\s*\)?)?$",
    re.I,
)


def _field_clarification_match(value: str, message: str):
    match = _FIELD_CLARIFICATION.fullmatch(value.strip().rstrip("."))
    location = match.group(2).strip() if match and match.group(2) else ""
    if not match or (location and not _contains(location, message)):
        return None
    return match


def _remove_field_clarification_flags(data: dict, message: str) -> dict:
    """Remove only the provider's typed marker for an omitted profile field.

    A supported field awaiting clarification is represented by omitted fields
    plus profile questions.  This narrow pattern does not remove substantive
    unsupported conditions such as round-trip or baggage requirements.
    """
    result = deepcopy(data)
    kept: list[str] = []
    guidance: list[str] = []
    for item in result["unsupported"]:
        match = _field_clarification_match(item, message)
        location = match.group(2).strip() if match and match.group(2) else ""
        if not match:
            kept.append(item)
            continue
        place = match.group(1).casefold()
        guidance.append(f"Please specify a {place} airport{f' for {location}' if location else ''}.")
    result["unsupported"] = kept
    result["explanation"] = _append_guidance(result["explanation"], guidance)
    return result


def _normalise_fields(
    domain: str,
    data: dict,
    message: str,
    source_messages: list[dict] | None = None,
) -> dict:
    result = deepcopy(data)
    fields = result["fields"]
    sources = result["sources"]
    guidance: list[str] = []
    for key in list(fields):
        if key == "cabin":
            quote = sources.get(key, "")
            if type(quote) is not str or not quote or not _contains(quote, message):
                raise GroundingFailure("cabin source quotation is not in customer text")
            fields[key] = _canonical_cabin(domain, fields[key])
            continue
        if key == "trip_type":
            quote = sources.get(key, "")
            if type(quote) is not str or not quote or not _contains(quote, message):
                raise GroundingFailure("trip_type source quotation is not in customer text")
            value = fields[key]
            if (type(value) is not str or value.strip().casefold().replace("-", "_").replace(" ", "_") != "one_way"
                    or not _one_way_quote_supports(quote)):
                raise GroundingFailure("trip_type must be a source-grounded one-way value")
            fields[key] = "one_way"
            continue
        if key not in {"origin_airports", "destination_airports"}:
            continue
        quote = sources.get(key, "")
        if type(quote) is not str or not quote or not _contains(quote, message):
            raise GroundingFailure(f"{key} source quotation is not in customer text")
        normalised, ambiguous, unresolved = _normalise_airports(
            fields[key], key, quote, message, source_messages
        )
        if ambiguous:
            # Keep the original customer words in the conversation and leave the
            # required field unresolved so the profile asks for a specific airport.
            fields.pop(key, None)
            sources.pop(key, None)
            place = "origin" if key == "origin_airports" else "destination"
            locations = ", ".join(unresolved[:3]) or "the requested area"
            guidance.append(f"Please specify a {place} airport for {locations}.")
            clarification = {"field": key, "source_quote": quote, "reason": "ambiguous"}
            if clarification not in result["clarifications"]:
                result["clarifications"].append(clarification)
        else:
            fields[key] = normalised
    result["explanation"] = _append_guidance(result["explanation"], guidance)
    return result


def _reconcile_one_way_unsupported(data: dict) -> dict:
    """Remove only an exact duplicate one-way marker after grounding it."""
    result = deepcopy(data)
    if result["fields"].get("trip_type") != "one_way":
        return result
    quote = result["sources"].get("trip_type")
    if not isinstance(quote, str) or not _one_way_quote_supports(quote):
        return result
    result["unsupported"] = [
        item for item in result["unsupported"]
        if not (_is_standalone_one_way_marker(item) and _one_way_quote_supports(item))
    ]
    return result


def _is_standalone_one_way_marker(value: str) -> bool:
    if type(value) is not str:
        return False
    normalized = value.strip().translate(_SOURCE_TYPOGRAPHY).casefold().rstrip(".!?;:,")
    return bool(_ONE_WAY_QUOTE.fullmatch(normalized))


def reconcile_one_way_unsupported(data: dict) -> dict:
    """Reconcile merged flags after pipeline preservation without widening scope."""
    return _reconcile_one_way_unsupported(data)


def _cabin_marker_canonical(value: str) -> str | None:
    if type(value) is not str:
        return None
    normalized = _cabin_label(value).rstrip(".!?;:,")
    markers = {
        "basic economy": "basic_economy",
        "basic economy class": "basic_economy",
        "premium economy": "premium_economy",
        "premium economy class": "premium_economy",
        "economy": "economy",
        "economy class": "economy",
        "business": "business",
        "business class": "business",
        "first": "first",
        "first class": "first",
    }
    for label, canonical in list(markers.items()):
        if normalized in {label, f"{label} is fine", f"{label} is okay"}:
            return canonical
    return None


def reconcile_cabin_unsupported(data: dict, domain: str, message: str) -> dict:
    """Remove only duplicate standalone positive cabin markers after merging."""
    result = deepcopy(data)
    value = result.get("fields", {}).get("cabin") if isinstance(result.get("fields"), dict) else None
    quote = result.get("sources", {}).get("cabin") if isinstance(result.get("sources"), dict) else None
    if (not isinstance(value, str) or not isinstance(quote, str)
            or not _contains(quote, message)):
        return result
    try:
        canonical = _canonical_cabin(domain, value)
    except GroundingFailure:
        return result
    if not _cabin_quote_supports(canonical, quote, domain):
        return result
    result["unsupported"] = [
        item for item in result.get("unsupported", [])
        if _cabin_marker_canonical(item) != _cabin_label(canonical).replace(" ", "_")
    ]
    return result


def clarification_guidance(data: object, message: str) -> list[str]:
    """Return guidance for broad/unknown airport values in a quarantined draft."""
    if not isinstance(data, dict) or not isinstance(data.get("fields"), dict):
        return []
    sources = data.get("sources") if isinstance(data.get("sources"), dict) else {}
    guidance: list[str] = []
    for key in ("origin_airports", "destination_airports"):
        values = data["fields"].get(key)
        quote = sources.get(key)
        if not isinstance(values, list) or not isinstance(quote, str) or not _contains(quote, message):
            continue
        try:
            _, ambiguous, unresolved = _normalise_airports(values, key, quote, message)
        except GroundingFailure:
            continue
        if ambiguous:
            place = "origin" if key == "origin_airports" else "destination"
            locations = ", ".join(unresolved[:3]) or "the requested area"
            guidance.append(f"Please specify a {place} airport for {locations}.")
    return guidance


def _money_cents(quote: str) -> int | None:
    qualifier = r"(?:under|below|at\s+most|up\s+to|max(?:imum)?(?:\s+of)?|budget(?:\s+of)?)"
    qualified = re.search(
        rf"(?i)\b{qualifier}\s*(?:USD\s*)?\$?\s*(\d[\d,]*(?:\.\d{{1,2}})?)",
        quote,
    )
    if qualified:
        try:
            cents = int(Decimal(qualified.group(1).replace(",", "")) * 100)
        except (InvalidOperation, ValueError):
            return None
        return cents - 1 if re.match(r"(?i)under|below", qualified.group(0).strip()) else cents
    dollar = re.search(r"\$\s*(\d[\d,]*(?:\.\d{1,2})?)", quote)
    if dollar:
        try:
            return int(Decimal(dollar.group(1).replace(",", "")) * 100)
        except (InvalidOperation, ValueError):
            return None
    return None


_MONEY_BOUND = re.compile(
    r"(?i)\b(?:under|below|at\s+most|up\s+to|max(?:imum)?(?:\s+of)?|"
    r"budget(?:\s+of)?)\s*(?:USD\s*)?\$?\s*"
    r"\d[\d,]*(?:\.\d{1,2})?"
)
_MONEY_AMBIGUITY = re.compile(
    r"(?i)\b(?:around|about|roughly|approximately|flexible|prefer(?:ably)?|"
    r"ignore\s+(?:the\s+)?budget|if|unless|maybe)\b"
)
_MONEY_CORRECTION = re.compile(
    r"(?i)\b(?:actually|instead|correction|change(?:d)?|update(?:d)?|"
    r"rather|now)\b"
)
_MONEY_TOKEN = re.compile(
    r"(?i)(?:USD\s*\$?\s*|\$\s*)\d[\d,]*(?:\.\d{1,2})?"
    r"|\b\d[\d,]*(?:\.\d{1,2})?\s*(?:USD|dollars?)\b"
)


def _amount_token_cents(token: str) -> int | None:
    match = re.search(r"\d[\d,]*(?:\.\d{1,2})?", token)
    if not match:
        return None
    try:
        return int(Decimal(match.group(0).replace(",", "")) * 100)
    except (InvalidOperation, ValueError):
        return None


def _money_bounds(message: str) -> list[tuple[int, int, int]]:
    """Return (start, end, cents) for explicit monetary bounds."""
    bounds: list[tuple[int, int, int]] = []
    normalized = message.translate(_SOURCE_TYPOGRAPHY)
    for match in _MONEY_BOUND.finditer(normalized):
        cents = _money_cents(match.group(0))
        if cents is not None:
            bounds.append((match.start(), match.end(), cents))
    # Count standalone dollar/USD amounts too, so a conflicting bare budget
    # cannot be hidden behind one otherwise valid bound.  Skip tokens already
    # covered by a qualified match.
    for match in _MONEY_TOKEN.finditer(normalized):
        if any(match.start() < end and match.end() > start for start, end, _ in bounds):
            continue
        cents = _amount_token_cents(match.group(0))
        if cents is not None:
            bounds.append((match.start(), match.end(), cents))
    return sorted(bounds, key=lambda item: item[0])


def _safe_money_clarification(quote: str, message: str) -> int | None:
    """Compile one unambiguous quoted bound into its canonical cents value.

    This is a small compiler for an explicit customer bound, rather than a
    fallback extractor.  Ambiguous budget language and conflicting bounds
    stay as reviewable clarifications.
    """
    if (not isinstance(quote, str) or not isinstance(message, str)
            or not _contains(quote, message)
            or _MONEY_AMBIGUITY.search(quote.translate(_SOURCE_TYPOGRAPHY))
            or _MONEY_AMBIGUITY.search(message.translate(_SOURCE_TYPOGRAPHY))):
        return None
    value = _money_cents(quote)
    if value is None or not _MONEY_BOUND.search(quote.translate(_SOURCE_TYPOGRAPHY)):
        return None
    bounds = _money_bounds(message)
    if not bounds:
        return None
    values = {item[2] for item in bounds}
    if len(values) == 1:
        return value if value in values else None
    # Multiple bounds are accepted only when the final one is an explicit
    # correction.  This preserves the existing latest-correction semantics
    # while leaving ordinary contradictory budgets for human review.
    latest = bounds[-1]
    if value != latest[2] or not _MONEY_CORRECTION.search(
        message[max(0, latest[0] - 80):latest[0]]
    ):
        return None
    return value


def _remove_money_clarification_explanation(text: str) -> str:
    """Remove only an explanation sentence made obsolete by money repair."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    kept = []
    for sentence in sentences:
        has_money = re.search(r"(?i)\b(?:price|budget|total|cost|amount|cent)\w*\b", sentence)
        has_uncertainty = re.search(
            r"(?i)\b(?:clarif\w*|ambigu\w*|unclear|cannot|can't|unable|not\s+map)\b",
            sentence,
        )
        if has_money and has_uncertainty:
            continue
        if sentence:
            kept.append(sentence)
    return " ".join(kept).strip() or "Review the proposed requirements."


def _recover_money_clarification(data: dict, domain: str, message: str) -> dict:
    """Promote only a safely compilable max-total clarification."""
    if domain not in {"flight", "hotel"}:
        return data
    result = deepcopy(data)
    if "max_total_cents" in result["fields"]:
        return result
    clarifications = result.get("clarifications", [])
    for item in list(clarifications):
        if (not isinstance(item, dict) or item.get("field") != "max_total_cents"
                or not isinstance(item.get("source_quote"), str)):
            continue
        value = _safe_money_clarification(item["source_quote"], message)
        if value is None:
            continue
        result["fields"]["max_total_cents"] = value
        result["sources"]["max_total_cents"] = item["source_quote"]
        result["clarifications"].remove(item)
        result["explanation"] = _remove_money_clarification_explanation(
            result["explanation"]
        )
        break
    return result


_NATURAL_DATE = re.compile(
    r"(?i)\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?"
    r"(?:,?\s+(\d{4}))?\b"
)
_HOTEL_SHARED_YEAR_RANGE = re.compile(
    r"(?i)\b(?P<month1>[A-Za-z]{3,9})\.?\s+"
    r"(?P<day1>\d{1,2})(?:st|nd|rd|th)?\s*"
    r"(?:through|to|[-\u2010-\u2015])\s*"
    r"(?:(?P<month2>[A-Za-z]{3,9})\.?\s+)?"
    r"(?P<day2>\d{1,2})(?:st|nd|rd|th)?\s*,?\s*"
    r"(?P<year>(?:19|20)\d{2})\b"
)


def _shared_hotel_year_supports(value: str, quote: str, message: str,
                                domain: str | None, key: str | None) -> bool:
    """Prove a yearless hotel date from one same-month, shared-year range.

    This is deliberately narrower than general date inference.  It only uses
    an explicit full range in the hotel request, and never applies to flight
    dates, cross-month ranges, or a phrase without a year.
    """
    if domain != "hotel" or key not in {"checkin_date", "checkout_date"}:
        return False
    if not isinstance(value, str) or not isinstance(quote, str) or not isinstance(message, str):
        return False
    try:
        expected = date.fromisoformat(value)
    except ValueError:
        return False
    if _YEAR.search(quote):
        return False
    natural = _NATURAL_DATE.search(quote.translate(_SOURCE_TYPOGRAPHY))
    if not natural or natural.group(1).casefold() not in _MONTHS or natural.group(3):
        return False
    quote_month = _MONTHS[natural.group(1).casefold()]
    quote_day = int(natural.group(2))
    if (expected.month, expected.day) != (quote_month, quote_day):
        return False
    normalized_message = message.translate(_SOURCE_TYPOGRAPHY)
    for match in _HOTEL_SHARED_YEAR_RANGE.finditer(normalized_message):
        month1 = match.group("month1").casefold()
        month2 = match.group("month2")
        if month1 not in _MONTHS:
            continue
        month1_number = _MONTHS[month1]
        month2_number = month1_number if not month2 else _MONTHS.get(month2.casefold())
        if month2_number != month1_number:
            continue
        if expected.year != int(match.group("year")):
            continue
        day1 = int(match.group("day1"))
        day2 = int(match.group("day2"))
        if (quote_month, quote_day) not in {
            (month1_number, day1), (month2_number, day2)
        }:
            continue
        try:
            # Validate both endpoints too; malformed dates must never become
            # authority through a regex-only match.
            date(expected.year, month1_number, day1)
            date(expected.year, month2_number, day2)
        except ValueError:
            continue
        return True
    return False


def _date_in_quote(value: str, quote: str, *, message: str | None = None,
                   domain: str | None = None, key: str | None = None) -> bool:
    if value.casefold() in quote.casefold():
        return True
    try:
        expected = date.fromisoformat(value)
    except ValueError:
        return False
    natural = _NATURAL_DATE.search(quote.translate(_SOURCE_TYPOGRAPHY))
    if not natural or natural.group(1).casefold() not in _MONTHS or not natural.group(3):
        return bool(message and _shared_hotel_year_supports(value, quote, message, domain, key))
    try:
        if expected == date(int(natural.group(3)), _MONTHS[natural.group(1).casefold()], int(natural.group(2))):
            return True
    except ValueError:
        return False
    return bool(message and _shared_hotel_year_supports(value, quote, message, domain, key))


def _airport_quote_supports(
    value: list[str], quote: str, message: str | None = None,
    source_messages: list[dict] | None = None,
    key: str | None = None,
) -> bool:
    scoped_message = (
        _field_source_scope(key, quote, message, source_messages)
        if key and message is not None and source_messages is not None else message
    )
    for airport in value:
        if not _airport_source_supports(airport, quote, scoped_message):
            return False
    return True


def _reply_binding(key: str, value: bool, quote: str, domain: str,
                   source_messages: list[dict] | None) -> str | None:
    """Resolve only a short trusted customer reply to a profile question.

    The reply remains the customer's exact quote (usually ``Yes``/``No``),
    while the interface question supplies field context.  Arbitrary text and
    assistant wording never enter this binding path.
    """
    if not source_messages or quote.strip().casefold() not in {"yes", "yes,", "yes please", "no", "no,", "no thanks"}:
        return None
    profile = get_profile(domain)
    field = profile.get("fields", {}).get(key)
    if not field or field.get("type") != "boolean":
        return None
    expected_question = field.get("question")
    for item in source_messages:
        if (not isinstance(item, dict) or item.get("role") not in {"user", "customer"}
                or item.get("content", "").strip().casefold() != quote.strip().casefold()):
            continue
        reply_to = item.get("reply_to")
        if not isinstance(reply_to, dict) or reply_to.get("field") != key:
            continue
        if reply_to.get("question") != expected_question:
            continue
        return "yes" if quote.strip().casefold().startswith("yes") else "no"
    return None


def _boolean_quote_supports(key: str, value: bool, quote: str, *, domain: str = "flight",
                            source_messages: list[dict] | None = None) -> bool:
    q = quote.translate(_SOURCE_TYPOGRAPHY).casefold()
    reply_binding = _reply_binding(key, value, quote, domain, source_messages)
    if reply_binding is not None:
        # "No" answers a requirement question by declining the requirement;
        # it must not become a stored false preference.
        return reply_binding == "yes" and value is True
    terms = {
        "nonstop": (r"\bnon[- ]?stop\b", r"\b(?:zero|no|without(?:\s+any)?)\s+(?:connections?|stops?)\b"),
        "refundable": (
            r"\brefundable\b",
            r"\bfree\s+cancellation\b",
            r"\bfree(?:ly)?\s+cancel(?:l)?able\b",
            r"\b(?:cancelled|canceled)\s+free(?:ly)?\b",
            r"\b(?:cancellation|reservation)\s+(?:is\s+)?free\b",
        ),
        "breakfast": (r"\bbreakfast\b",),
        "accessible": (r"\baccessib(?:le|ility)\b",),
    }.get(key, ())
    matches = [
        match for pattern in terms
        for match in re.finditer(pattern, q)
    ] if terms else []
    if not matches:
        return False
    if key == "refundable":
        # Refundability has several customer-facing phrasings.  Evaluate
        # polarity around each target phrase instead of letting an unrelated
        # clause such as "no preference on departure time" poison the value.
        # A fee/charge clause that is explicitly not required is still a
        # negation of the target, never proof of a refundable stay.
        def positive(match: re.Match) -> bool:
            if _target_phrase_negated(q, match.start(), match.end()):
                return False
            prefix = q[max(0, match.start() - 90):match.start()]
            if re.search(
                r"\b(?:preferably|ideally|would\s+prefer|prefer)\s+"
                r"(?:a|an|the)?\s*$",
                prefix,
            ):
                return False
            suffix = q[match.end():match.end() + 90]
            return not bool(re.match(
                r"\s+(?:fees?|charges?|costs?)\b[^.;!?]{0,60}\b"
                r"(?:is|are|was|were)?\s*not\s+"
                r"(?:required|needed|wanted|included|necessary)\b",
                suffix,
            ))
        if value:
            return any(positive(match) for match in matches)
        return any(_target_phrase_negated(q, match.start(), match.end()) for match in matches)
    if re.search(
        r"\b(?:don't|do not|doesn't|does not)\s+(?:require|need|care)\b"
        r"|\bno\s+(?:need|requirement|preference)\b"
        r"|\bwithout\s+(?:caring|care)\s+about\b",q,
    ):
        return False
    # Soft preferences are useful review context but are not hard constraints.
    if value and re.search(r"\b(?:preferably|ideally|if\s+possible|would\s+prefer|prefer)\b", q):
        return False
    if value:
        if key == "nonstop":
            # "no connections" and "zero stops" positively require nonstop;
            # only negations of nonstop itself cancel a true value.
            return not bool(re.search(r"\b(?:don't|do not|doesn't|does not)\s+(?:require|need|care\s+about)?\s*non[- ]?stop\b", q) or
                                re.search(r"\b(?:no|without|not)\s+non[- ]?stop\b", q))
        return not bool(re.search(r"\b(?:don't|do not|doesn't|does not|no|without|not)\b", q))
    # False means an explicit absence requirement. Phrases such as "no need",
    # "no preference", and "without caring" decline a requirement instead.
    if re.search(
        r"\b(?:don't|do not|doesn't|does not)\s+(?:require|need|care)\b"
        r"|\bno\s+(?:need|requirement|preference)\b"
        r"|\bwithout\s+(?:caring|care)\s+about\b",
        q,
    ):
        return False
    if key == "nonstop":
        return bool(re.search(r"\b(?:no|without|not|avoid)\s+non[- ]?stop\b", q))
    return bool(re.search(r"\b(?:no|without|not|avoid|non[- ]?)\b", q))


_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def _integer_appears(value: int, quote: str) -> bool:
    if re.search(rf"\b{re.escape(str(value))}\b", quote):
        return True
    return any(number == value and re.search(rf"\b{word}\b", quote, re.I)
               for word, number in _NUMBER_WORDS.items())


def _integer_with_unit_supports(value: int, quote: str, unit: str) -> bool:
    """Require a count and its reviewed unit in the same source phrase."""
    if type(value) is not int or unit not in {"room", "adult"}:
        return False
    number = r"(?:\d+|" + "|".join(_NUMBER_WORDS) + r")"
    match = re.search(rf"\b({number})\s+{unit}s?\b", quote.translate(_SOURCE_TYPOGRAPHY), re.I)
    if not match:
        return False
    token = match.group(1).casefold()
    parsed = int(token) if token.isdigit() else _NUMBER_WORDS.get(token)
    return parsed == value


def _time_in_quote(value: str, quote: str) -> bool:
    if value in quote:
        return True
    match = re.fullmatch(r"([01]\d|2[0-3]):([0-5]\d)", value)
    if not match:
        return False
    hour, minute = int(match.group(1)), match.group(2)
    if hour == 0:
        twelve_hour, meridiem = 12, "am"
    elif hour == 12:
        twelve_hour, meridiem = 12, "pm"
    elif hour < 12:
        twelve_hour, meridiem = hour, "am"
    else:
        twelve_hour, meridiem = hour - 12, "pm"
    return bool(re.search(rf"\b0?{twelve_hour}(?::?{minute})?\s*{meridiem}\b", quote, re.I))


def _ground_field(key: str, value, quote: str, message: str, domain: str,
                  source_messages: list[dict] | None = None) -> None:
    if type(quote) is not str or not quote or not _contains(quote, message):
        raise GroundingFailure(f"{key} source quotation is not in customer text")
    if key in {"origin_airports", "destination_airports"}:
        if not _airport_quote_supports(value, quote, message, source_messages, key):
            raise GroundingFailure(f"{key} value is not supported by its source quotation")
    elif key == "max_total_cents":
        if type(value) is not int or _money_cents(quote) != value:
            raise GroundingFailure("price value is not supported by its source quotation")
    elif key.endswith("date"):
        temporal = _temporal_value(key, quote, domain, source_messages)
        if temporal is not None:
            if temporal != value:
                raise GroundingFailure(f"{key} value is not supported by its dated source quotation")
            return
        if not isinstance(value, str) or not _date_in_quote(
            value, quote, message=message, domain=domain, key=key
        ):
            raise GroundingFailure(f"{key} value is not supported by its source quotation")
    elif key in {"nonstop", "refundable", "breakfast", "accessible"}:
        if type(value) is not bool or not _boolean_quote_supports(
            key, value, quote, domain=domain, source_messages=source_messages
        ):
            raise GroundingFailure(f"{key} value is not supported by its source quotation")
    elif key in {"departure_window"}:
        if not all(isinstance(item, str) and _time_in_quote(item, quote) for item in value):
            raise GroundingFailure("departure window is not supported by its source quotation")
    elif key in {"max_connections", "max_duration_minutes"}:
        if not re.search(r"\b(?:connection|connections|stop|stops|minute|minutes|hour|hours)\b", quote, re.I):
            raise GroundingFailure(f"{key} source quotation lacks its unit")
        if key == "max_duration_minutes":
            duration = re.search(r"\b(\d+)\s*(hour|hours|minute|minutes)\b", quote, re.I)
            supported = bool(duration and value == int(duration.group(1)) * (60 if duration.group(2).casefold().startswith("hour") else 1))
        else:
            supported = _integer_appears(value, quote)
        if not supported:
            raise GroundingFailure(f"{key} value is not supported by its source quotation")
    elif key in {"rooms", "adults"}:
        unit = "room" if key == "rooms" else "adult"
        if not _integer_with_unit_supports(value, quote, unit):
            raise GroundingFailure(f"{key} value is not supported by its source quotation")
    elif key == "cabin":
        if not _cabin_quote_supports(value, quote, domain):
            raise GroundingFailure("cabin value is not supported by its source quotation")
    elif key == "trip_type":
        if value != "one_way" or not _one_way_quote_supports(quote):
            raise GroundingFailure("trip_type value is not supported by its source quotation")
    elif isinstance(value, str):
        if value.casefold() not in quote.casefold():
            aliases = [name for name, codes in _AIRPORT_ALIASES.items() if value in codes]
            if not any(alias in quote.casefold() for alias in aliases):
                raise GroundingFailure(f"{key} value is not supported by its source quotation")


_DATEISH_QUOTE = re.compile(
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
    r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
    r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b"
    r"|\b(?:today|tomorrow|tonight|friday|saturday|sunday|weekend|"
    r"next\s+week|first\s+week|early|mid|late)\b"
    r"|\b\d{1,2}\s*[/.-]\s*\d{1,2}\b",
    re.I,
)
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_NO_REQUIREMENT_BOOLEAN = re.compile(
    r"\b(?:don't|do not|doesn't|does not)\s+(?:require|need|care)\b"
    r"|\bno\s+(?:need|requirement|preference)\b"
    r"|\bwithout\s+(?:a\s+)?(?:caring|care|preference)\b"
    r"|\bnot\s+(?:required|needed|necessary)\b",
    re.I,
)
_ACCESSIBLE_NO_REQUIREMENT = re.compile(
    r"\bno\s+accessib(?:le|ility)\s+requirement\b",
    re.I,
)
_UNSUPPORTED_BOOLEAN = re.compile(
    r"\b(?:overnight|red[- ]eye|layover|stopover)\b", re.I
)
_AMBIGUOUS_WINDOW = re.compile(
    r"\b(?:morning|afternoon|evening|early|late)\b|\b(?:before|after)\s+dinner\b",
    re.I,
)
_ARRIVAL_WINDOW = re.compile(r"\b(?:arrive|arrival|land|landing)\b", re.I)
_EXPLICIT_CLOCK = re.compile(
    r"\b(?:[01]?\d|2[0-3]):[0-5]\d\s*(?:am|pm)?\b"
    r"|\b(?:1[0-2]|0?[1-9])\s*(?:am|pm)\b",
    re.I,
)


def _yearless_date_quote(quote: str) -> bool:
    """Identify a date-like customer phrase whose year is genuinely absent."""
    return bool(
        isinstance(quote, str)
        and not _YEAR.search(quote)
        and _DATEISH_QUOTE.search(quote)
    )


def _recover_safe_field_uncertainty(data: dict, domain: str, message: str,
                                    source_messages: list[dict] | None = None) -> dict:
    """Compile a narrow set of uncertain fields into reviewable evidence.

    This deliberately handles only uncertainty that can be proven from the
    source phrase. Wrong explicit values, bad quotes, and unsupported types
    still fail deterministic validation and remain subject to audit repair.
    """
    result = deepcopy(data)
    fields = result["fields"]
    sources = result["sources"]
    profile_fields = get_profile(domain)["fields"]
    guidance: list[str] = []
    for key in list(fields):
        value = fields[key]
        quote = sources.get(key)
        if not isinstance(quote, str) or not quote or not _contains(quote, message):
            continue
        if key not in profile_fields:
            # Preserve an actual condition the selected profile cannot express
            # instead of treating a model-invented field as authoritative.
            fields.pop(key, None)
            sources.pop(key, None)
            if quote not in result["unsupported"]:
                result["unsupported"].append(quote)
            continue
        if (key.endswith("date") and _yearless_date_quote(quote)
                and _temporal_value(key, quote, domain, source_messages) is None
                and not _shared_hotel_year_supports(value, quote, message, domain, key)):
            fields.pop(key, None)
            sources.pop(key, None)
            clarification = {"field": key, "source_quote": quote, "reason": "ambiguous"}
            if not any(item.get("field") == key for item in result["clarifications"]):
                result["clarifications"].append(clarification)
            guidance.append(f"Please specify the year for {key.replace('_', ' ')}.")
            continue
        if (key == "departure_window" and _AMBIGUOUS_WINDOW.search(quote)
                and not _EXPLICIT_CLOCK.search(quote)):
            fields.pop(key, None)
            sources.pop(key, None)
            if _ARRIVAL_WINDOW.search(quote):
                if quote not in result["unsupported"]:
                    result["unsupported"].append(quote)
            else:
                clarification = {
                    "field": key, "source_quote": quote, "reason": "ambiguous"
                }
                if not any(item.get("field") == key for item in result["clarifications"]):
                    result["clarifications"].append(clarification)
                guidance.append("Please specify exact departure times.")
            continue
        if key == "max_duration_minutes" and _UNSUPPORTED_BOOLEAN.search(quote):
            # Overnight/red-eye language is a substantive itinerary condition,
            # not evidence for a numeric duration field.
            fields.pop(key, None)
            sources.pop(key, None)
            if quote not in result["unsupported"]:
                result["unsupported"].append(quote)
            continue
        if key not in {"nonstop", "refundable", "breakfast", "accessible"}:
            continue
        normalized_quote = quote.translate(_SOURCE_TYPOGRAPHY)
        no_requirement = _NO_REQUIREMENT_BOOLEAN.search(normalized_quote)
        if key == "accessible" and _ACCESSIBLE_NO_REQUIREMENT.search(normalized_quote):
            no_requirement = True
        if (key == "refundable" and no_requirement
                and _boolean_quote_supports(
                    key, value, quote, domain=domain, source_messages=source_messages
                )):
            # Scope "no preference" to the refundability phrase.  For
            # example, "no preference on departure time; refundable is fine"
            # still contains a positive, source-grounded refund requirement.
            no_requirement = None
        if (no_requirement
                or _reply_binding(key, value, quote, domain, source_messages) == "no"):
            # A no-preference answer is an intentional omission, never a
            # stored false requirement and never an unsupported condition.
            fields.pop(key, None)
            sources.pop(key, None)
            result["clarifications"] = [
                item for item in result["clarifications"] if item.get("field") != key
            ]
            result["unsupported"] = [item for item in result["unsupported"] if item != quote]
            continue
        if (_UNSUPPORTED_BOOLEAN.search(quote)
                and not _boolean_quote_supports(
                    key, value, quote, domain=domain, source_messages=source_messages
                )):
            # Preserve an uncheckable condition as the exact customer phrase
            # rather than laundering it into a false boolean.
            fields.pop(key, None)
            sources.pop(key, None)
            if quote not in result["unsupported"]:
                result["unsupported"].append(quote)
            continue
    # A provider may quarantine an arrival-time or overnight condition as a
    # clarification for a nearby supported field. Preserve the exact customer
    # phrase as unsupported because these conditions have no reviewed field.
    retained_clarifications: list[dict] = []
    for item in result["clarifications"]:
        if not isinstance(item, dict):
            retained_clarifications.append(item)
            continue
        field = item.get("field")
        quote = item.get("source_quote")
        if (field not in {"departure_window", "max_duration_minutes"}
                or not isinstance(quote, str)
                or not _contains(quote, message)):
            retained_clarifications.append(item)
            continue
        misclassified_arrival = (
            field == "departure_window" and _ARRIVAL_WINDOW.search(quote)
        )
        misclassified_overnight = (
            field == "max_duration_minutes" and _UNSUPPORTED_BOOLEAN.search(quote)
        )
        if not (misclassified_arrival or misclassified_overnight):
            retained_clarifications.append(item)
            continue
        if quote not in result["unsupported"]:
            result["unsupported"].append(quote)
    result["clarifications"] = retained_clarifications
    result["explanation"] = _append_guidance(result["explanation"], guidance)
    return result


def _recover_unknown_clarifications(data: dict, domain: str, message: str) -> dict:
    """Quarantine grounded clarifications for fields outside this profile.

    Profiles intentionally expose only reviewed fields. A provider can still
    name a real customer condition using a field from another domain. Preserve
    that condition as unsupported only when the record itself is structurally
    valid and its quote is an exact customer span; malformed or ungrounded
    records remain validation failures.
    """
    result = deepcopy(data)
    profile_fields = get_profile(domain)["fields"]
    retained: list[dict] = []
    for item in result["clarifications"]:
        if type(item) is not dict or set(item) != {"field", "source_quote", "reason"}:
            retained.append(item)
            continue
        field = item["field"]
        quote = item["source_quote"]
        reason = item["reason"]
        if (type(field) is not str or not field.strip() or field in profile_fields
                or type(quote) is not str or not quote.strip() or len(quote) > 2500
                or type(reason) is not str or reason not in CLARIFICATION_REASONS):
            retained.append(item)
            continue
        source_span = _source_span(quote, message)
        if source_span is None:
            retained.append(item)
            continue
        # A condition already represented as unsupported cannot also be
        # reclassified through an unknown clarification field. Keeping this
        # duplicate for normal validation prevents two competing records for
        # one customer clause.
        if any(_contains(source_span, existing) or _contains(existing, source_span)
               for existing in result["unsupported"]):
            # The existing unsupported phrase is retained as the canonical
            # record; this duplicate clarification is safely coalesced.
            continue
        if source_span not in result["unsupported"]:
            result["unsupported"].append(source_span)
    result["clarifications"] = retained
    return result


def grounded_unknown_clarifications(data: object, domain: str,
                                    message: str) -> list[str]:
    """Return safe unknown-field clarification phrases for audit retention."""
    if not isinstance(data, dict) or not isinstance(data.get("clarifications"), list):
        return []
    profile_fields = get_profile(domain)["fields"]
    existing = data.get("unsupported") if isinstance(data.get("unsupported"), list) else []
    result: list[str] = []
    for item in data["clarifications"]:
        if type(item) is not dict or set(item) != {"field", "source_quote", "reason"}:
            continue
        field = item["field"]
        quote = item["source_quote"]
        reason = item["reason"]
        if (type(field) is not str or not field.strip() or field in profile_fields
                or type(quote) is not str or not quote.strip() or len(quote) > 2500
                or type(reason) is not str or reason not in CLARIFICATION_REASONS):
            continue
        source_span = _source_span(quote, message)
        if source_span is None:
            continue
        if any(_contains(source_span, item) or _contains(item, source_span)
               for item in existing if isinstance(item, str)):
            continue
        if source_span not in result:
            result.append(source_span)
    return result[:20]


def recovery_records(data: object, domain: str, message: str,
                     source_messages: list[dict] | None = None) -> list[dict]:
    """Describe deterministic recovery in trace-safe identifiers only."""
    if not isinstance(data, dict) or not isinstance(data.get("fields"), dict):
        return []
    sources = data.get("sources") if isinstance(data.get("sources"), dict) else {}
    profile_fields = get_profile(domain)["fields"]
    records: list[dict] = []
    for key, value in data["fields"].items():
        quote = sources.get(key)
        if not isinstance(quote, str) or not quote or not _contains(quote, message):
            continue
        reason = None
        if key not in profile_fields:
            reason = "unsupported_profile_field"
        elif (key.endswith("date") and _yearless_date_quote(quote)
              and not _shared_hotel_year_supports(value, quote, message, domain, key)):
            reason = "year_missing"
        elif (key == "departure_window" and _AMBIGUOUS_WINDOW.search(quote)
              and not _EXPLICIT_CLOCK.search(quote)):
            reason = "arrival_window_unsupported" if _ARRIVAL_WINDOW.search(quote) else "window_ambiguous"
        elif key in {"nonstop", "refundable", "breakfast", "accessible"}:
            no_requirement = _NO_REQUIREMENT_BOOLEAN.search(quote)
            trusted_no = _reply_binding(key, value, quote, domain, source_messages) == "no"
            if no_requirement or trusted_no:
                reason = "no_requirement"
            elif (_UNSUPPORTED_BOOLEAN.search(quote)
                  and not _boolean_quote_supports(
                      key, value, quote, domain=domain, source_messages=source_messages
                  )):
                reason = "unsupported_boolean_condition"
        if reason:
            records.append({"field": key, "reason": reason})
    return records


def _validate_clarifications(data: dict, domain: str, message: str) -> None:
    clarifications = data.get("clarifications")
    if type(clarifications) is not list or len(clarifications) > 20:
        raise EnvelopeFailure("clarifications must be a bounded list")
    profile = get_profile(domain)
    seen: set[str] = set()
    for item in clarifications:
        if type(item) is not dict or set(item) != {"field", "source_quote", "reason"}:
            raise EnvelopeFailure("clarifications must contain field, source_quote, and reason")
        field = item["field"]
        quote = item["source_quote"]
        reason = item["reason"]
        if type(field) is not str or field not in profile["fields"]:
            raise EnvelopeFailure("clarification field is not in the reviewed profile")
        if field in seen:
            raise EnvelopeFailure("clarifications may contain each field only once")
        seen.add(field)
        if (type(quote) is not str or not quote.strip() or len(quote) > 2500
                or not _contains(quote, message)):
            raise GroundingFailure("clarification source quotation is not in customer text")
        if type(reason) is not str or reason not in CLARIFICATION_REASONS:
            raise EnvelopeFailure("clarification reason is not supported")
        if field in data["fields"]:
            raise EnvelopeFailure("a clarified field must be omitted until the customer resolves it")


def _validate_clarification_structure(data: dict) -> None:
    """Reject malformed clarification records before recovery inspects them."""
    clarifications = data.get("clarifications")
    if type(clarifications) is not list or len(clarifications) > 20:
        raise EnvelopeFailure("clarifications must be a bounded list")
    for item in clarifications:
        if type(item) is not dict or set(item) != {"field", "source_quote", "reason"}:
            raise EnvelopeFailure("clarifications must contain field, source_quote, and reason")
        field = item["field"]
        quote = item["source_quote"]
        reason = item["reason"]
        if type(field) is not str or not field.strip():
            raise EnvelopeFailure("clarification field must be a nonempty string")
        if type(quote) is not str or not quote.strip() or len(quote) > 2500:
            raise EnvelopeFailure("clarification source quote must be a bounded string")
        if type(reason) is not str or reason not in CLARIFICATION_REASONS:
            raise EnvelopeFailure("clarification reason is not supported")


def validate_extraction(domain: str, message: str, data: dict,
                        source_messages: list[dict] | None = None) -> dict:
    """Return a canonical, grounded draft or raise a typed local failure."""
    legacy = type(data) is dict and set(data) == LEGACY_KEYS
    if type(data) is not dict or (set(data) != EXPECTED_KEYS and not legacy):
        raise EnvelopeFailure("model response must contain exactly the reviewed envelope keys")
    if legacy:
        data = deepcopy(data)
        data["clarifications"] = []
    if type(data["fields"]) is not dict or type(data["sources"]) is not dict:
        raise EnvelopeFailure("fields and sources must be objects")
    if type(data["unsupported"]) is not list or len(data["unsupported"]) > 20:
        raise EnvelopeFailure("unsupported conditions must be a bounded list")
    if type(data["clarifications"]) is not list or len(data["clarifications"]) > 20:
        raise EnvelopeFailure("clarifications must be a bounded list")
    if any(type(value) is not str or not value.strip() or len(value) > 2500 for value in data["unsupported"]):
        raise EnvelopeFailure("unsupported conditions must be nonempty strings")
    if type(data["explanation"]) is not str or not data["explanation"].strip() or len(data["explanation"]) > 1500:
        raise EnvelopeFailure("explanation must be a bounded string")
    # Old four-key provider responses may carry a legacy freeform marker. New
    # five-key responses must classify supported clarification explicitly.
    canonical = _remove_field_clarification_flags(data, message) if legacy else deepcopy(data)
    canonical = _restore_source_spans(canonical, message)
    canonical = _restore_boolean_scope(canonical, message, source_messages)
    _validate_clarification_structure(canonical)
    canonical = _normalise_fields(domain, canonical, message, source_messages)
    canonical = _compile_temporal_fields(canonical, domain, message, source_messages)
    canonical = reconcile_supported_conditions(canonical, domain, message, source_messages)
    canonical = _recover_safe_field_uncertainty(
        canonical, domain, message, source_messages=source_messages
    )
    canonical = _recover_money_clarification(canonical, domain, message)
    canonical = _recover_unknown_clarifications(canonical, domain, message)
    canonical = _reconcile_one_way_unsupported(canonical)
    if (len(canonical["unsupported"]) > 20
            or any(type(value) is not str or not value.strip() or len(value) > 2500
                   for value in canonical["unsupported"])):
        raise EnvelopeFailure("unsupported conditions must be a bounded list")
    _validate_clarifications(canonical, domain, message)
    try:
        validate_fields(get_profile(domain), canonical["fields"])
    except ValueError as exc:
        raise EnvelopeFailure(str(exc)) from exc
    if set(canonical["sources"]) != set(canonical["fields"]):
        raise EnvelopeFailure("source coverage must match proposed fields")
    for key, value in canonical["fields"].items():
        if value is None:
            raise EnvelopeFailure("null fields are not customer no-preference choices")
        _ground_field(key, value, canonical["sources"].get(key), message, domain, source_messages)
    return canonical


def bounded_unsupported(data: object, message: str | None = None,
                        domain: str | None = None) -> list[str]:
    """Extract only safe first-stage flags for retention during audit repair."""
    legacy = isinstance(data, dict) and "clarifications" not in data
    if not isinstance(data, dict) or not isinstance(data.get("unsupported"), list):
        values = []
    else:
        values = [item.strip() for item in data["unsupported"]
            if isinstance(item, str) and item.strip() and len(item) <= 2500
            and not (legacy and message is not None and _field_clarification_match(item, message))][:20]
    if domain is not None and message is not None:
        for item in grounded_unknown_clarifications(data, domain, message):
            if item not in values:
                values.append(item)
    return list(dict.fromkeys(values))[:20]


def remove_resolved_field_markers(items: list[str], clarifications: list[dict],
                                  message: str) -> list[str]:
    """Drop only a typed missing-field marker resolved by a real clarification.

    Five-key envelopes must carry both the marker and structured clarification
    through audit, so removal is allowed only when field and quoted customer
    words agree. Conditions such as baggage and round trip never match this
    narrow migration pattern.
    """
    if not items or not clarifications:
        return list(items)
    result: list[str] = []
    for item in items:
        match = _field_clarification_match(item, message)
        if not match:
            result.append(item)
            continue
        field = f"{match.group(1).casefold()}_airports"
        location = (match.group(2) or "").strip()
        if not location:
            # Without a location in the legacy marker there is no source
            # overlap to prove that a structured clarification resolves it.
            result.append(item)
            continue
        resolved = False
        for clarification in clarifications:
            if not isinstance(clarification, dict) or clarification.get("field") != field:
                continue
            quote = clarification.get("source_quote")
            if not isinstance(quote, str):
                continue
            if _contains(location, quote) or _contains(quote, location):
                resolved = True
                break
        if not resolved:
            result.append(item)
    return list(dict.fromkeys(result))[:20]


def valid_candidate_fields(data: object, domain: str, message: str,
                           source_messages: list[dict] | None = None) -> dict:
    """Return fields that survived full grounding, or an empty quarantine set."""
    if not isinstance(data, dict):
        return {}
    try:
        candidate = validate_extraction(domain, message, data, source_messages=source_messages)
    except (EnvelopeFailure, GroundingFailure, ValueError):
        return {}
    guidance = " ".join(re.findall(r"Please specify [^.?!]+[.?!]", candidate["explanation"]))
    return {"fields": deepcopy(candidate["fields"]), "sources": deepcopy(candidate["sources"]),
            "guidance": guidance, "clarifications": deepcopy(candidate["clarifications"])}


def valid_candidate_clarifications(data: object, domain: str, message: str) -> list[dict]:
    """Keep valid clarification records even when another candidate field fails."""
    if not isinstance(data, dict) or not isinstance(data.get("clarifications"), list):
        return []
    data = _restore_source_spans(data, message)
    profile = get_profile(domain)
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    valid: list[dict] = []
    for item in data["clarifications"]:
        if type(item) is not dict or set(item) != {"field", "source_quote", "reason"}:
            continue
        field, quote, reason = item["field"], item["source_quote"], item["reason"]
        if (field not in profile["fields"] or reason not in CLARIFICATION_REASONS
                or type(quote) is not str or not quote.strip() or len(quote) > 2500
                or not _contains(quote, message)):
            continue
        if field in fields:
            # A broad airport value is normalized away and may carry a valid
            # clarification; a hard proposed value may not carry both records.
            if field not in {"origin_airports", "destination_airports"}:
                continue
            source = data.get("sources", {}).get(field) if isinstance(data.get("sources"), dict) else None
            source = source if isinstance(source, str) else quote
            try:
                _, ambiguous, _ = _normalise_airports(
                    fields[field], field, source or quote, message
                )
            except GroundingFailure:
                continue
            if not ambiguous:
                continue
        if any(existing["field"] == field for existing in valid):
            continue
        valid.append(deepcopy(item))
    return valid


def preserve_valid_candidate(candidate: dict, audited: dict, domain: str, message: str) -> dict:
    """Prevent a valid first proposal disappearing from a valid audit envelope."""
    result = deepcopy(audited)
    for key, value in candidate.get("fields", {}).items():
        if key not in result["fields"]:
            result["fields"][key] = deepcopy(value)
            result["sources"][key] = deepcopy(candidate["sources"][key])
    guidance = candidate.get("guidance", "")
    if guidance and guidance not in result["explanation"]:
        result["explanation"] = _append_guidance(result["explanation"], [guidance])
    existing = {item["field"] for item in result.get("clarifications", [])}
    for item in candidate.get("clarifications", []):
        if item["field"] not in result["fields"] and item["field"] not in existing:
            result["clarifications"].append(deepcopy(item))
            existing.add(item["field"])
    return result


def preserve_candidate_clarifications(clarifications: list[dict], audited: dict) -> dict:
    result = deepcopy(audited)
    result.setdefault("clarifications", [])
    existing = {item["field"] for item in result["clarifications"]}
    for item in clarifications:
        if item["field"] not in result["fields"] and item["field"] not in existing:
            result["clarifications"].append(deepcopy(item))
            existing.add(item["field"])
    return result


def _temporal_value(key, quote, domain, source_messages=None):
    """Resolve dates only from a customer quote and its recorded clock context."""
    if key not in {'departure_date', 'checkin_date', 'checkout_date'}:
        return None
    resolved = resolve_date_choice(quote, reference_for_quote(quote, source_messages))
    if domain == 'flight' and key == 'departure_date':
        return resolved
    if domain == 'hotel':
        if isinstance(resolved, str):
            return resolved
        if isinstance(resolved, dict) and set(resolved) == {'start', 'end'}:
            return resolved['start' if key == 'checkin_date' else 'end']
    return None


def _compile_temporal_fields(data, domain, message, source_messages=None):
    """Compile explicit choices without losing range endpoints in a proposal.

    A quoted date range can be represented as a range rather than collapsed to
    its first day. Invalid explicit dates are still rejected, not repaired by
    changing their meaning. Typed airport widget replies are similarly complete
    sets of customer-selected options, not model-invented defaults.
    """
    result = deepcopy(data)
    for key, value in list(result['fields'].items()):
        quote = result['sources'].get(key)
        if not isinstance(quote, str) or not _contains(quote, message):
            continue
        expected = _temporal_value(key, quote, domain, source_messages)
        if domain == 'flight' and key == 'departure_date':
            for turn in reversed(source_messages or []):
                content = turn.get('content', '')
                if turn.get('role') not in {'user', 'customer'} or not _contains(quote, content):
                    continue
                expanded = expand_date_quote(quote, content)
                if expanded and _bare_date_condition(expanded):
                    expanded_value = _temporal_value(key, expanded, domain, source_messages)
                    if isinstance(expanded_value, dict):
                        first = expanded_value.get('start') or (expanded_value.get('dates') or [None])[0]
                        if value == first or value == expanded_value:
                            result['fields'][key] = expanded_value
                            result['sources'][key] = expanded
                            quote, expected = expanded, expanded_value
                break
        if isinstance(expected, dict) and isinstance(value, str):
            first = expected.get('start') or (expected.get('dates') or [None])[0]
            if value == first:
                result['fields'][key] = expected
        # A date-question reply can quote the first endpoint while the actual
        # answer specifies a full interval. Preserve that complete source.
        if domain == 'flight' and key == 'departure_date':
            for turn in reversed(source_messages or []):
                content = turn.get('content', '')
                if (turn.get('role') in {'user', 'customer'} and
                        (turn.get('reply_to') or {}).get('field') == key and
                        _contains(quote, content) and _bare_date_condition(content)):
                    full = _temporal_value(key, content, domain, source_messages)
                    if isinstance(full, dict):
                        first = full.get('start') or (full.get('dates') or [None])[0]
                        if value == first or value == full:
                            result['fields'][key] = full
                            result['sources'][key] = content
                    break
    if source_messages:
        turn = source_messages[-1]
        key = (turn.get('reply_to') or {}).get('field')
        content = turn.get('content', '')
        if domain == 'flight' and key in {'origin_airports', 'destination_airports'}:
            prefix = 'Depart from' if key == 'origin_airports' else 'Arrive at'
            match = re.fullmatch('(?i:' + re.escape(prefix) + r')\s+([A-Z]{3}(?:\s+or\s+[A-Z]{3})*)[.!]?', content)
            if match:
                codes = [code.upper() for code in re.split(r'\s+or\s+', match.group(1), flags=re.I)]
                try:
                    validate_fields(get_profile(domain), {key: codes})
                except ValueError:
                    return result
                result['fields'][key] = list(dict.fromkeys(codes))
                result['sources'][key] = content
                result['clarifications'] = [c for c in result['clarifications'] if c['field'] != key]
    return result


_DATE_WORDS = re.compile(
    r'\b(?:dates?|departure|depart|travel|i|can|on|from|between|within|the|next|'
    r'week|days?|today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|through|to|or|and|inclusive|these|work|'
    r'jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|'
    r'aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b', re.I)


def _bare_date_condition(phrase):
    if not isinstance(phrase, str):
        return False
    stripped = re.sub(r'(?<=\d)(?:st|nd|rd|th)\b', '', phrase, flags=re.I)
    stripped = _DATE_WORDS.sub('', stripped)
    return not re.sub(r'[\d\s.,:/\-\u2010-\u2015]+', '', stripped)


_GEO_PATTERN = re.compile(
    r'^(?:(from|to|in)\s+)?(fl|florida|the state of florida|new york|new york city|nyc|'
    r'chicago|chi|washington|new england|usa|united states|the united states)$', re.I)


@lru_cache(maxsize=8)
def _airport_codes_for_region(place: str) -> frozenset[str]:
    """Return every catalogue airport in a named US region for reconciliation."""
    normalized_place = place.strip().casefold()
    aliases = {"fl": "florida"}
    normalized_place = aliases.get(normalized_place, normalized_place)
    return frozenset(
        code
        for code, record in airport_records().items()
        if record["country"].casefold() == "us"
        and record["region"].casefold() == normalized_place
    )


def reconcile_supported_conditions(data, domain, message, source_messages=None):
    """Classify known slot ambiguities; never discard a substantive condition.

    Geography and travel-date choices belong to supported fields. A later
    source-grounded answer resolves the earlier ambiguity in that same slot.
    Additional qualifiers (bags, returns, proximity, arrival deadlines) are
    not bare slot markers and remain held. Every change is still a draft.
    """
    result = deepcopy(data)
    result.setdefault('clarifications', [])
    if domain != 'flight':
        return result
    pending = {item['field']: item for item in result['clarifications']}
    kept = []
    for phrase in result.get('unsupported', []):
        if not isinstance(phrase, str) or not _contains(phrase, message):
            kept.append(phrase)
            continue
        geo = _GEO_PATTERN.fullmatch(phrase.strip())
        field = None
        if geo:
            direction, place = geo.groups()
            direction = (direction or '').casefold()
            if direction == 'from':
                field = 'origin_airports'
            elif direction == 'to':
                field = 'destination_airports'
            else:
                directions = {d.casefold() for d in re.findall(r'\b(from|to)\s+' + re.escape(place) + r'\b', message, re.I)}
                if len(directions) == 1:
                    field = 'origin_airports' if next(iter(directions)).casefold() == 'from' else 'destination_airports'
                else:
                    matches = [item['field'] for item in result['clarifications']
                               if item['field'] in {'origin_airports', 'destination_airports'}
                               and _contains(place, item['source_quote'])]
                    if len(set(matches)) == 1:
                        field = matches[0]
            if field:
                airports = result['fields'].get(field)
                if airports:
                    # A regional marker is satisfied only when every disclosed
                    # airport belongs to that region in the maintained catalog.
                    # No single airport is selected from the region here.
                    region = place.casefold().removeprefix('the state of ')
                    if set(airports) <= _airport_codes_for_region(region):
                        pending.pop(field, None)
                        continue
                    kept.append(phrase)
                    continue
                pending.setdefault(field, {'field': field, 'source_quote': phrase, 'reason': 'ambiguous'})
                continue
        if _bare_date_condition(phrase):
            value = _temporal_value('departure_date', phrase, domain, source_messages)
            if value is not None:
                if 'departure_date' not in result['fields']:
                    result['fields']['departure_date'] = value
                    result['sources']['departure_date'] = phrase
                pending.pop('departure_date', None)
                continue
            if _DATEISH_QUOTE.search(phrase):
                pending.setdefault('departure_date', {'field': 'departure_date', 'source_quote': phrase, 'reason': 'ambiguous'})
                continue
        kept.append(phrase)
    for field, item in list(pending.items()):
        if field in {'origin_airports', 'destination_airports'}:
            airports = _explicit_airport_choices(item['source_quote'])
            if airports:
                result['fields'][field] = airports
                result['sources'][field] = item['source_quote']
                pending.pop(field, None)
                continue
        value = _temporal_value(field, item['source_quote'], domain, source_messages)
        if value is not None:
            if field not in result['fields']:
                result['fields'][field] = value
                result['sources'][field] = item['source_quote']
            pending.pop(field, None)
        elif field in result['fields']:
            pending.pop(field, None)
    result['unsupported'] = list(dict.fromkeys(kept))
    result['clarifications'] = list(pending.values())
    return result


def _explicit_airport_choices(quote):
    """Compile positive alternatives named in a quoted airport answer."""
    if not isinstance(quote, str) or re.search(r'\b(?:not|except|avoid|preferably|maybe)\b', quote, re.I):
        return None
    # An alternative list is a choice set, not ambiguity about which single
    # airport must be chosen. Every value still needs this exact source quote.
    if not re.search(r'\b(?:or|both|either|any)\b', quote, re.I):
        return None
    found = []
    for alias, codes in _AIRPORT_ALIASES.items():
        if re.search(r'\b' + re.escape(alias) + r'\b', quote, re.I):
            found.extend(code for code in codes if airport_record(code) is not None)
    found.extend(
        code for code in re.findall(r'\b[A-Z]{3}\b', quote)
        if code not in {'USA', 'NYC', 'CHI'} and airport_record(code) is not None
    )
    values = list(dict.fromkeys(found))
    return values if values and len(values) <= 20 else None


def clarification_field_supported(field, quote, domain, source_messages=None):
    """Require a real field mention before a new ambiguity replaces old state."""
    if not isinstance(quote, str) or not quote.strip():
        return False
    if source_messages:
        latest = source_messages[-1]
        if ((latest.get('reply_to') or {}).get('field') == field
                and _contains(quote, latest.get('content', ''))):
            return True
    patterns = {
        'max_total_cents': r'\$|\b(?:budget|price|dollars?|USD|spend|cost)\b',
        'origin_airports': r'\b(?:airport|depart|from|origin)\b',
        'destination_airports': r'\b(?:airport|arrive|arrival|destination|to)\b',
        'departure_date': _DATEISH_QUOTE.pattern,
        'checkin_date': _DATEISH_QUOTE.pattern,
        'checkout_date': _DATEISH_QUOTE.pattern,
        'departure_window': r'\b(?:morning|afternoon|evening|departure|takeoff|am|pm)\b|\d:\d',
        'nonstop': r'\b(?:non[- ]?stop|direct|connections?|layovers?)\b',
        'max_connections': r'\b(?:connections?|layovers?|stops?)\b',
        'max_duration_minutes': r'\b(?:duration|hours?|minutes?)\b',
        'cabin': r'\b(?:cabin|economy|business|first)\b',
        'refundable': r'\b(?:refund\w*|cancel\w*)\b',
        'breakfast': r'\bbreakfast\b',
        'accessible': r'\baccessib\w*\b',
        'rooms': r'\brooms?\b', 'adults': r'\b(?:adults?|guests?)\b',
        'trip_type': r'\b(?:one[- ]?way|round[- ]?trip|outbound)\b',
    }
    return bool(re.search(patterns.get(field, r'(?!)'), quote, re.I))


_BOOLEAN_WORDS = {
    'nonstop': r'non[- ]?stop', 'refundable': r'refundable',
    'breakfast': r'breakfast', 'accessible': r'accessib(?:le|ility)',
}
_NEGATIVE_PREFIX = re.compile(
    r'(?P<scope>(?:(?:do\s+not|does\s+not|don[’\']t|doesn[’\']t|'
    r'no\s+need|no\s+preference|not|no|without|avoid|non[- ]?)'
    r'(?:\s+(?:require|need|care|about|whether|if|for|get|buy|book|allow|want|a|an|the))*\s*)+)$', re.I)


def _restore_boolean_scope(data, message, source_messages=None):
    """Keep a real negation that sits immediately outside a short quote.

    A model must not quote only 'refundable' from 'non-refundable', or only
    'nonstop' from 'do not require nonstop'. The restored phrase is contiguous
    customer text, not generated evidence. Existing field polarity checks
    then reject reversed values or preserve explicit no-requirement wording.
    """
    result = deepcopy(data)
    texts = [m.get('content', '') for m in source_messages or []
             if m.get('role') in {'user', 'customer'}] or [message]
    for field in list(result['fields']):
        pattern = _BOOLEAN_WORDS.get(field)
        quote = result['sources'].get(field)
        if not pattern or not isinstance(quote, str) or not re.match(r'^(?:' + pattern + r')\b', quote, re.I):
            continue
        for text in reversed(texts):
            span = _source_span(quote, text)
            if span is None:
                continue
            occurrences = list(re.finditer(re.escape(span), text))
            # An identical short token used with conflicting scopes must not
            # be used to invent which statement the customer authorized.
            contexts = []
            for occurrence in occurrences:
                prefix = text[max(0, occurrence.start()-90):occurrence.start()]
                match = _NEGATIVE_PREFIX.search(prefix)
                contexts.append((match.group('scope') if match else '') + span)
            if contexts and all(context == contexts[0] for context in contexts):
                result['sources'][field] = contexts[0]
            elif any(context != span for context in contexts):
                result['fields'].pop(field, None)
                result['sources'].pop(field, None)
                result['clarifications'] = [c for c in result['clarifications'] if c['field'] != field]
                result['clarifications'].append({'field': field, 'source_quote': text, 'reason': 'ambiguous'})
            break
    return result
