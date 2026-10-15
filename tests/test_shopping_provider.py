from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from app import shopping_provider as provider


def approved(**overrides):
    fields = {
        "max_total_cents": 29_950,
        "origin_airports": ["WAW"],
        "destination_airports": ["BER"],
        "departure_date": "2027-02-10",
        "nonstop": True,
    }
    fields.update(overrides)
    return {"domain": "flight", "fields": fields}


def itinerary(
    *,
    price=299.50,
    booking_url="https://kiwi.com/u/demo",
    stops=0,
    departure="2027-02-10T09:25:00",
    arrival="2027-02-10T10:45:00",
    country="Poland",
):
    return {
        "id": "demo-1",
        "price": price,
        "priceFormatted": f"{price} USD",
        "bookingUrl": booking_url,
        "outbound": {
            "from": "WAW",
            "to": "BER",
            "departureTime": departure,
            "arrivalTime": arrival,
            "durationSeconds": 4800,
            "stops": stops,
            "route": ["WAW", "BER"] if stops == 0 else ["WAW", "VIE", "BER"],
            "cabinClass": "Economy",
            "segments": [
                {
                    "from": "WAW",
                    "to": "BER",
                    "fromCountry": country,
                    "toCountry": "Germany",
                    "departureTime": departure,
                    "arrivalTime": arrival,
                    "durationSeconds": 4800,
                    "carrier": "LO",
                    "carrierName": "LOT Polish Airlines",
                    "flightNumber": "LO387",
                    "cabinClass": "Economy",
                }
            ],
        },
        "inbound": None,
    }


def payload(*items, currency="USD"):
    return {
        "query": "WAW → BER",
        "currency": currency,
        "itineraries": list(items),
        "resultsCount": len(items),
    }


def install_stub(monkeypatch, response, calls=None):
    calls = calls if calls is not None else []

    async def fake(arguments):
        calls.append(arguments)
        if isinstance(response, BaseException):
            raise response
        return response

    monkeypatch.setattr(provider, "_call_search_tool", fake)
    return calls


def test_normalizes_flat_contract_and_keeps_external_unverified(monkeypatch):
    calls = install_stub(monkeypatch, payload(itinerary(price=299.50)))

    result = provider.search_flights(approved())

    assert len(calls) == 1
    assert calls[0]["flyFrom"] == "WAW"
    assert calls[0]["flyTo"] == "BER"
    assert calls[0]["departureDate"] == "10/02/2027"
    assert calls[0]["max_sector_stopovers"] == 0
    # 29,950 cents becomes an inclusive provider filter of $300, then the
    # adapter performs the exact local cents comparison.
    assert calls[0]["price_to"] == 300
    row = result["results"][0]
    assert result["status"] == "external_unverified"
    assert row["price_cents"] == 29_950
    assert row["currency"] == "USD"
    assert row["carrier"] == "LO"
    assert row["origin"] == "WAW"
    assert row["destination"] == "BER"
    assert row["duration_minutes"] == 80
    assert row["connections"] == 0
    assert row["booking_url"] == "https://kiwi.com/u/demo"
    assert row["verification_status"] == "external_unverified"
    assert row["advisory_checks"]
    assert "checkout_jwt" not in row
    assert "merchant_signature" not in row
    assert "PASS" not in {check["status"] for check in row["advisory_checks"]}


def test_local_money_filter_drops_quote_above_exact_cents(monkeypatch):
    install_stub(monkeypatch, payload(itinerary(price=299.51)))

    result = provider.search_flights(approved())

    assert result["results"] == []


def test_non_usd_provider_response_is_rejected_for_usd_requirements(monkeypatch):
    install_stub(monkeypatch, payload(itinerary(price=121), currency="EUR"))

    with pytest.raises(provider.ShoppingProviderError) as exc:
        provider.search_flights(approved())
    assert exc.value.code == "provider_currency_mismatch"


def test_human_readable_cabin_labels_are_normalized(monkeypatch):
    install_stub(monkeypatch, payload(itinerary()))

    result = provider.search_flights(approved(cabin="economy"))

    row = result["results"][0]
    assert row["facts"]["cabin"] == "economy"
    cabin_check = next(check for check in row["advisory_checks"] if check["check_id"] == "cabin")
    assert cabin_check["status"] == "MATCH"


def test_booking_url_is_allowlisted_and_untrusted_country_is_data(monkeypatch):
    install_stub(
        monkeypatch,
        payload(itinerary(booking_url="https://attacker.example/collect?country=Poland", country="Neverland")),
    )

    result = provider.search_flights(approved())
    row = result["results"][0]

    assert row["booking_url"] is None
    assert row["outbound"]["segments"][0]["fromCountry"] == "Neverland"
    assert row["verification_status"] == "external_unverified"


def test_missing_provider_fields_are_retained_as_unknown(monkeypatch):
    raw = itinerary()
    del raw["outbound"]["departureTime"]
    del raw["outbound"]["stops"]
    install_stub(monkeypatch, payload(raw))

    row = provider.search_flights(approved())["results"][0]

    assert row["departure_at"] is None
    assert row["connections"] is None
    checks = {check["check_id"]: check for check in row["advisory_checks"]}
    assert checks["departure_date"]["status"] == "UNKNOWN"
    assert checks["nonstop"]["status"] == "UNKNOWN"


def test_all_airport_scope_combinations_are_queried(monkeypatch):
    calls = install_stub(monkeypatch, payload())

    result = provider.search_flights(
        approved(origin_airports=["WAW", "KRK"], destination_airports=["BER", "MUC"]),
    )

    assert len(calls) == 4
    assert result["query"]["query_count"] == 4
    assert {call["flyFrom"] for call in calls} == {"WAW", "KRK"}
    assert {call["flyTo"] for call in calls} == {"BER", "MUC"}


def test_scope_limit_is_actionable_and_does_not_silently_choose_first(monkeypatch):
    calls = install_stub(monkeypatch, payload())

    with pytest.raises(provider.ShoppingProviderError) as exc:
        provider.search_flights(
            approved(
                origin_airports=["WAW", "KRK", "GDN"],
                destination_airports=["BER", "MUC", "FRA", "HAM", "DUS"],
            ),
        )

    assert exc.value.code == "scope_too_broad"
    assert calls == []


def test_date_range_uses_inclusive_provider_end_and_discrete_dates_are_bounded(monkeypatch):
    calls = install_stub(monkeypatch, payload())
    provider.search_flights(approved(departure_date={"start": "2027-02-10", "end": "2027-02-12"}))
    assert calls[0]["departureDate"] == "10/02/2027"
    assert calls[0]["departureDateTo"] == "12/02/2027"

    with pytest.raises(provider.ShoppingProviderError) as exc:
        provider.search_flights(
            approved(departure_date={"dates": [f"2027-02-{day:02d}" for day in range(1, 14)]})
        )
    assert exc.value.code == "scope_too_broad"


def test_optional_requested_scope_must_be_approved_member(monkeypatch):
    calls = install_stub(monkeypatch, payload())
    with pytest.raises(provider.ShoppingProviderError) as exc:
        provider.search_flights(approved(), origin_airports=["WAW", "LHR"])
    assert exc.value.code == "invalid_scope"
    assert calls == []


def test_timeout_is_stable_and_no_retry(monkeypatch):
    calls = install_stub(monkeypatch, TimeoutError("network details must not escape"))
    with pytest.raises(provider.ShoppingProviderError) as exc:
        provider.search_flights(approved())
    assert exc.value.code == "provider_timeout"
    assert len(calls) == 1


def test_structured_content_precedes_text_fallback():
    class Content:
        text = '{"currency":"USD","itineraries":[]}'

    class Response:
        isError = False
        structuredContent = {"currency": "USD", "itineraries": [{"id": "structured"}]}
        content = [Content()]

    parsed = provider._structured_result(Response())
    assert parsed["itineraries"][0]["id"] == "structured"


def test_text_fallback_parses_json():
    class Content:
        text = '{"currency":"USD","itineraries":[]}'

    class Response:
        isError = False
        structuredContent = None
        content = [Content()]

    assert provider._structured_result(Response())["itineraries"] == []


def test_search_is_sync_only_for_bounded_sdk_entrypoint(monkeypatch):
    install_stub(monkeypatch, payload())

    async def inside_loop():
        with pytest.raises(provider.ShoppingProviderError) as exc:
            provider.search_flights(approved())
        return exc.value.code

    assert asyncio.run(inside_loop()) == "sync_context_required"
