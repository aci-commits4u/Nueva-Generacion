"""Contract tests for the pure semantic intent ledger."""

from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator

from app.intent_ledger import (
    LedgerError,
    bootstrap_ledger,
    compile_ledger,
    empty_ledger,
    proposal_schema,
    reduce_ledger,
    review_ledger,
)


CATALOG = [
    {"id": "t1p0e27h111111111111", "text": "EWR or JFK to MCO on 2026-11-12"},
    {"id": "t2p0e24h222222222222", "text": "The all-in total is USD 300."},
    {"id": "t3p0e36h333333333333", "text": "Actually, use EWR or LGA instead."},
    {"id": "t4p0e22h444444444444", "text": "I do not care about breakfast."},
]


def op(
    operation="add",
    *,
    key="route",
    field=None,
    value=None,
    strength="required",
    status="active",
    text="route requirement",
    refs=None,
    target_id=None,
    unit=None,
):
    return {
        "op": operation,
        "target_id": target_id,
        "key": key,
        "field": field,
        "value": value,
        "strength": strength,
        "status": status,
        "text": text,
        "source_refs": list(refs or [CATALOG[0]["id"]]),
        "unit": unit,
    }


def proposal(*operations, expected_revision=0, action="ready_for_review"):
    return {
        "expected_revision": expected_revision,
        "operations": list(operations),
        "action": action,
        "question": None,
        "assistant_message": "I captured the latest requirements.",
        "explanation": "The proposed state is ready for review.",
    }


def test_empty_ledger_has_revision_records_and_history():
    assert empty_ledger() == {"revision": 0, "records": [], "history": []}
    assert empty_ledger(3)["revision"] == 3


def test_reduce_adds_immutable_record_and_history():
    ledger = empty_ledger()
    before = deepcopy(ledger)
    result = reduce_ledger(
        "flight",
        ledger,
        proposal(
            op(
                key="origin_airports",
                field="origin_airports",
                value=["EWR", "JFK"],
                text="EWR or JFK",
            )
        ),
        CATALOG,
        expected_revision=0,
    )
    assert ledger == before
    assert result["revision"] == 1
    assert result["records"][0]["id"]
    assert result["records"][0]["created_revision"] == 1
    assert result["records"][0]["status"] == "active"
    assert result["records"][0]["source_is_current_value_evidence"] is True
    assert result["records"][0]["source_entailment"] == "model_assertion_unverified"
    assert "source_entails_value" not in result["records"][0]
    assert result["history"][0]["revision"] == 1
    assert result["history"][0]["op"] == "add"


def test_omission_is_no_operation_and_preserves_unrelated_records():
    ledger = reduce_ledger(
        "flight",
        empty_ledger(),
        proposal(
            op(key="origin_airports", field="origin_airports", value=["EWR"]),
            op(key="departure_date", field="departure_date", value="2026-11-12"),
        ),
        CATALOG,
        expected_revision=0,
    )
    result = reduce_ledger(
        "flight",
        ledger,
        proposal(expected_revision=1),
        CATALOG,
        expected_revision=1,
    )
    assert result["revision"] == 2
    assert [r["key"] for r in result["records"] if r["status"] == "active"] == [
        "origin_airports",
        "departure_date",
    ]


def test_replace_supersedes_only_target_and_preserves_unrelated_state():
    ledger = reduce_ledger(
        "flight",
        empty_ledger(),
        proposal(
            op(key="origin_airports", field="origin_airports", value=["EWR"]),
            op(key="departure_date", field="departure_date", value="2026-11-12"),
        ),
        CATALOG,
        expected_revision=0,
    )
    target = next(r for r in ledger["records"] if r["key"] == "origin_airports")
    changed = reduce_ledger(
        "flight",
        ledger,
        proposal(
            op(
                "replace",
                key="origin_airports",
                field="origin_airports",
                value=["EWR", "LGA"],
                refs=[CATALOG[3]["id"]],
                target_id=target["id"],
                text="EWR or LGA",
            ),
            expected_revision=1,
        ),
        CATALOG,
        expected_revision=1,
    )
    active = [r for r in changed["records"] if r["status"] == "active"]
    assert next(r for r in active if r["key"] == "origin_airports")["value"] == ["EWR", "LGA"]
    assert next(r for r in active if r["key"] == "departure_date")["value"] == "2026-11-12"
    old = next(r for r in changed["records"] if r["id"] == target["id"])
    assert old["status"] == "superseded"


def test_retract_removes_requirement_and_no_preference_is_explicit():
    ledger = reduce_ledger(
        "hotel",
        empty_ledger(),
        proposal(
            op(key="city", field="city", value="Toronto"),
            op(
                key="breakfast",
                field="breakfast",
                value=True,
                refs=[CATALOG[3]["id"]],
                text="breakfast matters",
            ),
        ),
        CATALOG,
        expected_revision=0,
    )
    breakfast = next(r for r in ledger["records"] if r["key"] == "breakfast")
    retracted = reduce_ledger(
        "hotel",
        ledger,
        proposal(
            op(
                "retract",
                key="breakfast",
                target_id=breakfast["id"],
                refs=[CATALOG[3]["id"]],
                text="breakfast is no longer required",
            ),
            expected_revision=1,
        ),
        CATALOG,
        expected_revision=1,
    )
    assert not [r for r in retracted["records"] if r["status"] == "active" and r["key"] == "breakfast"]
    city = next(r for r in retracted["records"] if r["key"] == "city")
    no_pref = reduce_ledger(
        "hotel",
        retracted,
        proposal(
            op(
                "no_preference",
                key="breakfast",
                field="breakfast",
                status="no_preference",
                value=None,
                target_id=breakfast["id"],
                refs=[CATALOG[3]["id"]],
                text="breakfast is no preference",
            ),
            expected_revision=2,
        ),
        CATALOG,
        expected_revision=2,
    )
    assert any(r["status"] == "no_preference" and r["key"] == "breakfast" for r in no_pref["records"])
    assert any(r["status"] == "active" and r["id"] == city["id"] for r in no_pref["records"])


def test_declined_record_can_be_replaced_with_fresh_customer_evidence():
    ledger = reduce_ledger(
        "hotel",
        empty_ledger(),
        proposal(
            op(
                "no_preference",
                key="breakfast",
                field="breakfast",
                status="no_preference",
                value=None,
                refs=[CATALOG[3]["id"]],
                text="breakfast is no preference",
            )
        ),
        CATALOG,
        expected_revision=0,
    )
    target = ledger["records"][0]["id"]
    changed = reduce_ledger(
        "hotel",
        ledger,
        proposal(
            op(
                "replace",
                key="breakfast",
                field="breakfast",
                value=True,
                target_id=target,
                refs=[CATALOG[3]["id"]],
                text="breakfast is required again",
            ),
            expected_revision=1,
        ),
        CATALOG,
        expected_revision=1,
    )
    assert compile_ledger("hotel", changed, CATALOG)["fields"]["breakfast"] is True


def test_stale_revision_and_invalid_batch_are_atomic():
    ledger = empty_ledger()
    with pytest.raises(LedgerError, match="revision"):
        reduce_ledger("flight", ledger, proposal(expected_revision=2), CATALOG, expected_revision=2)
    assert ledger == empty_ledger()

    bad = proposal(
        op(key="origin_airports", field="origin_airports", value=["EWR"]),
        op(key="origin_airports_2", field="origin_airports", value=["MCO"]),
    )
    with pytest.raises(LedgerError, match="conflict|duplicate"):
        reduce_ledger("flight", ledger, bad, CATALOG, expected_revision=0)
    assert ledger == empty_ledger()


@pytest.mark.parametrize(
    "bad_ref",
    ["invented", CATALOG[0]["id"] + "x"],
)
def test_unknown_or_spoofed_source_ref_rejected_without_mutation(bad_ref):
    ledger = empty_ledger()
    with pytest.raises(LedgerError, match="source"):
        reduce_ledger(
            "flight",
            ledger,
            proposal(op(key="origin_airports", field="origin_airports", value=["EWR"], refs=[bad_ref])),
            CATALOG,
            expected_revision=0,
        )
    assert ledger == empty_ledger()


def test_replace_requires_existing_target_and_latest_turn_evidence():
    with pytest.raises(LedgerError, match="target"):
        reduce_ledger(
            "flight",
            empty_ledger(),
            proposal(op("replace", key="origin_airports", field="origin_airports", value=["EWR"], target_id="r999")),
            CATALOG,
            expected_revision=0,
        )
    ledger = reduce_ledger(
        "flight",
        empty_ledger(),
        proposal(op(key="origin_airports", field="origin_airports", value=["EWR"])),
        CATALOG,
        expected_revision=0,
    )
    target = ledger["records"][0]["id"]
    with pytest.raises(LedgerError, match="latest"):
        reduce_ledger(
            "flight",
            ledger,
            proposal(
                op(
                    "replace",
                    key="origin_airports",
                    field="origin_airports",
                    value=["JFK"],
                    target_id=target,
                    refs=[CATALOG[0]["id"]],
                ),
                expected_revision=1,
            ),
            CATALOG,
            expected_revision=1,
        )


def test_date_range_and_or_set_values_compile_as_typed_fields():
    ledger = reduce_ledger(
        "flight",
        empty_ledger(),
        proposal(
            op(key="origin_airports", field="origin_airports", value=["EWR", "JFK"]),
            op(key="departure_date", field="departure_date", value={"start": "2026-11-12", "end": "2026-11-20"}),
        ),
        CATALOG,
        expected_revision=0,
    )
    compiled = compile_ledger("flight", ledger, CATALOG)
    assert compiled["fields"] == {
        "origin_airports": ["EWR", "JFK"],
        "departure_date": {"start": "2026-11-12", "end": "2026-11-20"},
    }


def test_required_unsupported_and_preferred_unknown_remain_visible_without_hardening():
    ledger = reduce_ledger(
        "general",
        empty_ledger(),
        proposal(
            op(key="max_total_cents", field="max_total_cents", value=30000, unit="total", refs=[CATALOG[1]["id"]], text="USD 300 all-in"),
            op(key="quiet", field=None, value=None, strength="required", text="quiet room", refs=[CATALOG[0]["id"]]),
            op(key="walkable", field=None, value=None, strength="preferred", text="walkable area", refs=[CATALOG[0]["id"]]),
        ),
        CATALOG,
        expected_revision=0,
    )
    compiled = compile_ledger("general", ledger, CATALOG)
    assert compiled["fields"]["max_total_cents"] == 30000
    assert "quiet room" in compiled["unsupported"]
    assert "walkable area" not in compiled["unsupported"]
    assert any(item["key"] == "quiet" for item in compiled["criteria"])
    assert any(item["key"] == "walkable" and item["strength"] == "preferred" for item in compiled["criteria"])
    assert any(item.get("key") == "quiet" for item in compiled["clarifications"])


def test_monetary_scope_must_be_profile_currency_and_all_in_total():
    good = reduce_ledger(
        "hotel",
        empty_ledger(),
        proposal(op(key="max_total_cents", field="max_total_cents", value=22000, unit="total", refs=[CATALOG[1]["id"]], text="USD 220 all-in")),
        CATALOG,
        expected_revision=0,
    )
    assert compile_ledger("hotel", good, CATALOG)["fields"]["max_total_cents"] == 22000

    bad = reduce_ledger(
        "hotel",
        empty_ledger(),
        proposal(op(key="max_total_cents", field="max_total_cents", value=22000, unit="nightly", refs=[CATALOG[1]["id"]], text="USD 220 nightly")),
        CATALOG,
        expected_revision=0,
    )
    compiled = compile_ledger("hotel", bad, CATALOG)
    assert "max_total_cents" not in compiled["fields"]
    assert any("nightly" in item for item in compiled["unsupported"])

    with pytest.raises(LedgerError, match="scope"):
        reduce_ledger(
            "hotel",
            empty_ledger(),
            proposal(
                op(
                    key="max_total_cents",
                    field="max_total_cents",
                    value={"amount": 220, "currency": "USD", "scope": "nightly"},
                    unit="total",
                    refs=[CATALOG[1]["id"]],
                    text="USD 220 nightly",
                )
            ),
            CATALOG,
            expected_revision=0,
        )


def test_unrecognized_unit_stays_unsupported_and_is_not_an_alias():
    ledger = reduce_ledger(
        "general",
        empty_ledger(),
        proposal(
            op(
                key="max_total_cents",
                field="max_total_cents",
                value=50000,
                unit="USD cents",
                refs=[CATALOG[1]["id"]],
                text="USD 500 total",
            )
        ),
        CATALOG,
        expected_revision=0,
    )
    compiled = compile_ledger("general", ledger, CATALOG)
    assert "max_total_cents" not in compiled["fields"]
    assert "USD 500 total" in compiled["unsupported"]


def test_bootstrap_rejects_any_unbound_legacy_projection_atomically():
    draft = {
        "fields": {"city": "Toronto", "max_total_cents": 20000},
        "sources": {"city": "Toronto", "max_total_cents": "fabricated"},
        "unsupported": ["quiet room"],
    }
    before = deepcopy(draft)
    with pytest.raises(LedgerError, match="catalogue-backed|safely"):
        bootstrap_ledger("hotel", draft, CATALOG + [{"id": "t1p0e7h555555555555", "text": "Toronto"}])
    assert draft == before


def test_bootstrap_preserves_legacy_substring_quotes_from_a_whole_customer_turn():
    catalog = [{
        "id": "t1p0e41hsource",
        "text": "I need a Toronto hotel; keep it quiet.",
    }]
    draft = {
        "fields": {"city": "Toronto"},
        "sources": {"city": "Toronto"},
        "unsupported": ["keep it quiet"],
    }
    bootstrapped = bootstrap_ledger("hotel", draft, catalog)
    city = next(record for record in bootstrapped["records"] if record["field"] == "city")
    unknown = next(record for record in bootstrapped["records"] if record["field"] is None)
    assert city["source_refs"] == [catalog[0]["id"]]
    assert city["source_quotes"] == ["Toronto"]
    assert unknown["source_refs"] == [catalog[0]["id"]]
    assert unknown["source_quotes"] == ["keep it quiet"]
    compiled = compile_ledger("hotel", bootstrapped, catalog)
    assert compiled["sources"]["city"] == "Toronto"
    assert "keep it quiet" in compiled["unsupported"]


def test_bootstrap_accepts_a_saved_nested_intent_ledger():
    ledger = reduce_ledger(
        "hotel",
        empty_ledger(),
        proposal(op(key="city", field="city", value="Toronto", refs=[CATALOG[0]["id"]], text="Toronto")),
        CATALOG,
        expected_revision=0,
    )
    restored = bootstrap_ledger("hotel", {"intent_ledger": ledger, "fields": {}}, CATALOG)
    assert restored["revision"] == ledger["revision"]
    assert restored["records"][0]["value"] == "Toronto"


def test_bootstrap_retains_embedded_quotes_when_saved_source_is_not_in_new_catalogue():
    old_catalog = [{"id": "t1p0e7hsource", "text": "Toronto"}]
    ledger = reduce_ledger(
        "hotel",
        empty_ledger(),
        proposal(op(key="city", field="city", value="Toronto", refs=[old_catalog[0]["id"]], text="Toronto")),
        old_catalog,
        expected_revision=0,
    )
    restored = bootstrap_ledger(
        "hotel",
        {"intent_ledger": ledger},
        [{"id": "t2p0e9hnewsource", "text": "Montreal"}],
    )
    assert restored["records"][0]["source_refs"] == [old_catalog[0]["id"]]
    assert restored["records"][0]["source_quotes"] == ["Toronto"]


def test_source_catalog_opaque_suffix_still_enforces_latest_turn_on_replacement():
    catalog = [
        {"id": "t1p0e4hsource", "text": "Toronto"},
        {"id": "t2p0e7hsource", "text": "Actually Montreal"},
    ]
    ledger = reduce_ledger(
        "hotel",
        empty_ledger(),
        proposal(op(key="city", field="city", value="Toronto", refs=[catalog[0]["id"]], text="Toronto")),
        catalog,
        expected_revision=0,
    )
    target = ledger["records"][0]["id"]
    with pytest.raises(LedgerError, match="latest"):
        reduce_ledger(
            "hotel",
            ledger,
            proposal(
                op(
                    "replace",
                    key="city",
                    field="city",
                    value="Montreal",
                    target_id=target,
                    refs=[catalog[0]["id"]],
                    text="Montreal",
                ),
                expected_revision=1,
            ),
            catalog,
            expected_revision=1,
        )


def test_proposal_schema_exposes_strict_typed_operation_and_question_shape():
    schema = proposal_schema("flight", CATALOG, empty_ledger())
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "expected_revision", "operations", "action", "question", "assistant_message", "explanation",
    }
    operation = schema["properties"]["operations"]["items"]
    assert len(operation["anyOf"]) == 2
    assert all(branch["type"] == "object" for branch in operation["anyOf"])
    assert all(branch["additionalProperties"] is False for branch in operation["anyOf"])
    assert all(set(branch["required"]) == {
        "op", "target_id", "key", "field", "value", "strength", "status", "text", "source_refs", "unit",
    } for branch in operation["anyOf"])
    unit_schema = operation["anyOf"][1]["properties"]["unit"]
    unit = next(item for item in unit_schema["anyOf"] if item.get("type") == "string")
    assert set(unit["enum"]) == {
        "total", "all_in_total", "total_cents", "per_night", "per_room", "per_person", "before_tax", "other",
    }


def test_proposal_schema_pins_expected_revision_to_server_owned_base():
    ledger = empty_ledger(2)
    schema = proposal_schema("flight", CATALOG, ledger)
    assert schema["properties"]["expected_revision"] == {"type": "integer", "enum": [2]}


def test_proposal_schema_rejects_illegal_operation_cross_fields_and_target_null():
    schema = proposal_schema("hotel", CATALOG, empty_ledger())
    validator = Draft202012Validator(schema)

    illegal_decline = proposal(
        op("no_preference", key="breakfast", field="breakfast", value=None, status="active")
    )
    assert not validator.is_valid(illegal_decline)

    invalid_target_edit = proposal(
        op("replace", key="breakfast", field="breakfast", value=True, target_id=None)
    )
    assert not validator.is_valid(invalid_target_edit)

    valid_decline = proposal(
        op("no_preference", key="breakfast", field="breakfast", value=None, status="no_preference")
    )
    assert validator.is_valid(valid_decline)

    valid_add = proposal(op("add", key="breakfast", field="breakfast", value=True))
    assert validator.is_valid(valid_add)


def test_proposal_schema_adds_exact_target_branches_only_after_record_exists():
    ledger = reduce_ledger(
        "hotel",
        empty_ledger(),
        proposal(op(key="breakfast", field="breakfast", value=True)),
        CATALOG,
        expected_revision=0,
    )
    schema = proposal_schema("hotel", CATALOG, ledger)
    branches = schema["properties"]["operations"]["items"]["anyOf"]
    assert len(branches) == 5
    edit_branch = next(
        branch for branch in branches
        if branch["properties"]["op"]["enum"] == ["replace"]
    )
    assert edit_branch["properties"]["target_id"]["enum"] == ["r1"]
    Draft202012Validator.check_schema(schema)


def test_customer_review_revision_preserves_source_provenance_and_records_new_value():
    ledger = reduce_ledger(
        "hotel",
        empty_ledger(),
        proposal(op(key="city", field="city", value="Toronto", refs=[CATALOG[0]["id"]], text="Toronto")),
        CATALOG,
        expected_revision=0,
    )
    reviewed = review_ledger("hotel", ledger, {"city": "Montreal"}, [], revision=1)
    record = next(r for r in reviewed["records"] if r["status"] == "active" and r["field"] == "city")
    assert record["value"] == "Montreal"
    assert record["provenance"] == "customer_review"
    assert record["source_refs"] == [CATALOG[0]["id"]]
    assert record["source_quotes"] == [CATALOG[0]["text"]]
    assert record["source_is_current_value_evidence"] is False
    assert record["source_entailment"] == "customer_review_authoritative"
    assert "source_entails_value" not in record
    assert reviewed["revision"] == 2
    assert compile_ledger("hotel", reviewed)["fields"]["city"] == "Montreal"


def test_customer_review_none_is_explicit_no_preference_and_does_not_compile():
    ledger = reduce_ledger(
        "hotel",
        empty_ledger(),
        proposal(op(key="breakfast", field="breakfast", value=True, refs=[CATALOG[3]["id"]], text="breakfast")),
        CATALOG,
        expected_revision=0,
    )
    reviewed = review_ledger("hotel", ledger, {"breakfast": None}, [], revision=1)
    record = next(r for r in reviewed["records"] if r["status"] == "no_preference")
    assert record["field"] == "breakfast"
    assert compile_ledger("hotel", reviewed)["fields"]["breakfast"] is None


def test_compiler_uses_embedded_source_quote_after_catalogue_is_unavailable():
    ledger = reduce_ledger(
        "general",
        empty_ledger(),
        proposal(op(key="max_total_cents", field="max_total_cents", value=30000, unit="total", refs=[CATALOG[1]["id"]], text="USD 300 all-in")),
        CATALOG,
        expected_revision=0,
    )
    compiled = compile_ledger("general", ledger)
    assert compiled["sources"]["max_total_cents"] == CATALOG[1]["text"]


def test_structured_airport_answer_overrides_model_narrowing_and_marks_widget_provenance():
    widget_catalog = [{"id": "t1p0e26haaaaaaaa", "text": "Depart from EWR or JFK."}]
    ledger = reduce_ledger(
        "flight",
        empty_ledger(),
        proposal(op(key="origin_airports", field="origin_airports", value=["EWR"], refs=[widget_catalog[0]["id"]])),
        widget_catalog,
        expected_revision=0,
    )
    target_id = ledger["records"][0]["id"]
    changed = reduce_ledger(
        "flight",
        ledger,
        proposal(
            op(
                key="origin_airports",
                field="origin_airports",
                value=["EWR"],
                target_id=target_id,
                refs=[widget_catalog[0]["id"]],
            ),
            expected_revision=1,
        ),
        widget_catalog,
        expected_revision=1,
        structured_answer={
            "question_id": "q-airports",
            "field": "origin_airports",
            "values": ["EWR", "JFK"],
            "source_quote": widget_catalog[0]["text"],
        },
    )
    record = next(r for r in changed["records"] if r["status"] == "active")
    assert record["value"] == ["EWR", "JFK"]
    assert record["provenance"] == "customer_widget"
    assert record["text"] == widget_catalog[0]["text"]
    assert changed["history"][-1]["provenance"] == "customer_widget"


def test_structured_airport_answer_requires_exact_latest_catalogue_source():
    with pytest.raises(LedgerError, match="catalogue|source"):
        reduce_ledger(
            "flight",
            empty_ledger(),
            proposal(),
            CATALOG,
            expected_revision=0,
            structured_answer={
                "field": "origin_airports",
                "values": ["EWR"],
                "source_quote": "Depart from EWR.",
            },
        )


def test_generic_new_criterion_can_be_questioned_only_when_proposed():
    question = {
        "criterion_key": "quiet_room",
        "field": None,
        "text": "Do you need a quiet room?",
        "why": "The request mentions quietness, which is not a supported profile field.",
        "answer_kind": "text",
        "answer_semantics": None,
        "options": [],
    }
    proposed = proposal(
        op(key="quiet_room", field=None, value=None, status="needs_clarification", text="quiet room"),
        action="ask_user",
    )
    proposed["question"] = question
    ledger = reduce_ledger("general", empty_ledger(), proposed, CATALOG, expected_revision=0)
    assert ledger["revision"] == 1
    with pytest.raises(LedgerError, match="criterion_key"):
        standalone = proposal(action="ask_user")
        standalone["question"] = question
        reduce_ledger("general", empty_ledger(), standalone, CATALOG, expected_revision=0)


def test_missing_monetary_value_can_remain_unresolved_or_no_preference():
    unresolved = reduce_ledger(
        "general",
        empty_ledger(),
        proposal(op(key="max_total_cents", field="max_total_cents", value=None, status="needs_clarification", text="budget is unclear")),
        CATALOG,
        expected_revision=0,
    )
    assert "max_total_cents" not in compile_ledger("general", unresolved, CATALOG)["fields"]
    declined = reduce_ledger(
        "general",
        empty_ledger(),
        proposal(op("no_preference", key="max_total_cents", field="max_total_cents", value=None, status="no_preference", text="no budget preference")),
        CATALOG,
        expected_revision=0,
    )
    assert "max_total_cents" not in compile_ledger("general", declined, CATALOG)["fields"]


def test_review_value_does_not_reuse_old_quote_as_entailment():
    ledger = reduce_ledger(
        "hotel",
        empty_ledger(),
        proposal(op(key="city", field="city", value="Toronto", refs=[CATALOG[0]["id"]], text="Toronto")),
        CATALOG,
        expected_revision=0,
    )
    reviewed = review_ledger("hotel", ledger, {"city": "Montreal"}, [], revision=1)
    record = next(r for r in reviewed["records"] if r["status"] == "active" and r["field"] == "city")
    assert record["source_refs"] == [CATALOG[0]["id"]]
    assert record["source_is_current_value_evidence"] is False
    assert record["source_entailment"] == "customer_review_authoritative"
    compiled = compile_ledger("hotel", reviewed, CATALOG)
    assert compiled["sources"].get("city") is None
    assert compiled["criteria"][-1]["source_quote"] is None


def test_review_preserves_preferred_unknown_criterion_when_not_flagged():
    ledger = reduce_ledger(
        "hotel",
        empty_ledger(),
        proposal(op(key="quiet", field=None, value=None, strength="preferred", text="quiet would be nice")),
        CATALOG,
        expected_revision=0,
    )
    reviewed = review_ledger("hotel", ledger, {"city": "Toronto"}, [], revision=1)
    assert any(r["key"] == "quiet" and r["status"] == "active" for r in reviewed["records"])

