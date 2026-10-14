"""Provider-facing structured contract for the adaptive interpreter.

The adaptive model receives a small catalogue of exact customer-source spans.
It returns references into that catalogue instead of copying quotations.  The
server then hydrates those references back into the legacy envelope consumed by
the existing grounding and planner validators.  This keeps the model useful
for arbitrary domains while making provenance a deterministic application
operation.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
from typing import Any

from app.profile_registry import get_profile


_MAX_CATALOG_CHARS = 15000
_MAX_SEGMENT_CHARS = 80
_MAX_SEGMENTS = 80
_CLAUSE_BREAK = re.compile(r"\s+(?=(?:and|or|but|with|plus|also)\s+)", re.IGNORECASE)


class StructuredIntentError(ValueError):
    """Provider structured output cannot be safely grounded."""


_DEFAULT_REVIEW_GUIDANCE = (
    "Review your original request and the captured requirements before approving."
)


def _user_source_texts(source_text: str | None,
                       source_messages: list[dict[str, Any]] | None) -> list[str]:
    """Return customer turns only; interface and merchant data never enter."""
    turns: list[str] = []
    for item in source_messages or []:
        if not isinstance(item, dict):
            continue
        if item.get("role") in {"user", "customer"} and isinstance(item.get("content"), str):
            # Keep the original message bytes for offset-backed refs. The
            # caller's bounded conversation is already size-limited.
            if item["content"].strip():
                turns.append(item["content"])
    if turns:
        return turns
    if isinstance(source_text, str) and source_text.strip():
        return [source_text]
    return []


def _chunk_spans(text: str) -> list[tuple[int, int]]:
    """Return exact source offsets without normalizing customer whitespace."""
    sentence_bounds = [0]
    for match in re.finditer(r"[.!?;\n]+", text):
        sentence_bounds.append(match.end())
    if sentence_bounds[-1] != len(text):
        sentence_bounds.append(len(text))
    spans: list[tuple[int, int]] = []
    for sentence_start, sentence_end in zip(sentence_bounds, sentence_bounds[1:]):
        if sentence_end <= sentence_start:
            continue
        local = text[sentence_start:sentence_end]
        clause_starts = [sentence_start]
        for match in _CLAUSE_BREAK.finditer(local):
            clause_starts.append(sentence_start + match.end())
        clause_starts = sorted(set(clause_starts))
        clause_bounds = clause_starts + [sentence_end]
        for clause_start, clause_end in zip(clause_bounds, clause_bounds[1:]):
            # Trim only boundary whitespace by moving the offsets; the text
            # stored for a ref remains the exact original slice.
            while clause_start < clause_end and text[clause_start].isspace():
                clause_start += 1
            while clause_end > clause_start and text[clause_end - 1].isspace():
                clause_end -= 1
            if clause_start >= clause_end:
                continue
            word_start = clause_start
            last_end = clause_start
            for word in re.finditer(r"\S+", text[clause_start:clause_end]):
                start = clause_start + word.start()
                end = clause_start + word.end()
                if end - word_start > _MAX_SEGMENT_CHARS and last_end > word_start:
                    spans.append((word_start, last_end))
                    word_start = start
                last_end = end
            if word_start < last_end:
                spans.append((word_start, last_end))
    return spans


def build_source_catalog(source_text: str | None = None,
                         source_messages: list[dict[str, Any]] | None = None) -> list[dict[str, str]]:
    """Build opaque refs containing turn, offsets, and a source hash.

    IDs identify one contiguous span of one customer message. Including the
    source hash makes a ref from a different conversation impossible to reuse;
    the offsets make the provenance auditable without asking the model to copy
    quote text. A bounded character budget prevents source text from becoming
    an unbounded model input.
    """
    turns = _user_source_texts(source_text, source_messages)
    catalog: list[dict[str, str]] = []
    used = 0
    records = [
        (turn_index, text,
         hashlib.sha256(text.encode("utf-8")).hexdigest()[:12],
         _chunk_spans(text))
        for turn_index, text in enumerate(turns, start=1)
    ]
    # First reserve whole-turn refs for every customer turn. This guarantees a
    # later correction remains citeable even when clause refs consume the
    # remaining entry budget.
    whole_turn_ids: set[tuple[int, int, int]] = set()
    for turn_index, text, source_hash, _spans in records:
        if used + len(text) <= _MAX_CATALOG_CHARS and len(catalog) < _MAX_SEGMENTS:
            catalog.append({
                "id": f"t{turn_index}p0e{len(text)}h{source_hash}",
                "text": text,
            })
            used += len(text)
            whole_turn_ids.add((turn_index, 0, len(text)))
    # Fill spare entries with exact compact spans for easier provenance
    # selection. The whole-turn refs above are never removed or overwritten.
    for turn_index, text, source_hash, spans in records:
        for start, end in spans:
            if len(catalog) >= _MAX_SEGMENTS:
                return catalog
            if (turn_index, start, end) in whole_turn_ids:
                continue
            # The span builder keeps each source span within the preferred
            # size. Do not slice here: an offset-backed ref must never lose
            # the tail of a customer clause.
            if used + (end - start) > _MAX_CATALOG_CHARS:
                continue
            catalog.append({
                "id": f"t{turn_index}p{start}e{end}h{source_hash}",
                "text": text[start:end],
            })
            used += end - start
    return catalog


def source_catalog_digest(catalog: list[dict[str, str]]) -> str:
    """Return a stable digest for trace metadata without logging source text."""
    encoded = json.dumps(catalog, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _profile_value_schema(spec: dict[str, Any]) -> dict[str, Any]:
    field_type = spec.get("type")
    if field_type == "integer":
        return {"type": "integer"}
    if field_type == "boolean":
        return {"type": "boolean"}
    if field_type == "strings":
        return {"type": "array", "items": {"type": "string"}}
    if field_type == "window":
        return {
            "type": "array", "items": {"type": "string"},
        }
    if field_type == "date_choice":
        return {
            "anyOf": [
                {"type": "string"},
                {
                    "type": "object", "additionalProperties": False,
                    "properties": {"start": {"type": "string"},
                                   "end": {"type": "string"}},
                    "required": ["start", "end"],
                },
                {
                    "type": "object", "additionalProperties": False,
                    "properties": {"dates": {"type": "array", "items": {"type": "string"}}},
                    "required": ["dates"],
                },
            ]
        }
    return {"type": "string"}


def _claim_schema(profile_fields: dict[str, Any], refs: list[str]) -> dict[str, Any]:
    alternatives = []
    for field, spec in profile_fields.items():
        alternatives.append({
            "type": "object", "additionalProperties": False,
            "properties": {
                "field": {"type": "string", "enum": [field]},
                "value": _profile_value_schema(spec),
                "source_ref": {"$ref": "#/$defs/source_ref"},
            },
            "required": ["field", "value", "source_ref"],
        })
    return {"type": "array", "items": {"anyOf": alternatives}}


def response_schema(domain: str, catalog: list[dict[str, str]]) -> dict[str, Any]:
    """Return the strict provider schema for one profile and source catalogue."""
    profile_fields = get_profile(domain).get("fields", {})
    field_names = list(profile_fields)
    refs = [item["id"] for item in catalog]
    # A source-less request can still be reviewed, but no model claim may cite
    # a fabricated reference. The empty enum is avoided because some provider
    # schema validators reject it; hydration still drops unknown refs.
    ref_enum = refs or ["__no_customer_source_ref__"]
    criterion_keys = field_names + refs
    required_field_names = [
        field for field, spec in profile_fields.items() if spec.get("required")
    ]
    field_ref = {"$ref": "#/$defs/profile_field"}
    key_ref = {"$ref": "#/$defs/registered_key"}
    source_ref = {"$ref": "#/$defs/source_ref"}
    option = {
        "type": "object", "additionalProperties": False,
        "properties": {"label": {"type": "string"},
                       "value": {"type": "string"}},
        "required": ["label", "value"],
    }
    question = {
        "anyOf": [
            {"type": "null"},
            {"type": "object", "additionalProperties": False,
             "properties": {
                 "criterion_key": key_ref,
                 "text": {"type": "string"},
                 "why": {"type": "string"},
                 "answer_kind": {"type": "string", "enum": ["single", "multi", "date_choice", "text", "number", "boolean"]},
                 "answer_semantics": {"anyOf": [{"type": "null"}, {"type": "string", "enum": ["requirement_boolean", "preference_boolean"]}]},
                 "options": {"type": "array", "items": option},
             }, "required": ["criterion_key", "text", "why", "answer_kind", "answer_semantics", "options"]},
        ]
    }
    criterion_kind = {"type": "string", "enum": ["requirement", "preference", "ambiguity"]}
    criterion_status = {"type": "string", "enum": ["captured", "needs_clarification", "declined", "unsupported"]}
    profile_criterion_with_ref = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "key": field_ref,
            "source_ref": source_ref,
            "kind": criterion_kind,
            "status": criterion_status,
        },
        "required": ["key", "source_ref", "kind", "status"],
    }
    profile_criterion_missing = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "key": {"type": "string", "enum": required_field_names or ["__no_required_profile_field__"]},
            "source_ref": {"type": "null"},
            "kind": criterion_kind,
            "status": criterion_status,
        },
        "required": ["key", "source_ref", "kind", "status"],
    }
    generic_criterion = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "key": {"type": "string", "enum": refs or ["__no_customer_source_id__"]},
            "kind": criterion_kind,
            "status": criterion_status,
        },
        "required": ["key", "kind", "status"],
    }
    criterion = {
        "anyOf": [
            {"anyOf": [profile_criterion_with_ref, profile_criterion_missing]},
            generic_criterion,
        ],
    }
    clarification = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "field": field_ref,
            "source_ref": source_ref,
            "reason": {"type": "string", "enum": ["ambiguous", "preference", "missing"]},
        },
        "required": ["field", "source_ref", "reason"],
    }
    return {
        "type": "object", "additionalProperties": False,
        "properties": {
            "supported_claims": _claim_schema(profile_fields, ref_enum),
            "unsupported": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {"source_ref": source_ref}, "required": ["source_ref"]}},
            "clarifications": {"type": "array", "items": clarification},
            "criteria": {"type": "array", "items": criterion},
            "action": {"type": "string", "enum": ["ask_user", "inspect_offers", "retrieve_policy", "ready_for_review", "review_required"]},
            "assistant_message": {"type": "string"},
            "question": question,
            "explanation": {"type": "string"},
            "offer_observations": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["supported_claims", "unsupported", "clarifications", "criteria", "action", "assistant_message", "question", "explanation", "offer_observations"],
        "$defs": {
            "source_ref": {"type": "string", "enum": ref_enum},
            "registered_key": {"type": "string", "enum": criterion_keys or field_names},
            "profile_field": {"type": "string", "enum": field_names},
        },
    }


def _catalog_map(catalog: list[dict[str, str]]) -> dict[str, str]:
    return {item.get("id"): item.get("text") for item in catalog if isinstance(item, dict) and isinstance(item.get("id"), str) and isinstance(item.get("text"), str)}


def hydrate_response(raw: Any, *, domain: str, catalog: list[dict[str, str]],
                     require_wire: bool = False) -> Any:
    """Hydrate a structured response into the legacy envelope.

    Legacy provider fixtures remain accepted by direct callers during rollout.
    Real adaptive transport passes ``require_wire=True`` so a provider cannot
    silently fall back to the fragile legacy shape. Structured output with an
    unknown source ref fails closed so a model can never manufacture customer
    provenance by naming a near-match ID.
    """
    if not isinstance(raw, dict) or "supported_claims" not in raw:
        if require_wire:
            raise StructuredIntentError("adaptive response omitted the structured wire contract")
        return raw
    expected_keys = {
        "supported_claims", "unsupported", "clarifications", "criteria",
        "action", "assistant_message", "question", "explanation",
        "offer_observations",
    }
    if set(raw) != expected_keys:
        raise StructuredIntentError("structured response has unexpected top-level keys")
    refs = _catalog_map(catalog)
    profile_fields = get_profile(domain).get("fields", {})
    field_names = set(profile_fields)
    registered_keys = field_names | set(refs)

    def require_ref(ref: Any, where: str) -> str:
        if not isinstance(ref, str) or ref not in refs:
            raise StructuredIntentError(f"{where} cites an unknown customer source ref")
        return ref

    fields: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for claim in raw.get("supported_claims") or []:
        if not isinstance(claim, dict) or set(claim) != {"field", "value", "source_ref"}:
            raise StructuredIntentError("supported claim shape is invalid")
        field, value = claim.get("field"), claim.get("value")
        ref = require_ref(claim.get("source_ref"), "supported claim")
        if field not in field_names or value is None:
            raise StructuredIntentError("supported claim targets an out-of-scope field")
        if field in fields:
            if fields[field] != value or sources[field] != refs[ref]:
                raise StructuredIntentError("conflicting duplicate supported claim")
            continue
        fields[field] = deepcopy(value)
        sources[field] = refs[ref]

    unsupported: list[str] = []
    for item in raw.get("unsupported") or []:
        if not isinstance(item, dict) or set(item) != {"source_ref"}:
            raise StructuredIntentError("unsupported condition shape is invalid")
        ref = require_ref(item.get("source_ref"), "unsupported condition")
        if refs[ref] not in unsupported:
            unsupported.append(refs[ref])

    clarifications: list[dict[str, Any]] = []
    for item in raw.get("clarifications") or []:
        if not isinstance(item, dict) or set(item) != {"field", "source_ref", "reason"}:
            raise StructuredIntentError("clarification shape is invalid")
        ref = require_ref(item.get("source_ref"), "clarification")
        field, reason = item.get("field"), item.get("reason")
        if field not in field_names:
            raise StructuredIntentError("clarification targets an out-of-scope field")
        if reason not in {"ambiguous", "preference", "missing"}:
            raise StructuredIntentError("clarification reason is invalid")
        row = {"field": field, "source_quote": refs[ref], "reason": reason}
        if row not in clarifications:
            clarifications.append(row)

    criteria: list[dict[str, Any]] = []
    criteria_by_key: dict[str, dict[str, Any]] = {}
    for item in raw.get("criteria") or []:
        if not isinstance(item, dict) or "key" not in item:
            raise StructuredIntentError("criterion shape is invalid")
        key = item.get("key")
        if key not in registered_keys:
            raise StructuredIntentError("criterion key is out of scope")
        expected_keys = (
            {"key", "kind", "status"}
            if key in refs else
            {"key", "source_ref", "kind", "status"}
        )
        if set(item) != expected_keys:
            raise StructuredIntentError("criterion shape is invalid")
        raw_ref = item.get("source_ref") if key in field_names else key
        kind = item.get("kind")
        status = item.get("status")
        if kind not in {"requirement", "preference", "ambiguity"}:
            raise StructuredIntentError("criterion kind is invalid")
        if status not in {"captured", "needs_clarification", "declined", "unsupported"}:
            raise StructuredIntentError("criterion status is invalid")
        field = key if key in field_names else None
        if raw_ref is None:
            if (
                key not in field_names
                or not profile_fields[key].get("required")
                or key in fields
                or status != "needs_clarification"
            ):
                raise StructuredIntentError("only a missing required profile criterion may omit source ref")
            ref = None
        else:
            ref = require_ref(raw_ref, "criterion")
        row = {
            "key": key, "field": field,
            "text": refs[ref] if ref is not None else profile_fields[key].get("label", key),
            "source_quote": refs[ref] if ref is not None else None,
            "kind": kind,
            "status": status,
            "verification": "supported" if field in field_names else "unsupported",
        }
        previous = criteria_by_key.get(key)
        if previous is not None:
            if previous != row:
                raise StructuredIntentError("conflicting duplicate criterion")
            continue
        criteria_by_key[key] = row
        criteria.append(row)

    question = raw.get("question")
    hydrated_question = None
    if question is not None:
        if not isinstance(question, dict) or set(question) != {
            "criterion_key", "text", "why", "answer_kind",
            "answer_semantics", "options",
        }:
            raise StructuredIntentError("question shape is invalid")
        question_key = question.get("criterion_key")
        if question_key not in registered_keys:
            raise StructuredIntentError("question target is out of scope")
        question_field = question_key if question_key in field_names else None
        # A source-id question remains source-bound even if the model omitted
        # the separate criteria row. Bind that exact source condition here;
        # the question text remains model-generated and is never synthesized.
        if question_key in refs and question_key not in criteria_by_key:
            row = {
                "key": question_key, "field": question_field,
                "text": refs[question_key], "source_quote": refs[question_key],
                "kind": "ambiguity", "status": "needs_clarification",
                "verification": "supported" if question_field in field_names else "unsupported",
            }
            criteria.append(row)
            criteria_by_key[question_key] = row
        hydrated_question = deepcopy(question)
        hydrated_question["field"] = question_field
    result = {
        "fields": fields, "sources": sources, "unsupported": unsupported,
        "clarifications": clarifications,
        "explanation": (
            raw.get("explanation")
            if isinstance(raw.get("explanation"), str) and raw.get("explanation").strip()
            else _DEFAULT_REVIEW_GUIDANCE
        ),
        "criteria": criteria, "action": raw.get("action"),
        "assistant_message": raw.get("assistant_message"), "question": hydrated_question,
        "offer_observations": raw.get("offer_observations"),
    }
    return result

