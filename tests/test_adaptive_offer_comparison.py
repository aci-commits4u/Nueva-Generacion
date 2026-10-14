"""Read-only comparison previews for adaptive merchant inspection."""

def _flight_fields():
    return {
        "origin_airports": ["EWR"],
        "destination_airports": ["MCO", "MIA"],
        "departure_date": "2026-11-12",
        "nonstop": True,
    }


def test_connecting_offer_is_advisory_conflict_for_nonstop_requirement():
    from app.adaptive_intent import execute_tool

    result = execute_tool("inspect_offers", domain="flight", fields=_flight_fields())
    mismatch = next(row for row in result["offers"] if row["facts"]["connection_count"] == 3)
    comparison = mismatch["draft_comparison"]
    check = next(item for item in comparison["checks"] if item["check_id"] == "nonstop")

    assert comparison["status"] == "UNAPPROVED"
    assert comparison["advisory"] is True
    assert check["status"] == "CONFLICT"
    assert check["offer_value"] is False
    assert "advisory only" in check["message"]


def test_verified_route_accepts_any_customer_provided_arrival_airport():
    from app.adaptive_intent import execute_tool

    result = execute_tool("inspect_offers", domain="flight", fields=_flight_fields())
    match = next(row for row in result["offers"] if row["facts"]["connection_count"] == 0)
    check = next(
        item for item in match["draft_comparison"]["checks"]
        if item["check_id"] == "destination_airports"
    )
    assert check["status"] == "MATCH"
    assert check["offer_value"] == "MCO"


def test_missing_signed_fact_is_unknown_not_a_pass_or_approval():
    from app.adaptive_intent import execute_tool

    def missing_fact(_domain, _fields):
        return {
            "tool": "inspect_offers",
            "status": "ok",
            "read_only": True,
            "offers": [{
                "id": "offer-missing-nonstop",
                "offer_hash": "hash-missing-nonstop",
                "facts": {"origin": "EWR", "destination": "MCO"},
                "signed": True,
                "provenance": "merchant-signed checkout payload",
            }],
        }

    result = execute_tool(
        "inspect_offers",
        domain="flight",
        fields=_flight_fields(),
        tool_overrides={"inspect_offers": missing_fact},
    )
    comparison = result["offers"][0]["draft_comparison"]
    check = next(item for item in comparison["checks"] if item["check_id"] == "nonstop")
    assert comparison["status"] == "UNAPPROVED"
    assert check["status"] == "UNKNOWN"
    assert check["offer_value"] is None


def test_unverified_signature_hides_offer_values_and_stays_unknown():
    from app.adaptive_intent import execute_tool

    def forged(_domain, _fields):
        return {
            "tool": "inspect_offers",
            "status": "ok",
            "read_only": True,
            "offers": [{
                "id": "offer-forged",
                "offer_hash": "hash-forged",
                "facts": {"nonstop": False},
                "signed": False,
                "provenance": "untrusted merchant text",
            }],
        }

    result = execute_tool(
        "inspect_offers",
        domain="flight",
        fields=_flight_fields(),
        tool_overrides={"inspect_offers": forged},
    )
    comparison = result["offers"][0]["draft_comparison"]
    checks = {item["check_id"]: item for item in comparison["checks"]}
    assert comparison["status"] == "UNAPPROVED"
    assert checks["nonstop"]["status"] == "UNKNOWN"
    assert checks["nonstop"]["offer_value"] is None


def test_rules_engine_bool_type_is_strict():
    from app.adaptive_intent import execute_tool

    def malformed_bool(_domain, _fields):
        return {
            "tool": "inspect_offers", "status": "ok", "read_only": True,
            "offers": [{
                "id": "offer-int-bool", "offer_hash": "hash-int-bool",
                "facts": {"nonstop": 1}, "signed": True,
                "provenance": "merchant-signed checkout payload",
            }],
        }

    result = execute_tool(
        "inspect_offers", domain="flight", fields=_flight_fields(),
        tool_overrides={"inspect_offers": malformed_bool},
    )
    check = next(item for item in result["offers"][0]["draft_comparison"]["checks"]
                 if item["check_id"] == "nonstop")
    assert check["status"] == "UNKNOWN"
    assert check["offer_value"] is None


def test_rules_engine_rejects_malformed_signed_date():
    from app.adaptive_intent import execute_tool

    def malformed_date(_domain, _fields):
        return {
            "tool": "inspect_offers", "status": "ok", "read_only": True,
            "offers": [{
                "id": "offer-bad-date", "offer_hash": "hash-bad-date",
                "facts": {"departure_date": "2026-99-99"}, "signed": True,
                "provenance": "merchant-signed checkout payload",
            }],
        }

    result = execute_tool(
        "inspect_offers", domain="flight", fields=_flight_fields(),
        tool_overrides={"inspect_offers": malformed_date},
    )
    check = next(item for item in result["offers"][0]["draft_comparison"]["checks"]
                 if item["check_id"] == "departure_date")
    assert check["status"] == "UNKNOWN"
    assert check["offer_value"] is None


def test_rules_engine_keeps_string_equality_exact():
    from app.adaptive_intent import execute_tool

    fields = dict(_flight_fields(), cabin="Economy")

    def case_variant(_domain, _fields):
        return {
            "tool": "inspect_offers", "status": "ok", "read_only": True,
            "offers": [{
                "id": "offer-case", "offer_hash": "hash-case",
                "facts": {"cabin": "economy"}, "signed": True,
                "provenance": "merchant-signed checkout payload",
            }],
        }

    result = execute_tool(
        "inspect_offers", domain="flight", fields=fields,
        tool_overrides={"inspect_offers": case_variant},
    )
    check = next(item for item in result["offers"][0]["draft_comparison"]["checks"]
                 if item["check_id"] == "cabin")
    assert check["status"] == "CONFLICT"
    assert check["offer_value"] == "economy"
