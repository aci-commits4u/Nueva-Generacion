"""Bounded recovery for parseable live proposals with mixed field quality."""

from app.ai_grounding import recover_grounded_parts


def envelope(fields, sources, *, unsupported=None, clarifications=None, explanation="Review."):
    return {
        "fields": fields,
        "sources": sources,
        "unsupported": [] if unsupported is None else unsupported,
        "clarifications": [] if clarifications is None else clarifications,
        "explanation": explanation,
    }


def test_partial_recovery_keeps_valid_route_and_date_and_compiles_wrong_money():
    message = "Fly from EWR to CPH on 2026-11-12 under $1200, with a checked bag."
    result = recover_grounded_parts(
        "flight",
        message,
        envelope(
            {
                "origin_airports": ["EWR"],
                "destination_airports": ["CPH"],
                "departure_date": "2026-11-12",
                "max_total_cents": 120000,
            },
            {
                "origin_airports": "EWR",
                "destination_airports": "CPH",
                "departure_date": "2026-11-12",
                "max_total_cents": "under $1200",
            },
            unsupported=["checked bag"],
        ),
        source_messages=[{"role": "user", "content": message}],
    )

    assert result is not None
    assert result["fields"] == {
        "origin_airports": ["EWR"],
        "destination_airports": ["CPH"],
        "departure_date": "2026-11-12",
        "max_total_cents": 119999,
    }
    assert result["sources"]["max_total_cents"] == "under $1200"
    assert result["unsupported"] == ["checked bag"]
    assert result["recovery"]["rejected_fields"][0]["field"] == "max_total_cents"
    assert result["recovery"]["rejected_fields"][0]["source_grounded"] is True


def test_wrong_boolean_polarity_becomes_source_linked_clarification():
    message = "A non-refundable flight from EWR under $300."
    result = recover_grounded_parts(
        "flight",
        message,
        envelope(
            {"origin_airports": ["EWR"], "refundable": True, "max_total_cents": 29999},
            {
                "origin_airports": "EWR",
                "refundable": "non-refundable",
                "max_total_cents": "under $300",
            },
        ),
    )

    assert result is not None
    assert "refundable" not in result["fields"]
    assert result["clarifications"] == [{
        "field": "refundable", "source_quote": "non-refundable", "reason": "ambiguous"
    }]
    assert result["fields"]["origin_airports"] == ["EWR"]


def test_unquoted_field_cannot_be_fabricated_into_a_clarification():
    message = "Fly from EWR under $300."
    result = recover_grounded_parts(
        "flight",
        message,
        envelope(
            {"origin_airports": ["EWR"], "destination_airports": ["CPH"], "max_total_cents": 29999},
            {
                "origin_airports": "EWR",
                "destination_airports": "invented destination",
                "max_total_cents": "under $300",
            },
        ),
    )

    assert result is not None
    assert result["fields"] == {
        "origin_airports": ["EWR"], "max_total_cents": 29999
    }
    assert "destination_airports" not in result["fields"]
    assert not any(item["field"] == "destination_airports"
                   for item in result["clarifications"])
    assert any(item["field"] == "destination_airports"
               and item["issue"] == "source_unquoted"
               for item in result["recovery"]["rejected_fields"])


def test_all_untrusted_fields_keep_typed_failure_instead_of_passing_empty_draft():
    message = "A non-refundable flight."
    result = recover_grounded_parts(
        "flight",
        message,
        envelope(
            {"max_connections": 2},
            {"max_connections": "non-refundable"},
        ),
    )

    assert result is None


def test_malformed_or_extra_top_level_structure_is_never_partially_accepted():
    message = "Fly from EWR under $300."
    malformed = envelope(
        {"origin_airports": ["EWR"]}, {"origin_airports": "EWR"}
    )
    malformed["extra"] = "provider payload"
    assert recover_grounded_parts("flight", message, malformed) is None

    over_capacity = envelope(
        {"origin_airports": ["EWR"]}, {"origin_airports": "EWR"},
        unsupported=[f"condition {index}" for index in range(21)],
    )
    assert recover_grounded_parts("flight", message, over_capacity) is None


def test_unknown_conditions_remain_held_alongside_recovered_fields():
    message = "Fly from EWR to CPH under $300; round trip and checked bag."
    result = recover_grounded_parts(
        "flight",
        message,
        envelope(
            {"origin_airports": ["EWR"], "destination_airports": ["CPH"], "max_total_cents": 29999},
            {
                "origin_airports": "EWR",
                "destination_airports": "CPH",
                "max_total_cents": "under $300",
            },
            unsupported=["round trip", "checked bag"],
        ),
    )

    assert result is not None
    assert result["unsupported"] == ["round trip", "checked bag"]


def test_existing_passenger_condition_is_retained_once_without_dropping_other_scope():
    from app.ai_grounding import validate_extraction
    message = "A nonstop flight for one adult under $300, with May 7 preferred."
    result = validate_extraction("flight", message, envelope(
        {"nonstop": True, "max_total_cents": 29999},
        {"nonstop": "nonstop", "max_total_cents": "under $300"},
        unsupported=["one adult", "May 7 preferred"],
    ))
    assert result["unsupported"] == ["one adult", "May 7 preferred"]


def test_different_or_incomplete_passenger_flag_does_not_hide_requested_quantity():
    from app.ai_grounding import validate_extraction
    message = "A nonstop flight for one adult under $300."
    for existing in ("one", "two adults"):
        result = validate_extraction("flight", message, envelope(
            {"nonstop": True, "max_total_cents": 29999},
            {"nonstop": "nonstop", "max_total_cents": "under $300"},
            unsupported=[existing],
        ))
        assert "for one adult" in result["unsupported"]


def test_scope_preservation_overflow_fails_closed_without_truncating_conditions():
    message = (
        "Fly from EWR to CPH on 2026-11-12 for 2 adults; "
        "November 14 is preferred."
    )
    result = recover_grounded_parts(
        "flight",
        message,
        envelope(
            {
                "origin_airports": ["EWR"],
                "destination_airports": ["CPH"],
                "departure_date": "2026-11-12",
            },
            {
                "origin_airports": "EWR",
                "destination_airports": "CPH",
                "departure_date": "2026-11-12",
            },
            unsupported=[f"condition {index}" for index in range(20)],
        ),
    )

    # Quantity and date-priority preservation would take this beyond the
    # bounded envelope.  The helper must fail closed rather than drop either
    # those conditions or one of the original unknown flags.
    assert result is None

