"""Deterministic validation and source grounding for model-proposed drafts.

The model is allowed to propose language and values.  This module decides whether
those proposals are representable by a reviewed profile and whether each value is
actually supported by customer text.  It never authorizes a purchase.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation
import re

from app.profile_registry import get_profile, validate_fields


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
    "florida",
    "the state of florida",
    "new england",
    "the united states",
    "united states",
    "usa",
    "chicago",
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


def _contains(quote: str, text: str) -> bool:
    return quote.casefold() in text.casefold()


def _normalise_airports(value, key: str, quote: str) -> tuple[list[str], bool, list[str]]:
    if type(value) is not list or not value or any(type(item) is not str for item in value):
        raise GroundingFailure(f"{key} must contain airport codes or specific city names")
    airports: list[str] = []
    ambiguous = False
    unresolved: list[str] = []
    for raw in value:
        token = raw.strip()
        lower = token.casefold()
        if _IATA.fullmatch(token.upper()):
            code = token.upper()
            aliases = [name for name, codes in _AIRPORT_ALIASES.items() if code in codes]
            if not re.search(rf"\b{re.escape(code)}\b", quote, re.I) and not any(
                re.search(rf"\b{re.escape(alias)}\b", quote, re.I) for alias in aliases
            ):
                raise GroundingFailure(f"{key} value is not supported by its source quotation")
            airports.append(code)
        elif lower in _AIRPORT_ALIASES:
            airports.extend(_AIRPORT_ALIASES[lower])
        elif lower in _AMBIGUOUS_LOCATIONS:
            ambiguous = True
            unresolved.append(token)
        else:
            # A customer-named city that is outside the reviewed alias map is
            # a clarification need, not permission to invent an airport.
            ambiguous = True
            unresolved.append(token)
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


def _normalise_fields(domain: str, data: dict, message: str) -> dict:
    result = deepcopy(data)
    fields = result["fields"]
    sources = result["sources"]
    guidance: list[str] = []
    for key in list(fields):
        if key not in {"origin_airports", "destination_airports"}:
            continue
        quote = sources.get(key, "")
        if type(quote) is not str or not quote or not _contains(quote, message):
            raise GroundingFailure(f"{key} source quotation is not in customer text")
        normalised, ambiguous, unresolved = _normalise_airports(fields[key], key, quote)
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
            _, ambiguous, unresolved = _normalise_airports(values, key, quote)
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


def _date_in_quote(value: str, quote: str) -> bool:
    if value.casefold() in quote.casefold():
        return True
    try:
        expected = date.fromisoformat(value)
    except ValueError:
        return False
    natural = re.search(
        r"(?i)\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b",
        quote,
    )
    if not natural or natural.group(1).casefold() not in _MONTHS or not natural.group(3):
        return False
    try:
        return expected == date(int(natural.group(3)), _MONTHS[natural.group(1).casefold()], int(natural.group(2)))
    except ValueError:
        return False


def _airport_quote_supports(value: list[str], quote: str) -> bool:
    lower = quote.casefold()
    for airport in value:
        if airport.casefold() in lower:
            continue
        aliases = [name for name, codes in _AIRPORT_ALIASES.items() if airport in codes]
        if not any(alias in lower for alias in aliases):
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
    q = quote.casefold()
    reply_binding = _reply_binding(key, value, quote, domain, source_messages)
    if reply_binding is not None:
        # "No" answers a requirement question by declining the requirement;
        # it must not become a stored false preference.
        return reply_binding == "yes" and value is True
    terms = {
        "nonstop": (r"\bnon[- ]?stop\b", r"\b(?:zero|no|without(?:\s+any)?)\s+(?:connections?|stops?)\b"),
        "refundable": (r"\brefundable\b", r"\bfree\s+cancellation\b"),
        "breakfast": (r"\bbreakfast\b",),
        "accessible": (r"\baccessible\b",),
    }.get(key, ())
    if not terms or not any(re.search(pattern, q) for pattern in terms):
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
    # False means an explicit absence requirement. "I don't care" is not one.
    if re.search(r"\b(?:don't|do not|doesn't|does not)\s+(?:require|need|care)\b", q):
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
        if not _airport_quote_supports(value, quote):
            raise GroundingFailure(f"{key} value is not supported by its source quotation")
    elif key == "max_total_cents":
        if type(value) is not int or _money_cents(quote) != value:
            raise GroundingFailure("price value is not supported by its source quotation")
    elif key.endswith("date"):
        if not isinstance(value, str) or not _date_in_quote(value, quote):
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
    elif key == "cabin":
        if not isinstance(value, str) or value.casefold().replace("_", " ") not in quote.casefold():
            raise GroundingFailure("cabin value is not supported by its source quotation")
    elif isinstance(value, str):
        if value.casefold() not in quote.casefold():
            aliases = [name for name, codes in _AIRPORT_ALIASES.items() if value in codes]
            if not any(alias in quote.casefold() for alias in aliases):
                raise GroundingFailure(f"{key} value is not supported by its source quotation")


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
    if any(type(value) is not str or not value.strip() or len(value) > 2500 for value in data["unsupported"]):
        raise EnvelopeFailure("unsupported conditions must be nonempty strings")
    if type(data["explanation"]) is not str or not data["explanation"].strip() or len(data["explanation"]) > 1500:
        raise EnvelopeFailure("explanation must be a bounded string")
    # Old four-key provider responses may carry a legacy freeform marker. New
    # five-key responses must classify supported clarification explicitly.
    canonical = _remove_field_clarification_flags(data, message) if legacy else deepcopy(data)
    canonical = _normalise_fields(domain, canonical, message)
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


def bounded_unsupported(data: object, message: str | None = None) -> list[str]:
    """Extract only safe first-stage flags for retention during audit repair."""
    legacy = isinstance(data, dict) and "clarifications" not in data
    if not isinstance(data, dict) or not isinstance(data.get("unsupported"), list):
        values = []
    else:
        values = [item.strip() for item in data["unsupported"]
            if isinstance(item, str) and item.strip() and len(item) <= 2500
            and not (legacy and message is not None and _field_clarification_match(item, message))][:20]
    return list(dict.fromkeys(values))[:20]


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
                _, ambiguous, _ = _normalise_airports(fields[field], field, source or quote)
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
