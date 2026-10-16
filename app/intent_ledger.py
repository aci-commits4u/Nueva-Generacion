"""Pure transactional intent ledger and profile compiler.

The model may propose semantic edits, but this module owns state transitions,
source identity, typed profile values, and revision conflicts.  It deliberately
does not decide whether a quotation entails a semantic claim; that is the
model/review boundary.  All public functions copy their inputs before doing any
work so a rejected batch cannot partially apply.
"""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
import json
import re
from typing import Any

from app.profile_registry import get_profile, validate_fields


class LedgerError(ValueError):
    """A proposal cannot be safely applied to the current ledger."""


_LEDGER_KEYS = {"revision", "records", "history"}
_PROPOSAL_KEYS = {
    "expected_revision",
    "operations",
    "action",
    "question",
    "assistant_message",
    "explanation",
}
_OP_KEYS = {
    "op",
    "target_id",
    "key",
    "field",
    "value",
    "strength",
    "status",
    "text",
    "source_refs",
    "unit",
}
_OPS = {"add", "replace", "retract", "resolve", "no_preference"}
_ACTIONS = {"ask_user", "ready_for_review", "review_required"}
_STRENGTHS = {"required", "preferred"}
_STATUSES = {"active", "needs_clarification", "no_preference"}
_TERMINAL_STATUSES = {"superseded", "retracted"}
_CANONICAL_UNITS = (
    "total",
    "all_in_total",
    "total_cents",
    "per_night",
    "per_room",
    "per_person",
    "before_tax",
    "other",
)
# Source IDs are produced by ``structured_intent.build_source_catalog``.  The
# production suffix is a hexadecimal digest, while fixtures and persisted
# drafts may use readable opaque suffixes (for example ``hsource``).  Keep the
# structural turn/offset binding without over-constraining that opaque suffix.
_SOURCE_ID = re.compile(r"^t(?P<turn>\d+)p(?P<start>\d+)e(?P<end>\d+)h[0-9A-Za-z]+$")
_RECORD_ID = re.compile(r"^r(?P<number>\d+)$")
_MONETARY_UNITS = {"total", "all_in_total", "total_cents"}


def empty_ledger(revision: int = 0) -> dict[str, Any]:
    """Return a new empty ledger at ``revision``."""

    if type(revision) is not int or revision < 0:
        raise LedgerError("revision must be a non-negative integer")
    return {"revision": revision, "records": [], "history": []}


def _profile(domain: str) -> dict[str, Any]:
    try:
        return get_profile(domain)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        raise LedgerError(str(exc)) from exc


def _catalog_map(catalog: Any) -> dict[str, dict[str, Any]]:
    if catalog is None:
        return {}
    if not isinstance(catalog, list):
        raise LedgerError("catalog must be a list")
    result: dict[str, dict[str, Any]] = {}
    for item in catalog:
        if not isinstance(item, dict) or set(item) - {"id", "text"}:
            raise LedgerError("catalog entries must contain only id and text")
        source_id, text = item.get("id"), item.get("text")
        if not isinstance(source_id, str) or not source_id:
            raise LedgerError("catalog source IDs must be non-empty strings")
        if not isinstance(text, str) or not text:
            raise LedgerError("catalog source text must be non-empty strings")
        if source_id in result:
            raise LedgerError("catalog contains duplicate source IDs")
        result[source_id] = {"id": source_id, "text": text}
    return result


def _source_turn(source_id: str) -> int | None:
    match = _SOURCE_ID.fullmatch(source_id)
    return int(match.group("turn")) if match else None


def _latest_turn(catalog: dict[str, dict[str, Any]]) -> int | None:
    turns = [turn for source_id in catalog if (turn := _source_turn(source_id)) is not None]
    return max(turns) if turns else None


def _source_quotes(source_refs: list[str], catalog: dict[str, dict[str, Any]]) -> list[str]:
    return [catalog[ref]["text"] for ref in source_refs if ref in catalog]


def _validate_source_refs(
    refs: Any,
    catalog: dict[str, dict[str, Any]],
    *,
    required: bool = True,
    allow_unknown: bool = False,
) -> list[str]:
    if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
        raise LedgerError("source_refs must be an array of source IDs")
    if required and not refs:
        raise LedgerError("every model operation requires customer source evidence")
    if len(refs) != len(set(refs)):
        raise LedgerError("source_refs must not contain duplicates")
    unknown = [ref for ref in refs if ref not in catalog]
    if unknown and not allow_unknown:
        raise LedgerError("operation cites an unknown customer source")
    return list(refs)


def _value_equal(left: Any, right: Any) -> bool:
    try:
        return json.dumps(left, sort_keys=True, separators=(",", ":"), ensure_ascii=True) == json.dumps(
            right, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )
    except (TypeError, ValueError):
        return left == right


def _normalise_money(
    value: Any,
    unit: str | None,
    profile: dict[str, Any],
) -> tuple[Any, str | None, str | None]:
    """Normalize supported money forms while retaining unsupported scope.

    Profile fields are stored as integer cents.  A model may provide integer
    cents directly or a typed amount object.  A non-total unit remains a
    semantic record and is deliberately compiled as unsupported instead of
    being silently converted to a total.
    """

    currency = profile.get("currency")
    if unit is not None and not isinstance(unit, str):
        raise LedgerError("unit must be a string or null")
    if type(value) is int:
        if value < 0:
            raise LedgerError("monetary values cannot be negative")
        return value, unit, currency
    if not isinstance(value, dict):
        raise LedgerError("monetary value must be integer cents or a typed amount")
    allowed = {"amount", "amount_cents", "cents", "currency", "scope"}
    if set(value) - allowed:
        raise LedgerError("monetary value has unexpected properties")
    value_currency = value.get("currency")
    if value_currency != currency:
        raise LedgerError(f"monetary value must use profile currency {currency}")
    scope = value.get("scope")
    if scope is not None and not isinstance(scope, str):
        raise LedgerError("monetary scope must be a string")
    if scope is not None and unit is not None:
        equivalent = {scope, unit}
        if equivalent <= _MONETARY_UNITS:
            # ``total`` and ``all_in_total`` are equivalent profile labels.
            pass
        elif scope != unit:
            raise LedgerError("monetary value unit and scope disagree")
    if scope is not None and unit is None:
        unit = scope
    if unit is None:
        raise LedgerError("monetary value must declare its pricing scope")
    if "amount_cents" in value or "cents" in value:
        amount = value.get("amount_cents", value.get("cents"))
        if type(amount) is not int or amount < 0:
            raise LedgerError("amount_cents must be a non-negative integer")
        return amount, unit, value_currency
    amount = value.get("amount")
    if type(amount) not in {int, float} or isinstance(amount, bool) or amount < 0:
        raise LedgerError("amount must be a non-negative number")
    try:
        cents = Decimal(str(amount)) * 100
    except (InvalidOperation, ValueError) as exc:
        raise LedgerError("invalid monetary amount") from exc
    if cents != cents.to_integral_value() or cents < 0:
        raise LedgerError("monetary amount must have at most two decimal places")
    return int(cents), unit, value_currency


def _validate_field_value(
    profile: dict[str, Any],
    field: str | None,
    value: Any,
    unit: str | None,
) -> tuple[Any, str | None, str | None]:
    if field is None:
        if value is not None and not isinstance(value, (str, int, float, bool, list, dict)):
            raise LedgerError("unknown criteria must carry a JSON value")
        return deepcopy(value), unit, None
    fields = profile.get("fields", {})
    if field not in fields:
        raise LedgerError(f"unsupported profile field: {field}")
    if value is None:
        # Missing monetary meaning is a valid unresolved/no-preference record;
        # it must remain visible for compilation instead of failing reduction.
        if field == "max_total_cents":
            if unit is not None and not isinstance(unit, str):
                raise LedgerError("unit must be a string or null")
            return None, unit, None
        return None, None, None
    if field == "max_total_cents":
        return _normalise_money(value, unit, profile)
    if unit is not None:
        raise LedgerError(f"unit is only valid for monetary field {field}")
    try:
        validate_fields(profile, {field: value})
    except ValueError as exc:
        raise LedgerError(str(exc)) from exc
    return deepcopy(value), None, None


def _validate_ledger_shape(ledger: Any) -> dict[str, Any]:
    if not isinstance(ledger, dict) or set(ledger) != _LEDGER_KEYS:
        raise LedgerError("ledger shape is invalid")
    if type(ledger.get("revision")) is not int or ledger["revision"] < 0:
        raise LedgerError("ledger revision is invalid")
    if not isinstance(ledger.get("records"), list) or not isinstance(ledger.get("history"), list):
        raise LedgerError("ledger records/history must be arrays")
    return deepcopy(ledger)


def _next_record_id(records: list[dict[str, Any]]) -> str:
    numbers = []
    for record in records:
        match = _RECORD_ID.fullmatch(str(record.get("id", "")))
        if match:
            numbers.append(int(match.group("number")))
    return f"r{max(numbers, default=0) + 1}"


def _record_ids(records: list[dict[str, Any]]) -> set[str]:
    ids = set()
    for record in records:
        if not isinstance(record, dict):
            raise LedgerError("ledger records must be objects")
        record_id = record.get("id")
        if not isinstance(record_id, str) or not record_id:
            raise LedgerError("ledger record ID is invalid")
        if record_id in ids:
            raise LedgerError("ledger contains duplicate record IDs")
        ids.add(record_id)
    return ids


def _active_record(records: list[dict[str, Any]], target_id: str, *, allow_terminal: bool = False) -> dict[str, Any]:
    for record in records:
        if record.get("id") == target_id:
            if record.get("status") not in {"active", "needs_clarification", "no_preference"} and not allow_terminal:
                raise LedgerError("target record is no longer active")
            return record
    raise LedgerError("target record does not exist")


def _validate_question(
    question: Any,
    profile: dict[str, Any],
    ledger: dict[str, Any],
    *,
    allow_unknown: bool = False,
) -> None:
    if question is None:
        return
    if not isinstance(question, dict):
        raise LedgerError("question must be null or an object")
    expected = {
        "criterion_key", "field", "text", "why", "answer_kind", "answer_semantics", "options",
    }
    if set(question) != expected:
        raise LedgerError("question shape is invalid")
    allowed_keys = set(profile.get("fields", {})) | {
        record.get("key")
        for record in ledger.get("records", [])
        if isinstance(record, dict) and isinstance(record.get("key"), str)
    }
    if not isinstance(question["criterion_key"], str) or (
        not allow_unknown and question["criterion_key"] not in allowed_keys
    ):
        raise LedgerError("question criterion_key is invalid")
    field = question["field"]
    if field is not None and field not in profile.get("fields", {}):
        raise LedgerError("question field is not in the profile")
    for key in ("text", "why"):
        if not isinstance(question[key], str) or not question[key].strip():
            raise LedgerError("question text/why must be non-empty")
    if question["answer_kind"] not in {"single", "multi", "date_choice", "text", "number", "boolean"}:
        raise LedgerError("question answer_kind is invalid")
    if question["answer_semantics"] not in {None, "requirement_boolean", "preference_boolean"}:
        raise LedgerError("question answer_semantics is invalid")
    if not isinstance(question["options"], list):
        raise LedgerError("question options must be an array")
    for option in question["options"]:
        if not isinstance(option, dict) or set(option) != {"label", "value"}:
            raise LedgerError("question option shape is invalid")
        if not all(isinstance(option[key], str) and option[key].strip() for key in ("label", "value")):
            raise LedgerError("question option values must be non-empty strings")


def _validate_proposal(proposal: Any, profile: dict[str, Any], ledger: dict[str, Any]) -> None:
    if not isinstance(proposal, dict) or set(proposal) != _PROPOSAL_KEYS:
        raise LedgerError("proposal shape is invalid")
    if type(proposal["expected_revision"]) is not int or proposal["expected_revision"] < 0:
        raise LedgerError("proposal expected_revision is invalid")
    if not isinstance(proposal["operations"], list) or len(proposal["operations"]) > 40:
        raise LedgerError("proposal operations must be a bounded array")
    if proposal["action"] not in _ACTIONS:
        raise LedgerError("proposal action is invalid")
    if not isinstance(proposal["assistant_message"], str) or not isinstance(proposal["explanation"], str):
        raise LedgerError("proposal messages must be strings")
    _validate_question(proposal["question"], profile, ledger, allow_unknown=True)


def _validate_operation_shape(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != _OP_KEYS:
        raise LedgerError("operation shape is invalid")
    operation = deepcopy(raw)
    if operation["op"] not in _OPS:
        raise LedgerError("operation type is invalid")
    if operation["target_id"] is not None and not isinstance(operation["target_id"], str):
        raise LedgerError("target_id must be a record ID or null")
    if not isinstance(operation["key"], str) or not operation["key"].strip() or len(operation["key"]) > 160:
        raise LedgerError("operation key is invalid")
    if operation["field"] is not None and not isinstance(operation["field"], str):
        raise LedgerError("operation field must be a string or null")
    if operation["strength"] not in _STRENGTHS:
        raise LedgerError("operation strength is invalid")
    if operation["status"] not in _STATUSES:
        raise LedgerError("operation status is invalid")
    if operation["op"] == "no_preference" and operation["status"] != "no_preference":
        raise LedgerError("no_preference operation must use no_preference status")
    if operation["op"] == "no_preference" and (
        operation["value"] is not None or operation["unit"] is not None
    ):
        raise LedgerError("no_preference operation must use null value and unit")
    if operation["op"] != "no_preference" and operation["status"] == "no_preference":
        raise LedgerError("no_preference status requires no_preference operation")
    if not isinstance(operation["text"], str) or not operation["text"].strip() or len(operation["text"]) > 2000:
        raise LedgerError("operation text is invalid")
    if operation["unit"] is not None and not isinstance(operation["unit"], str):
        raise LedgerError("operation unit must be a string or null")
    return operation


def _record_from_operation(
    operation: dict[str, Any],
    profile: dict[str, Any],
    catalog: dict[str, dict[str, Any]],
    *,
    revision: int,
    record_id: str,
    provenance: str = "model",
    source_refs: list[str] | None = None,
) -> dict[str, Any]:
    refs = source_refs if source_refs is not None else operation["source_refs"]
    value, unit, currency = _validate_field_value(profile, operation["field"], operation["value"], operation["unit"])
    record = {
        "id": record_id,
        "key": operation["key"],
        "field": operation["field"],
        "value": value,
        "unit": unit,
        "strength": operation["strength"],
        "status": operation["status"],
        "text": operation["text"],
        "source_refs": list(refs),
        "source_quotes": _source_quotes(refs, catalog),
        "revision": revision,
        "created_revision": revision,
        "updated_revision": revision,
        "provenance": provenance,
        "source_is_current_value_evidence": True,
        "source_entailment": (
            "customer_widget_selection"
            if provenance == "customer_widget"
            else "model_assertion_unverified"
        ),
    }
    if currency is not None:
        record["currency"] = currency
    return record


def _structured_airport_operation(
    structured_answer: dict[str, Any],
    *,
    domain: str,
    profile: dict[str, Any],
    catalog: dict[str, dict[str, Any]],
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Bind a validated airport widget answer to exact customer evidence.

    The HTTP layer validates the widget/question contract.  The reducer still
    binds the canonical message to the immutable source catalogue and checks
    the typed set so a caller cannot smuggle a widget claim through this pure
    boundary.  The caller marks the resulting record as ``customer_widget``.
    """

    if domain != "flight" or not isinstance(structured_answer, dict):
        raise LedgerError("structured_answer is only supported for flight airport choices")
    field = structured_answer.get("field")
    values = structured_answer.get("values")
    source_quote = structured_answer.get("source_quote")
    supplied_ref = structured_answer.get("source_ref")
    if field not in {"origin_airports", "destination_airports"}:
        raise LedgerError("structured airport answer field is invalid")
    if not isinstance(values, list) or not 1 <= len(values) <= 20:
        raise LedgerError("structured airport answer must contain one to twenty airports")
    try:
        normalized, _, _ = _validate_field_value(profile, field, values, None)
    except LedgerError as exc:
        raise LedgerError("structured airport answer contains invalid airport values") from exc
    if supplied_ref is not None:
        if not isinstance(supplied_ref, str) or supplied_ref not in catalog:
            raise LedgerError("structured airport answer source ID is not in customer catalogue")
        if source_quote is None:
            source_quote = catalog[supplied_ref]["text"]
        elif source_quote != catalog[supplied_ref]["text"]:
            raise LedgerError("structured airport answer source ID and quote disagree")
    if not isinstance(source_quote, str) or not source_quote.strip():
        raise LedgerError("structured airport answer requires its canonical customer source")
    exact_refs = [source_id for source_id, item in catalog.items() if item.get("text") == source_quote]
    if not exact_refs:
        raise LedgerError("structured airport answer source is not in customer catalogue")
    latest_turn = _latest_turn(catalog)
    latest_refs = [ref for ref in exact_refs if latest_turn is None or _source_turn(ref) == latest_turn]
    if not latest_refs:
        raise LedgerError("structured airport answer must bind to the latest customer turn")
    if supplied_ref is not None and supplied_ref not in latest_refs:
        raise LedgerError("structured airport answer source ID is stale")
    target = next(
        (
            record
            for record in reversed(records)
            if record.get("field") == field and record.get("status") not in _TERMINAL_STATUSES
        ),
        None,
    )
    return {
        "op": "replace" if target is not None else "add",
        "target_id": target.get("id") if target is not None else None,
        "key": target.get("key") if target is not None else field,
        "field": field,
        "value": normalized,
        "strength": "required",
        "status": "active",
        "text": source_quote,
        "source_refs": latest_refs,
        "unit": None,
    }


def _check_conflicts(records: list[dict[str, Any]]) -> None:
    active = [record for record in records if record.get("status") not in _TERMINAL_STATUSES]
    by_key: dict[str, dict[str, Any]] = {}
    by_field: dict[str, list[dict[str, Any]]] = {}
    for record in active:
        key = record.get("key")
        if key in by_key:
            raise LedgerError("duplicate active semantic criterion")
        by_key[key] = record
        field = record.get("field")
        if field is not None and record.get("status") in {"active", "needs_clarification", "no_preference"}:
            by_field.setdefault(field, []).append(record)
    for field, field_records in by_field.items():
        if len(field_records) < 2:
            continue
        first = field_records[0]
        if any(not _value_equal(first.get("value"), other.get("value")) or first.get("status") != other.get("status") for other in field_records[1:]):
            raise LedgerError(f"conflicting active values for field {field}")
        raise LedgerError(f"duplicate active values for field {field}")


def reduce_ledger(
    domain: str,
    ledger: dict[str, Any],
    proposal: dict[str, Any],
    catalog: list[dict[str, Any]],
    *,
    expected_revision: int,
    structured_answer: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply one complete proposal transactionally to a copy of ``ledger``."""

    profile = _profile(domain)
    catalog_map = _catalog_map(catalog)
    current = _validate_ledger_shape(ledger)
    _record_ids(current["records"])
    if type(expected_revision) is not int or expected_revision < 0:
        raise LedgerError("expected_revision is invalid")
    if current["revision"] != expected_revision:
        raise LedgerError("ledger revision does not match expected revision")
    _validate_proposal(proposal, profile, current)
    if proposal["expected_revision"] != expected_revision:
        raise LedgerError("proposal revision does not match expected revision")
    if structured_answer is not None and not isinstance(structured_answer, dict):
        raise LedgerError("structured_answer must be an object")

    next_revision = expected_revision + 1
    records = current["records"]
    history = current["history"]
    seen_targets: set[str] = set()
    latest_turn = _latest_turn(catalog_map)
    operations = [_validate_operation_shape(raw) for raw in proposal["operations"]]
    structured_operation: dict[str, Any] | None = None
    if structured_answer is not None:
        structured_operation = _validate_operation_shape(
            _structured_airport_operation(
                structured_answer,
                domain=domain,
                profile=profile,
                catalog=catalog_map,
                records=records,
            )
        )
        structured_field = structured_operation["field"]
        structured_target = structured_operation.get("target_id")
        # A customer widget selection is authoritative for its bound route
        # field.  Discard model operations that could narrow, retract, or
        # rewrite that exact set, while preserving unrelated edits.
        operations = [
            operation
            for operation in operations
            if operation.get("field") != structured_field
            and operation.get("key") != structured_operation["key"]
            and (structured_target is None or operation.get("target_id") != structured_target)
        ]
        operations.append(structured_operation)
        if len(operations) > 40:
            raise LedgerError("proposal operations must be a bounded array")
    for operation in operations:
        refs = _validate_source_refs(operation["source_refs"], catalog_map)
        target_id = operation["target_id"]
        if target_id is not None:
            if target_id in seen_targets:
                raise LedgerError("multiple operations target the same record")
            seen_targets.add(target_id)
        target = None
        if operation["op"] == "add" and target_id is not None:
            raise LedgerError("add operation cannot target an existing record")
        if operation["op"] in {"replace", "resolve", "retract"} or target_id is not None:
            if target_id is None:
                raise LedgerError(f"{operation['op']} requires target_id")
            target = _active_record(
                records,
                target_id,
                allow_terminal=operation["op"] == "no_preference",
            )
            if target.get("key") != operation["key"]:
                raise LedgerError("operation target key does not match target record")
            if target.get("field") is not None and operation["field"] is not None and target.get("field") != operation["field"]:
                raise LedgerError("operation target field does not match target record")
            if latest_turn is not None and not any(_source_turn(ref) == latest_turn for ref in refs):
                raise LedgerError("replacement/retraction requires latest customer-turn evidence")
        operation_provenance = "customer_widget" if operation is structured_operation else "model"
        if operation["op"] in {"add", "replace", "resolve", "no_preference"}:
            if operation["op"] == "no_preference" and operation["value"] is not None:
                raise LedgerError("no_preference cannot carry a value")
            if operation["op"] != "no_preference" and operation["status"] == "active" and operation["field"] is not None and operation["value"] is None:
                raise LedgerError("active operation must carry a value")
            record = _record_from_operation(
                operation,
                profile,
                catalog_map,
                revision=next_revision,
                record_id=_next_record_id(records),
                provenance=operation_provenance,
            )
            if target is not None:
                target["status"] = "superseded"
                target["updated_revision"] = next_revision
            records.append(record)
            history.append({
                "revision": next_revision,
                "op": operation["op"],
                "record_id": record["id"],
                "target_id": target_id,
                "key": record["key"],
                "source_refs": list(refs),
                "source_quotes": _source_quotes(refs, catalog_map),
                "provenance": operation_provenance,
                "actor": operation_provenance,
                "source_is_current_value_evidence": True,
                "source_entailment": (
                    "customer_widget_selection"
                    if operation_provenance == "customer_widget"
                    else "model_assertion_unverified"
                ),
            })
        elif operation["op"] == "retract":
            target["status"] = "retracted"
            target["updated_revision"] = next_revision
            history.append({
                "revision": next_revision,
                "op": "retract",
                "record_id": target["id"],
                "target_id": target["id"],
                "key": target["key"],
                "source_refs": list(refs),
                "source_quotes": _source_quotes(refs, catalog_map),
                "provenance": operation_provenance,
                "actor": operation_provenance,
                "source_is_current_value_evidence": True,
                "source_entailment": (
                    "customer_widget_selection"
                    if operation_provenance == "customer_widget"
                    else "model_assertion_unverified"
                ),
            })
    _check_conflicts(records)
    _validate_question(
        proposal["question"],
        profile,
        {"records": records},
        allow_unknown=False,
    )
    current["revision"] = next_revision
    current["records"] = records
    current["history"] = history
    return current


def _match_source_refs(
    quote: Any,
    catalog: dict[str, dict[str, Any]],
    *,
    allow_substring: bool = False,
) -> list[str]:
    """Find catalogue refs that prove a legacy quote came from the customer.

    Legacy snapshots often retained a short quote such as ``"Toronto"``
    while the source catalogue retained only a whole-turn span.  Substring
    matching is used only by the explicit bootstrap importer, never by model
    operations.  When several turns contain the quote, retaining all equally
    plausible whole-turn refs avoids selecting an invented provenance.
    """

    if not isinstance(quote, str) or not quote:
        return []
    exact = [source_id for source_id, item in catalog.items() if item["text"] == quote]
    if exact or not allow_substring:
        return exact
    candidates = [source_id for source_id, item in catalog.items() if quote in item["text"]]
    if not candidates:
        return []
    whole_turns = []
    for source_id in candidates:
        match = _SOURCE_ID.fullmatch(source_id)
        item = catalog[source_id]
        if match and match.group("start") == "0" and int(match.group("end")) == len(item["text"]):
            whole_turns.append(source_id)
    if whole_turns:
        return whole_turns
    shortest = min(len(catalog[source_id]["text"]) for source_id in candidates)
    return [source_id for source_id in candidates if len(catalog[source_id]["text"]) == shortest]


def _match_source_quote(quote: Any, catalog: dict[str, dict[str, Any]]) -> str | None:
    refs = _match_source_refs(quote, catalog)
    return refs[0] if refs else None


def _bind_legacy_quote(
    quote: Any,
    catalog: dict[str, dict[str, Any]],
    supplied_refs: Any = None,
) -> tuple[list[str], str] | None:
    """Bind an old projection quote to actual customer catalogue evidence."""

    refs: list[str]
    if supplied_refs is not None:
        refs = _validate_source_refs(supplied_refs, catalog, required=False)
        if not refs:
            return None
        if isinstance(quote, str) and quote:
            matching = [ref for ref in refs if quote in catalog[ref]["text"]]
            if not matching:
                return None
            return matching, quote
        return refs, catalog[refs[-1]]["text"]
    if not isinstance(quote, str) or not quote:
        return None
    refs = _match_source_refs(quote, catalog, allow_substring=True)
    return (refs, quote) if refs else None


def bootstrap_ledger(domain: str, current_draft: dict[str, Any] | None, catalog: list[dict[str, Any]]) -> dict[str, Any]:
    """Import a legacy draft only where its quote is in customer evidence."""

    profile = _profile(domain)
    catalog_map = _catalog_map(catalog)
    if not current_draft:
        return empty_ledger()
    if not isinstance(current_draft, dict):
        raise LedgerError("current_draft must be an object")
    nested_ledger = current_draft.get("intent_ledger")
    if isinstance(nested_ledger, dict):
        # Saved drafts carry the semantic ledger beside legacy projection
        # fields.  Prefer that server-owned state when an explicit bootstrap
        # is requested; otherwise legacy fields can be imported below.
        if "records" in nested_ledger or "history" in nested_ledger:
            current_draft = nested_ledger
    if set(current_draft) >= _LEDGER_KEYS and isinstance(current_draft.get("records"), list):
        result = _validate_ledger_shape(current_draft)
        _record_ids(result["records"])
        for record in result["records"]:
            refs = record.get("source_refs", [])
            embedded_quotes = record.get("source_quotes")
            has_embedded_quotes = isinstance(embedded_quotes, list) and bool(embedded_quotes)
            if has_embedded_quotes and any(not isinstance(quote, str) or not quote for quote in embedded_quotes):
                raise LedgerError("persisted source quotes must be non-empty strings")
            _validate_source_refs(refs, catalog_map, required=False, allow_unknown=has_embedded_quotes)
            # A persisted ledger is allowed to outlive the catalogue snapshot
            # that created it.  Its embedded quotes are the immutable history
            # fallback; current catalogue text is only used when no quote was
            # persisted at all.  Incoming model operations still require every
            # ref to exist in the current catalogue.
            if isinstance(embedded_quotes, list) and embedded_quotes:
                record["source_quotes"] = list(embedded_quotes)
            else:
                record["source_quotes"] = _source_quotes(refs, catalog_map)
        _check_conflicts(result["records"])
        return result
    result = empty_ledger(int(current_draft.get("revision", 0)) if type(current_draft.get("revision", 0)) is int and current_draft.get("revision", 0) >= 0 else 0)
    raw_fields = current_draft.get("fields")
    if raw_fields is not None and not isinstance(raw_fields, dict):
        raise LedgerError("legacy fields projection is invalid")
    fields = raw_fields or {}
    raw_sources = current_draft.get("sources")
    if raw_sources is not None and not isinstance(raw_sources, dict):
        raise LedgerError("legacy sources projection is invalid")
    sources = raw_sources or {}
    raw_source_refs = current_draft.get("source_refs")
    if raw_source_refs is not None and not isinstance(raw_source_refs, dict):
        raise LedgerError("legacy source_refs projection is invalid")
    source_refs_by_field = raw_source_refs or {}
    for field, value in fields.items():
        if value is None:
            continue
        if field not in profile.get("fields", {}):
            raise LedgerError("legacy field is outside the profile")
        source_text = sources.get(field)
        supplied_refs = source_refs_by_field.get(field)
        if field in source_refs_by_field and not isinstance(supplied_refs, list):
            raise LedgerError("legacy field source_refs is invalid")
        if field in sources and source_text is not None and not isinstance(source_text, str):
            raise LedgerError("legacy field source quote is invalid")
        binding = _bind_legacy_quote(
            source_text if isinstance(source_text, str) and source_text else None,
            catalog_map,
            supplied_refs if isinstance(supplied_refs, list) else None,
        )
        if binding is None:
            raise LedgerError("legacy field lacks catalogue-backed customer evidence")
        bound_refs, exact_quote = binding
        try:
            normal_value, unit, currency = _validate_field_value(profile, field, value, "total" if field == "max_total_cents" else None)
        except LedgerError as exc:
            raise LedgerError("legacy field value cannot be imported safely") from exc
        record = {
            "id": _next_record_id(result["records"]),
            "key": field,
            "field": field,
            "value": normal_value,
            "unit": unit,
            "strength": "required",
            "status": "active",
            "text": exact_quote,
            "source_refs": bound_refs,
            "source_quotes": [exact_quote],
            "revision": result["revision"],
            "created_revision": result["revision"],
            "updated_revision": result["revision"],
            "provenance": "bootstrap",
            "source_is_current_value_evidence": True,
            "source_entailment": "bootstrap_unverified",
        }
        if currency is not None:
            record["currency"] = currency
        result["records"].append(record)
    raw_unsupported = current_draft.get("unsupported")
    if raw_unsupported is not None and not isinstance(raw_unsupported, list):
        raise LedgerError("legacy unsupported projection is invalid")
    unsupported = raw_unsupported or []
    for index, text in enumerate(unsupported):
        text_value = text if isinstance(text, str) else text.get("text") if isinstance(text, dict) else None
        supplied_refs = None
        if isinstance(text, dict):
            if isinstance(text.get("source_refs"), list):
                supplied_refs = text["source_refs"]
            elif isinstance(text.get("source_ref"), str):
                supplied_refs = [text["source_ref"]]
        if not isinstance(text_value, str) or not text_value:
            raise LedgerError(f"legacy unsupported item {index} is invalid")
        binding = _bind_legacy_quote(text_value, catalog_map, supplied_refs)
        if binding is None:
            raise LedgerError(f"legacy unsupported item {index} lacks catalogue-backed customer evidence")
        bound_refs, exact_quote = binding
        result["records"].append({
            "id": _next_record_id(result["records"]),
            "key": f"unsupported:{index}",
            "field": None,
            "value": None,
            "unit": None,
            "strength": "required",
            "status": "needs_clarification",
            "text": exact_quote,
            "source_refs": bound_refs,
            "source_quotes": [exact_quote],
            "revision": result["revision"],
            "created_revision": result["revision"],
            "updated_revision": result["revision"],
            "provenance": "bootstrap",
            "source_is_current_value_evidence": True,
            "source_entailment": "bootstrap_unverified",
        })
    _check_conflicts(result["records"])
    return result


def _record_source_texts(record: dict[str, Any], catalog: dict[str, dict[str, Any]]) -> list[str]:
    # ``source_is_current_value_evidence`` distinguishes a customer-owned
    # review value from a model assertion that merely cites a real source.
    # Read the old flag for saved pre-contract ledgers, but never emit it for
    # new records because it overstated semantic entailment.
    if (
        record.get("source_is_current_value_evidence") is False
        or record.get("source_entails_value") is False
    ):
        return []
    embedded = record.get("source_quotes")
    embedded_quotes = list(embedded) if isinstance(embedded, list) else []
    # Preserve the exact quote captured at bootstrap/reduction.  A later
    # catalogue snapshot may have broader spans (or changed availability),
    # but it must not replace the immutable quote stored with the record.
    return embedded_quotes or _source_quotes(record.get("source_refs", []), catalog)


def compile_ledger(domain: str, ledger: dict[str, Any], catalog: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Compile profile-supported required active records without interpretation."""

    profile = _profile(domain)
    current = _validate_ledger_shape(ledger)
    _record_ids(current["records"])
    catalog_map = _catalog_map(catalog)
    _check_conflicts(current["records"])
    fields: dict[str, Any] = {}
    sources: dict[str, str] = {}
    source_refs: dict[str, list[str]] = {}
    unsupported: list[str] = []
    clarifications: list[dict[str, Any]] = []
    criteria: list[dict[str, Any]] = []

    def add_unsupported(text: str) -> None:
        if text and text not in unsupported:
            unsupported.append(text)

    def add_clarification(record: dict[str, Any], reason: str = "unknown") -> None:
        embedded_quotes = _record_source_texts(record, catalog_map)
        item = {
            "key": record.get("key"),
            "field": record.get("field"),
            "reason": reason if reason in {"ambiguous", "preference", "missing"} else "ambiguous",
            "text": record.get("text", ""),
            "record_id": record.get("id"),
            "source_refs": list(record.get("source_refs", [])),
            "source_quote": embedded_quotes[-1] if embedded_quotes else None,
        }
        if not any(existing.get("key") == item["key"] and existing.get("reason") == item["reason"] for existing in clarifications):
            clarifications.append(item)

    for record in current["records"]:
        if record.get("status") in _TERMINAL_STATUSES:
            continue
        source_texts = _record_source_texts(record, catalog_map)
        criterion = {
            "record_id": record.get("id"),
            "key": record.get("key"),
            "field": record.get("field"),
            "value": deepcopy(record.get("value")),
            "unit": record.get("unit"),
            "strength": record.get("strength"),
            "status": record.get("status"),
            "text": record.get("text", ""),
            "source_refs": list(record.get("source_refs", [])),
            "source_quotes": source_texts,
            "source_quote": source_texts[-1] if source_texts else None,
            "provenance": record.get("provenance", "model"),
            "source_is_current_value_evidence": record.get("source_is_current_value_evidence"),
            "source_entailment": record.get("source_entailment"),
            "ledger_status": record.get("status"),
            "kind": "preference" if record.get("strength") == "preferred" else "requirement",
            "verification": "supported",
            "status": "captured",
        }
        criteria.append(criterion)
        if record.get("status") == "no_preference":
            criterion["status"] = "declined"
            criterion["verification"] = "not_required"
            if field := record.get("field"):
                if field in profile.get("fields", {}) and not profile["fields"][field].get("required"):
                    fields[field] = None
                    source_refs[field] = list(record.get("source_refs", []))
                    if source_texts:
                        sources[field] = source_texts[-1]
            continue
        field = record.get("field")
        if field is None:
            if record.get("status") in {"active", "needs_clarification"}:
                criterion["kind"] = "ambiguity"
                criterion["verification"] = "unsupported"
                criterion["status"] = "unsupported" if record.get("status") == "active" else "needs_clarification"
                if record.get("strength") == "required":
                    add_unsupported(record.get("text", ""))
                    add_clarification(record, "ambiguous")
            continue
        if record.get("strength") != "required":
            # Preferences remain visible in criteria but cannot become a
            # deterministic requirement merely by being present.
            continue
        if record.get("status") != "active":
            add_unsupported(record.get("text", ""))
            criterion["verification"] = "unsupported"
            criterion["status"] = "needs_clarification"
            add_clarification(record, "ambiguous")
            continue
        value = record.get("value")
        try:
            normal_value, unit, _currency = _validate_field_value(profile, field, value, record.get("unit"))
        except LedgerError:
            add_unsupported(record.get("text", ""))
            criterion["verification"] = "unsupported"
            criterion["status"] = "unsupported"
            add_clarification(record, "ambiguous")
            continue
        if field == "max_total_cents" and unit not in _MONETARY_UNITS:
            add_unsupported(record.get("text", ""))
            criterion["verification"] = "unsupported"
            criterion["status"] = "unsupported"
            add_clarification(record, "ambiguous")
            continue
        fields[field] = normal_value
        source_refs[field] = list(record.get("source_refs", []))
        if source_texts:
            sources[field] = source_texts[-1]

    for field, specification in profile.get("fields", {}).items():
        if specification.get("required") and field not in fields:
            placeholder = {
                "id": f"missing:{field}",
                "key": field,
                "field": field,
                "text": specification.get("question", f"Missing required field {field}"),
                "source_refs": [],
            }
            add_clarification(placeholder, "missing")

    return {
        "fields": fields,
        "sources": sources,
        "source_refs": source_refs,
        "unsupported": unsupported,
        "clarifications": clarifications,
        "criteria": criteria,
        "revision": current["revision"],
    }


def _value_schema() -> dict[str, Any]:
    return {
        "anyOf": [
            {"type": "null"},
            {"type": "string"},
            {"type": "number"},
            {"type": "boolean"},
            {
                "type": "array",
                "items": {
                    "anyOf": [
                        {"type": "string"},
                        {"type": "number"},
                        {"type": "boolean"},
                    ]
                },
            },
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                },
                "required": ["start", "end"],
            },
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {"dates": {"type": "array", "items": {"type": "string"}}},
                "required": ["dates"],
            },
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "amount": {"type": "number"},
                    "currency": {"type": "string"},
                    "scope": {"type": "string", "enum": list(_CANONICAL_UNITS)},
                },
                "required": ["amount", "currency", "scope"],
            },
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "amount_cents": {"type": "integer"},
                    "currency": {"type": "string"},
                    "scope": {"type": "string", "enum": list(_CANONICAL_UNITS)},
                },
                "required": ["amount_cents", "currency", "scope"],
            },
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "cents": {"type": "integer"},
                    "currency": {"type": "string"},
                    "scope": {"type": "string", "enum": list(_CANONICAL_UNITS)},
                },
                "required": ["cents", "currency", "scope"],
            },
        ]
    }


def proposal_schema(domain: str, catalog: list[dict[str, Any]], ledger: dict[str, Any]) -> dict[str, Any]:
    """Return the strict provider-facing JSON schema for one ledger state."""

    profile = _profile(domain)
    catalog_map = _catalog_map(catalog)
    current = _validate_ledger_shape(ledger)
    _record_ids(current["records"])
    field_names = list(profile.get("fields", {}))
    record_ids = [record.get("id") for record in current["records"] if isinstance(record.get("id"), str)]
    key_names = field_names + [record.get("key") for record in current["records"] if isinstance(record.get("key"), str)]
    # Keep the source enum non-empty for provider schema compatibility.  The
    # placeholder is not a real source and is rejected by the reducer; normal
    # live requests always carry at least one catalogue entry.
    source_enum = list(catalog_map) or ["__no_customer_source_ref__"]
    common_operation_properties = {
        "target_id": {"anyOf": [{"type": "null"}, {"type": "string"}]},
        "key": {"type": "string", "minLength": 1, "maxLength": 160},
        "field": {"anyOf": [{"type": "null"}, {"type": "string", "enum": field_names}]},
        "value": _value_schema(),
        "strength": {"type": "string", "enum": sorted(_STRENGTHS)},
        "text": {"type": "string", "minLength": 1, "maxLength": 2000},
        "source_refs": {
            "type": "array",
            "minItems": 1,
            "maxItems": 20,
            "items": {"type": "string", "enum": source_enum},
        },
        # Unit is a semantic pricing scope, never a currency spelling.
        # Integer monetary values are already cents; the profile currency
        # is supplied by the domain and must not be encoded in this field.
        "unit": {"anyOf": [{"type": "null"}, {"type": "string", "enum": list(_CANONICAL_UNITS)}]},
    }

    def operation_branch(
        op_name: str,
        status_schema: dict[str, Any],
        target_schema: dict[str, Any],
        *,
        no_preference: bool = False,
    ) -> dict[str, Any]:
        properties = deepcopy(common_operation_properties)
        properties["op"] = {"type": "string", "enum": [op_name]}
        properties["status"] = status_schema
        properties["target_id"] = target_schema
        if no_preference:
            properties["value"] = {"type": "null"}
            properties["unit"] = {"type": "null"}
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": properties,
            "required": sorted(_OP_KEYS),
        }

    active_status = {"type": "string", "enum": ["active", "needs_clarification"]}
    no_preference_target = {"type": "null"}
    if record_ids:
        no_preference_target = {
            "anyOf": [
                {"type": "null"},
                {"type": "string", "enum": record_ids},
            ]
        }
    operation_branches = [
        operation_branch(
            "no_preference",
            {"type": "string", "enum": ["no_preference"]},
            no_preference_target,
            no_preference=True,
        ),
        operation_branch("add", active_status, {"type": "null"}),
    ]
    if record_ids:
        edit_target = {"type": "string", "enum": record_ids}
        operation_branches.extend(
            operation_branch(op_name, active_status, edit_target)
            for op_name in ("replace", "resolve", "retract")
        )
    operation = {"anyOf": operation_branches}
    option = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"label": {"type": "string"}, "value": {"type": "string"}},
        "required": ["label", "value"],
    }
    question = {
        "anyOf": [
            {"type": "null"},
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "criterion_key": {"type": "string", "minLength": 1, "maxLength": 160},
                    "field": {"anyOf": [{"type": "null"}, {"type": "string", "enum": field_names}]},
                    "text": {"type": "string", "minLength": 1},
                    "why": {"type": "string", "minLength": 1},
                    "answer_kind": {"type": "string", "enum": ["single", "multi", "date_choice", "text", "number", "boolean"]},
                    "answer_semantics": {"anyOf": [{"type": "null"}, {"type": "string", "enum": ["requirement_boolean", "preference_boolean"]}]},
                    "options": {"type": "array", "items": option},
                },
                "required": ["criterion_key", "field", "text", "why", "answer_kind", "answer_semantics", "options"],
            },
        ]
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            # The revision is server-owned CAS state.  The provider may only
            # echo the exact base revision supplied with this schema.
            "expected_revision": {"type": "integer", "enum": [current["revision"]]},
            "operations": {"type": "array", "maxItems": 40, "items": operation},
            "action": {"type": "string", "enum": sorted(_ACTIONS)},
            "question": question,
            "assistant_message": {"type": "string"},
            "explanation": {"type": "string"},
        },
        "required": sorted(_PROPOSAL_KEYS),
        "$defs": {
            "profile_field": {"type": "string", "enum": field_names},
            "registered_key": {"type": "string", "enum": sorted(set(key_names)) or ["__no_key__"]},
            "source_ref": {"type": "string", "enum": source_enum},
        },
    }


def review_ledger(
    domain: str,
    ledger: dict[str, Any],
    fields: dict[str, Any],
    unsupported: list[Any],
    *,
    revision: int,
) -> dict[str, Any]:
    """Record an explicit customer review as a ledger revision.

    Reviewed edits have no fabricated chat source. Existing source references
    are carried forward when a value is edited; a newly added reviewed field is
    marked ``customer_review`` with an empty source list and is still compiled
    because the review gate is customer authority.
    """

    profile = _profile(domain)
    current = _validate_ledger_shape(ledger)
    if type(revision) is not int or revision != current["revision"]:
        raise LedgerError("ledger revision does not match review revision")
    if not isinstance(fields, dict) or not isinstance(unsupported, list):
        raise LedgerError("review fields and unsupported values are invalid")
    next_revision = revision + 1
    result = deepcopy(current)
    records = result["records"]
    result["history"].append({
        "revision": next_revision,
        "op": "review_snapshot",
        "record_id": None,
        "target_id": None,
        "key": None,
        "source_refs": [],
        "source_quotes": [],
        "provenance": "customer_review",
        "actor": "customer_review",
        "source_is_current_value_evidence": False,
        "source_entailment": "customer_review_authoritative",
    })
    old_active_by_field = {
        record.get("field"): record
        for record in records
        if record.get("status") not in _TERMINAL_STATUSES and record.get("field") is not None
    }
    reviewed_fields = set(fields)
    for field, value in fields.items():
        if field not in profile.get("fields", {}):
            raise LedgerError(f"unsupported profile field: {field}")
        normal_value, unit, currency = _validate_field_value(profile, field, value, "total" if field == "max_total_cents" else None)
        old = old_active_by_field.get(field)
        reviewed_status = "no_preference" if value is None else "active"
        if old is not None and old.get("status") == reviewed_status and _value_equal(old.get("value"), normal_value) and old.get("unit") == unit:
            continue
        if old is not None:
            old["status"] = "superseded"
            old["updated_revision"] = next_revision
        new = {
            "id": _next_record_id(records),
            "key": field,
            "field": field,
            "value": normal_value,
            "unit": unit,
            "strength": "required",
            "status": reviewed_status,
            "text": f"Customer review {'declined' if reviewed_status == 'no_preference' else 'set'} {field}",
            "source_refs": list(old.get("source_refs", [])) if old else [],
            "source_quotes": list(old.get("source_quotes", [])) if old else [],
            "revision": next_revision,
            "created_revision": next_revision,
            "updated_revision": next_revision,
            "provenance": "customer_review",
            "source_is_current_value_evidence": False,
            "source_entailment": "customer_review_authoritative",
        }
        if currency is not None:
            new["currency"] = currency
        records.append(new)
        result["history"].append({
            "revision": next_revision,
            "op": "review_replace" if old else "review_add",
            "record_id": new["id"],
            "target_id": old.get("id") if old else None,
            "key": field,
            "source_refs": list(new["source_refs"]),
            "source_quotes": list(new["source_quotes"]),
            "provenance": "customer_review",
            "actor": "customer_review",
            "source_is_current_value_evidence": False,
            "source_entailment": "customer_review_authoritative",
        })
    # Removed fields are explicit review retractions; omission from the
    # reviewed snapshot is meaningful because the user approved this exact
    # state. It does not affect unrelated semantic criteria.
    for field, old in old_active_by_field.items():
        if field in reviewed_fields or old.get("strength") != "required":
            continue
        old["status"] = "retracted"
        old["updated_revision"] = next_revision
        result["history"].append({
            "revision": next_revision,
            "op": "review_retract",
            "record_id": old["id"],
            "target_id": old["id"],
            "key": old.get("key"),
            "source_refs": list(old.get("source_refs", [])),
            "source_quotes": list(old.get("source_quotes", [])),
            "provenance": "customer_review",
            "actor": "customer_review",
            "source_is_current_value_evidence": False,
            "source_entailment": "customer_review_authoritative",
        })
    desired_unsupported = {
        item if isinstance(item, str) else item.get("text")
        for item in unsupported
        if isinstance(item, str) or isinstance(item, dict)
    }
    for record in records:
        if (
            record.get("field") is None
            and record.get("strength") == "required"
            and record.get("status") not in _TERMINAL_STATUSES
        ):
            if record.get("text") not in desired_unsupported:
                record["status"] = "retracted"
                record["updated_revision"] = next_revision
                result["history"].append({
                    "revision": next_revision,
                    "op": "review_retract_unsupported",
                    "record_id": record.get("id"),
                    "target_id": record.get("id"),
                    "key": record.get("key"),
                    "source_refs": list(record.get("source_refs", [])),
                    "source_quotes": list(record.get("source_quotes", [])),
                    "provenance": "customer_review",
                    "actor": "customer_review",
                    "source_is_current_value_evidence": False,
                    "source_entailment": "customer_review_authoritative",
                })
    existing_unknown = {record.get("text") for record in records if record.get("field") is None and record.get("status") not in _TERMINAL_STATUSES}
    for index, text_value in enumerate(sorted(value for value in desired_unsupported if value), start=1):
        if text_value in existing_unknown:
            continue
        record = {
            "id": _next_record_id(records),
            "key": f"reviewed:unsupported:{index}",
            "field": None,
            "value": None,
            "unit": None,
            "strength": "required",
            "status": "needs_clarification",
            "text": text_value,
            "source_refs": [],
            "source_quotes": [],
            "revision": next_revision,
            "created_revision": next_revision,
            "updated_revision": next_revision,
            "provenance": "customer_review",
            "source_is_current_value_evidence": False,
            "source_entailment": "customer_review_authoritative",
        }
        records.append(record)
        result["history"].append({
            "revision": next_revision,
            "op": "review_add_unsupported",
            "record_id": record["id"],
            "target_id": None,
            "key": record["key"],
            "source_refs": [],
            "source_quotes": [],
            "provenance": "customer_review",
            "actor": "customer_review",
            "source_is_current_value_evidence": False,
            "source_entailment": "customer_review_authoritative",
        })
    _check_conflicts(records)
    result["revision"] = next_revision
    return result


__all__ = [
    "LedgerError",
    "bootstrap_ledger",
    "compile_ledger",
    "empty_ledger",
    "proposal_schema",
    "reduce_ledger",
    "review_ledger",
]
