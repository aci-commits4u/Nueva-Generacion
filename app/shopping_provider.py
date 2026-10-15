"""Read-only live flight discovery through Kiwi.com's MCP server.

This module deliberately stops at discovery.  Kiwi results are external price
quotes and itinerary observations; they are not merchant-signed offers and
must never be turned into a Verifiable Intent checkout or purchase decision.
The application can compare the normalized facts to approved requirements as
an advisory convenience, but the normal signed-offer rules remain authoritative.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP
import json
import math
import re
from typing import Any
from urllib.parse import urlparse

from mcp import ClientSession
from mcp.client.streamable_http import (
    create_mcp_http_client,
    httpx2,
    streamable_http_client,
)

from app.profile_registry import get_profile, valid_date_choice, valid_time
from app.rules_engine import evaluate


KIWI_MCP_ENDPOINT = "https://mcp.kiwi.com"
KIWI_SEARCH_TOOL = "search-flight"
KIWI_PROVIDER = "kiwi"
MAX_QUERY_COMBINATIONS = 12
MAX_RESULTS = 10
MAX_OUTPUT_BYTES = 250_000
MCP_TIMEOUT_SECONDS = 25.0
_IATA_RE = re.compile(r"\A[A-Z]{3}\Z")
_ISO_DATE_RE = re.compile(r"\A\d{4}-\d{2}-\d{2}\Z")
_CABIN_TO_KIWI = {
    "economy": "M",
    "premium_economy": "W",
    "premium economy": "W",
    "business": "C",
    "first": "F",
}
_KIWI_TO_CABIN = {
    "m": "economy",
    "w": "premium_economy",
    "c": "business",
    "f": "first",
    # Kiwi's documented/observed response uses both booking codes and human
    # labels.  Preserve a known cabin requirement when the latter is returned
    # so the advisory comparison does not turn a trustworthy provider field
    # into UNKNOWN.
    "economy": "economy",
    "premium economy": "premium_economy",
    "premium_economy": "premium_economy",
    "business": "business",
    "first": "first",
}


class ShoppingProviderError(RuntimeError):
    """A safe, stable error that can be shown by the shopping endpoint."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def _as_mapping(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        if isinstance(dumped, Mapping):
            return dumped
    return None


def _approved_fields(approved: Mapping[str, Any] | Any) -> dict[str, Any]:
    value = _as_mapping(approved)
    if value is None:
        raise ShoppingProviderError("invalid_requirements", "Approved requirements must be an object.")
    domain = value.get("domain", "flight")
    if domain != "flight":
        raise ShoppingProviderError("unsupported_domain", "Live shopping discovery currently supports flights only.")
    nested = value.get("fields", value)
    if not isinstance(nested, Mapping):
        raise ShoppingProviderError("invalid_requirements", "Approved flight requirements must contain fields.")
    fields = dict(nested)
    profile = get_profile("flight")
    unknown = sorted(set(fields) - set(profile["fields"]))
    if unknown:
        raise ShoppingProviderError(
            "invalid_requirements",
            "Unsupported approved flight field(s): " + ", ".join(unknown),
        )
    required = ("origin_airports", "destination_airports", "departure_date", "max_total_cents")
    missing = [key for key in required if fields.get(key) is None]
    if missing:
        raise ShoppingProviderError(
            "missing_requirements",
            "Approve these flight details before searching: " + ", ".join(missing) + ".",
        )
    try:
        if not isinstance(fields["max_total_cents"], int) or isinstance(fields["max_total_cents"], bool):
            raise ValueError
        if fields["max_total_cents"] < 0:
            raise ValueError
        if not valid_date_choice(fields["departure_date"]):
            raise ValueError
    except (KeyError, ValueError, TypeError):
        raise ShoppingProviderError("invalid_requirements", "The approved flight date or price is invalid.")
    return fields


def _airport_set(value: Any, field: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ShoppingProviderError("invalid_scope", f"{field} must be a list of IATA airport codes.")
    items = list(value)
    if not items or len(items) > 12 or any(not isinstance(item, str) or not _IATA_RE.fullmatch(item) for item in items):
        raise ShoppingProviderError("invalid_scope", f"{field} must contain 1–12 uppercase IATA codes.")
    if len(set(items)) != len(items):
        raise ShoppingProviderError("invalid_scope", f"{field} contains duplicate airport codes.")
    return items


def _scoped_airports(fields: Mapping[str, Any], key: str, requested: Sequence[str] | None) -> list[str]:
    approved = _airport_set(fields[key], key)
    if requested is None:
        return approved
    chosen = _airport_set(requested, key)
    if not set(chosen).issubset(approved):
        raise ShoppingProviderError(
            "invalid_scope",
            f"The requested {key} scope must stay within the approved airport set.",
        )
    return chosen


def _iso_dates(value: Any) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, Mapping) and set(value) == {"start", "end"}:
        values = [value["start"], value["end"]]
        try:
            start = date.fromisoformat(value["start"])
            end = date.fromisoformat(value["end"])
        except (TypeError, ValueError):
            raise ShoppingProviderError("invalid_requirements", "The approved date range is invalid.")
        if start > end:
            raise ShoppingProviderError("invalid_requirements", "The approved date range is reversed.")
        return [value["start"]]  # one Kiwi range query; caller handles end separately
    elif isinstance(value, Mapping) and set(value) == {"dates"}:
        values = value["dates"]
    else:
        raise ShoppingProviderError("invalid_requirements", "Use an exact date, a date range, or date alternatives.")
    if not isinstance(values, list):
        values = list(values)
    if any(not isinstance(item, str) or not _ISO_DATE_RE.fullmatch(item) for item in values):
        raise ShoppingProviderError("invalid_requirements", "Approved dates must use YYYY-MM-DD.")
    try:
        parsed = [date.fromisoformat(item) for item in values]
    except ValueError:
        raise ShoppingProviderError("invalid_requirements", "One approved date does not exist.")
    if len(set(values)) != len(values):
        raise ShoppingProviderError("invalid_requirements", "Approved dates must be unique.")
    if isinstance(value, Mapping) and set(value) == {"dates"} and len(values) > MAX_QUERY_COMBINATIONS:
        raise ShoppingProviderError(
            "scope_too_broad",
            "Choose 12 or fewer date and airport combinations for a live search.",
        )
    return values


def _date_queries(value: Any) -> list[tuple[str, str | None]]:
    """Return Kiwi's exact-date or inclusive-range query pairs."""
    if isinstance(value, str):
        dates = _iso_dates(value)
        return [(dates[0], None)]
    if isinstance(value, Mapping) and set(value) == {"start", "end"}:
        dates = _iso_dates(value)
        return [(dates[0], value["end"])]
    dates = _iso_dates(value)
    return [(item, None) for item in dates]


def _kiwi_date(value: str) -> str:
    return datetime.strptime(value, "%Y-%m-%d").strftime("%d/%m/%Y")


def _query_args(
    fields: Mapping[str, Any],
    origin: str,
    destination: str,
    departure: str,
    departure_to: str | None,
    adults: int,
) -> dict[str, Any]:
    if type(adults) is not int or not 1 <= adults <= 9:
        raise ShoppingProviderError("invalid_passengers", "Adults must be an integer from 1 to 9.")
    args: dict[str, Any] = {
        "flyFrom": origin,
        "flyTo": destination,
        "departureDate": _kiwi_date(departure),
        "departureDateFlexDays": 0,
        "departureDateTo": _kiwi_date(departure_to) if departure_to else None,
        "adults": adults,
        "children": 0,
        "infants": 0,
        "cabinClass": _CABIN_TO_KIWI.get(str(fields.get("cabin", "")).strip().casefold()) if fields.get("cabin") else None,
        "currency": "USD",
        "locale": "en",
        "allow_self_transfer": False,
        "allow_overnight_stopovers": False,
        "allow_diff_airport_connection": False,
        "sort": "price",
    }
    if fields.get("nonstop") is True:
        args["max_sector_stopovers"] = 0
    elif fields.get("max_connections") is not None:
        args["max_sector_stopovers"] = fields["max_connections"]
    else:
        args["max_sector_stopovers"] = None
    max_cents = fields.get("max_total_cents")
    args["price_to"] = int((Decimal(max_cents) / Decimal(100)).to_integral_value(rounding=ROUND_CEILING))
    return {key: val for key, val in args.items() if val is not None}


def _safe_booking_url(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) > 2048:
        return None
    try:
        parsed = urlparse(value)
    except ValueError:
        return None
    host = (parsed.hostname or "").casefold().rstrip(".")
    if parsed.scheme != "https" or not host or not (host == "kiwi.com" or host.endswith(".kiwi.com")):
        return None
    if parsed.username or parsed.password or parsed.fragment:
        return None
    return value


def _number(value: Any) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite() or parsed < 0:
        return None
    return parsed


def _money_cents(value: Any) -> int | None:
    parsed = _number(value)
    if parsed is None:
        return None
    return int((parsed * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _text(value: Any, maximum: int = 240) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return value[:maximum]


def _iata(value: Any) -> str | None:
    return value if isinstance(value, str) and _IATA_RE.fullmatch(value) else None


def _segment(segment: Any) -> dict[str, Any]:
    data = _as_mapping(segment) or {}
    keys = (
        "from", "to", "fromCity", "toCity", "fromName", "toName", "fromCountry", "toCountry",
        "departureTime", "arrivalTime", "durationSeconds", "carrier", "carrierName", "flightNumber", "cabinClass",
    )
    result: dict[str, Any] = {}
    for key in keys:
        value = data.get(key)
        if key == "durationSeconds":
            result[key] = value if type(value) is int and 0 <= value <= 172800 else None
        elif key in {"from", "to"}:
            result[key] = _iata(value)
        elif key in {"carrier", "flightNumber"}:
            result[key] = _text(value, 32)
        else:
            result[key] = _text(value)
    return result


def _leg(leg: Any) -> dict[str, Any] | None:
    data = _as_mapping(leg)
    if not data:
        return None
    route = data.get("route")
    route_values = [item for item in route if isinstance(item, str) and _IATA_RE.fullmatch(item)] if isinstance(route, list) else []
    segments = [_segment(item) for item in data.get("segments", [])[:30]] if isinstance(data.get("segments"), list) else []
    stops = data.get("stops")
    if type(stops) is not int or stops < 0 or stops > 30:
        # Do not infer a checkout-grade connection fact from a partial provider
        # response.  The signed merchant offer, when available, owns the
        # deterministic value used for enforcement.
        stops = None
    technical_stops = data.get("technicalStops")
    if not ((type(technical_stops) is int and 0 <= technical_stops <= 30) or type(technical_stops) is bool):
        technical_stops = None
    return {
        "from": _iata(data.get("from")),
        "to": _iata(data.get("to")),
        "departure_time": _text(data.get("departureTime")),
        "arrival_time": _text(data.get("arrivalTime")),
        "duration_seconds": data.get("durationSeconds") if type(data.get("durationSeconds")) is int and data.get("durationSeconds") >= 0 else None,
        "connection_count": stops,
        "technical_stops": technical_stops,
        "route": route_values,
        "cabin": _KIWI_TO_CABIN.get(str(data.get("cabinClass", "")).casefold()) if data.get("cabinClass") else None,
        "segments": segments,
    }


def _raw_facts(outbound: Mapping[str, Any] | None, inbound: Mapping[str, Any] | None, price_cents: int | None, currency: str | None) -> dict[str, Any]:
    outbound = outbound or {}
    departure = outbound.get("departure_time")
    duration = outbound.get("duration_seconds")
    connections = outbound.get("connection_count")
    technical_stops = outbound.get("technical_stops")
    if type(technical_stops) is bool:
        technical_stops = int(technical_stops)
    facts: dict[str, Any] = {
        "origin": outbound.get("from"),
        "destination": outbound.get("to"),
        "departure_date": departure[:10] if isinstance(departure, str) and len(departure) >= 10 else None,
        "departure_local": departure[11:16] if isinstance(departure, str) and len(departure) >= 16 and valid_time(departure[11:16]) else None,
        "duration_minutes": math.ceil(duration / 60) if type(duration) is int and duration >= 0 else None,
        "connection_count": connections,
        # Kiwi's stops field proves connections, but not the absence of
        # technical stops.  A zero-stop result therefore stays unknown for a
        # strict nonstop requirement unless a provider field explicitly says so.
        "nonstop": (
            False if type(connections) is int and connections > 0
            else (connections == 0 and technical_stops == 0 if type(connections) is int and type(technical_stops) is int else None)
        ),
        "cabin": outbound.get("cabin"),
        "trip_type": "one_way" if inbound is None else None,
        "total_cents": price_cents,
        "currency": currency,
    }
    return facts


def _advisory_checks(fields: Mapping[str, Any], facts: Mapping[str, Any]) -> list[dict[str, Any]]:
    profile = get_profile("flight")
    checks = evaluate(profile, dict(fields), dict(facts)).get("checks", [])
    output = []
    for check in checks:
        status = check.get("status")
        output.append({
            "check_id": check.get("check_id"),
            "requirement": check.get("requirement"),
            "offer_value": check.get("offer_value") if status != "missing" else None,
            "status": {"pass": "MATCH", "fail": "CONFLICT", "missing": "UNKNOWN"}.get(status, "UNKNOWN"),
            "message": "Advisory comparison only; the external quote is not a signed offer.",
        })
    return output


def _normalize_result(item: Any, currency: str | None, retrieved_at: str, fields: Mapping[str, Any]) -> dict[str, Any] | None:
    data = _as_mapping(item)
    if not data:
        return None
    price = _money_cents(data.get("price"))
    outbound = _leg(data.get("outbound"))
    inbound = _leg(data.get("inbound"))
    if outbound is None:
        return None
    facts = _raw_facts(outbound, inbound, price, currency)
    max_cents = fields.get("max_total_cents")
    if price is not None and type(max_cents) is int and price > max_cents:
        return None
    booking_url = _safe_booking_url(data.get("bookingUrl"))
    raw_id = data.get("id")
    result_id = _text(raw_id, 160) or f"{facts.get('origin','')}-{facts.get('destination','')}-{facts.get('departure_date','')}"
    return {
        "record_type": "external_discovery",
        "id": result_id,
        "provider": KIWI_PROVIDER,
        # These flat fields are the stable UI/API contract.  The nested
        # itinerary and facts below retain the richer provider observation for
        # advisory comparison without making callers understand Kiwi's shape.
        "price_cents": price,
        "currency": currency or "USD",
        "carrier": (outbound.get("segments") or [{}])[0].get("carrier") if outbound.get("segments") else None,
        "origin": facts.get("origin"),
        "destination": facts.get("destination"),
        "departure_at": outbound.get("departure_time"),
        "arrival_at": outbound.get("arrival_time"),
        "duration_minutes": facts.get("duration_minutes"),
        "connections": facts.get("connection_count"),
        "verification_status": "external_unverified",
        "verified": False,
        "price_quote": {
            "amount_cents": price,
            "currency": currency or "USD",
            "display": _text(data.get("priceFormatted")),
        },
        "booking_url": booking_url,
        "outbound": outbound,
        "inbound": inbound,
        "facts": facts,
        "advisory_checks": _advisory_checks(fields, facts),
        "source_provenance": {
            "provider": KIWI_PROVIDER,
            "endpoint": KIWI_MCP_ENDPOINT,
            "tool": KIWI_SEARCH_TOOL,
            "retrieved_at": retrieved_at,
            "merchant_signature": None,
        },
    }


def _structured_result(result: Any) -> Mapping[str, Any]:
    if bool(getattr(result, "isError", False)):
        raise ShoppingProviderError("provider_error", "Kiwi could not complete the flight search.")
    structured = getattr(result, "structuredContent", None)
    structured_map = _as_mapping(structured)
    if structured_map is not None:
        return structured_map
    contents = getattr(result, "content", None)
    if isinstance(contents, list):
        for content in contents:
            text = getattr(content, "text", None)
            if text is None and isinstance(content, Mapping):
                text = content.get("text")
            if isinstance(text, str):
                try:
                    parsed = json.loads(text)
                except (TypeError, json.JSONDecodeError):
                    continue
                parsed_map = _as_mapping(parsed)
                if parsed_map is not None:
                    return parsed_map
    raise ShoppingProviderError("invalid_provider_response", "Kiwi returned an unreadable flight response.")


async def _call_search_tool(arguments: dict[str, Any]) -> Mapping[str, Any]:
    """Call the one allowlisted read-only MCP tool, once, with a hard timeout."""
    timeout = httpx2.Timeout(MCP_TIMEOUT_SECONDS, connect=5.0, read=MCP_TIMEOUT_SECONDS, write=5.0, pool=5.0)
    try:
        async with create_mcp_http_client(timeout=timeout) as client:
            async with streamable_http_client(KIWI_MCP_ENDPOINT, http_client=client) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream, read_timeout_seconds=MCP_TIMEOUT_SECONDS) as session:
                    await session.initialize()
                    response = await session.call_tool(KIWI_SEARCH_TOOL, arguments, read_timeout_seconds=MCP_TIMEOUT_SECONDS)
                    return _structured_result(response)
    except ShoppingProviderError:
        raise
    except TimeoutError:
        raise ShoppingProviderError("provider_timeout", "Kiwi did not respond within 25 seconds.")
    except Exception as exc:  # sanitize transport/SDK details at the boundary
        name = type(exc).__name__.casefold()
        if "timeout" in name:
            raise ShoppingProviderError("provider_timeout", "Kiwi did not respond within 25 seconds.")
        raise ShoppingProviderError("provider_unavailable", "Kiwi flight discovery is temporarily unavailable.")


async def _call_searches(arguments_list: Sequence[dict[str, Any]]) -> list[Mapping[str, Any]]:
    """Run the bounded set concurrently so a dead provider cannot multiply latency."""
    tasks = [asyncio.create_task(_call_search_tool(arguments)) for arguments in arguments_list]
    try:
        responses = await asyncio.wait_for(asyncio.gather(*tasks), timeout=MCP_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        for task in tasks:
            task.cancel()
        raise ShoppingProviderError("provider_timeout", "Kiwi did not respond within 25 seconds.")
    except ShoppingProviderError:
        for task in tasks:
            if not task.done():
                task.cancel()
        raise
    except TimeoutError:
        raise ShoppingProviderError("provider_timeout", "Kiwi did not respond within 25 seconds.")
    except Exception:
        raise ShoppingProviderError("provider_unavailable", "Kiwi flight discovery is temporarily unavailable.")
    return list(responses)


def _run(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    close = getattr(coro, "close", None)
    if close is not None:
        close()
    raise ShoppingProviderError("sync_context_required", "Use the synchronous shopping adapter outside an async event loop.")


def _invoke_search(arguments: dict[str, Any]) -> Mapping[str, Any]:
    """Normalize transport failures even when a test/provider shim is used."""
    try:
        result = _run(_call_search_tool(arguments))
    except ShoppingProviderError:
        raise
    except TimeoutError:
        raise ShoppingProviderError("provider_timeout", "Kiwi did not respond within 25 seconds.")
    except Exception as exc:
        if "timeout" in type(exc).__name__.casefold():
            raise ShoppingProviderError("provider_timeout", "Kiwi did not respond within 25 seconds.")
        raise ShoppingProviderError("provider_unavailable", "Kiwi flight discovery is temporarily unavailable.")
    if not isinstance(result, Mapping):
        raise ShoppingProviderError("invalid_provider_response", "Kiwi returned an invalid flight response.")
    return result


def search_flights(
    approved: Mapping[str, Any] | Any,
    *,
    adults: int = 1,
    origin_airports: Sequence[str] | None = None,
    destination_airports: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Search all approved airport/date combinations via Kiwi's read-only MCP.

    The returned records are explicitly ``external_discovery`` and
    ``external_unverified``.  They contain no checkout JWT, merchant signature,
    VI chain, PASS status, exception authority, or purchase capability.
    """
    fields = _approved_fields(approved)
    origins = _scoped_airports(fields, "origin_airports", origin_airports)
    destinations = _scoped_airports(fields, "destination_airports", destination_airports)
    date_queries = _date_queries(fields["departure_date"])
    combination_count = len(origins) * len(destinations) * len(date_queries)
    if combination_count > MAX_QUERY_COMBINATIONS:
        raise ShoppingProviderError(
            "scope_too_broad",
            f"This search has {combination_count} airport/date combinations. Choose 12 or fewer approved options.",
        )
    if type(adults) is not int or not 1 <= adults <= 9:
        raise ShoppingProviderError("invalid_passengers", "Adults must be an integer from 1 to 9.")
    calls: list[dict[str, Any]] = []
    for origin in origins:
        for destination in destinations:
            for departure, departure_to in date_queries:
                calls.append(_query_args(fields, origin, destination, departure, departure_to, adults))
    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    output: list[dict[str, Any]] = []
    payloads = _run(_call_searches(calls))
    for payload in payloads:
        if _json_size(payload) > MAX_OUTPUT_BYTES:
            raise ShoppingProviderError("provider_response_too_large", "Kiwi returned too much flight data.")
        if payload.get("error"):
            raise ShoppingProviderError("provider_error", "Kiwi could not complete the flight search.")
        currency = payload.get("currency") if isinstance(payload.get("currency"), str) else "USD"
        if currency.upper() != "USD":
            raise ShoppingProviderError("provider_currency_mismatch", "Kiwi returned a non-USD quote for a USD-approved request.")
        currency = "USD"
        itineraries = payload.get("itineraries")
        if itineraries is None:
            itineraries = []
        if not isinstance(itineraries, list):
            raise ShoppingProviderError("invalid_provider_response", "Kiwi returned invalid itinerary data.")
        for itinerary in itineraries:
            normalized = _normalize_result(itinerary, currency, retrieved_at, fields)
            if normalized is not None:
                output.append(normalized)
                if len(output) >= MAX_RESULTS:
                    break
        if len(output) >= MAX_RESULTS:
            break
    response = {
        "record_type": "external_discovery_result",
        "status": "external_unverified",
        "provider": KIWI_PROVIDER,
        "retrieved_at": retrieved_at,
        "currency": "USD",
        "query": {
            "origins": origins,
            "destinations": destinations,
            "date_queries": [
                {"departure": departure, "departure_to": departure_to}
                for departure, departure_to in date_queries
            ],
            "adults": adults,
            "query_count": len(calls),
        },
        "query_summary": {
            "origins": origins,
            "destinations": destinations,
            "date_queries": [
                {"departure": departure, "departure_to": departure_to}
                for departure, departure_to in date_queries
            ],
            "adults": adults,
            "query_count": len(calls),
        },
        "results": output,
        "not_verified": "These are live external price quotes. They are not merchant-signed offers and cannot approve or execute a purchase.",
        "not_verified_notice": "These are live external price quotes. They are not merchant-signed offers and cannot approve or execute a purchase.",
    }
    if _json_size(response) > MAX_OUTPUT_BYTES:
        raise ShoppingProviderError("provider_response_too_large", "The normalized flight response is too large.")
    return response


def _json_size(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    except (TypeError, ValueError):
        return MAX_OUTPUT_BYTES + 1


__all__ = ["KIWI_MCP_ENDPOINT", "KIWI_SEARCH_TOOL", "ShoppingProviderError", "search_flights"]
