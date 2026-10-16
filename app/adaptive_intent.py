"""Shared, model-directed intent planning.

The adaptive layer is deliberately an interpreter and tool router.  It can
propose a useful next question or request read-only commerce context, but it
cannot approve requirements or a purchase.  The legacy five-key extraction
envelope remains the only payload that can reach customer review and the
deterministic rules engine.

This module contains the small, provider-independent pieces of the adaptive
contract so they can be tested without a network call.  Provider calls stay in
``app.ai_pipeline``; tool calls here are read-only and return merchant facts as
data with explicit provenance.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
from typing import Any, Callable


PLAN_ACTIONS = {
    "ask_user",
    "inspect_offers",
    "retrieve_policy",
    "ready_for_review",
    "review_required",
}
ANSWER_KINDS = {"single", "multi", "date_choice", "text", "number", "boolean"}
CRITERION_KINDS = {"requirement", "preference", "ambiguity"}
TOOL_ACTIONS = {"inspect_offers", "retrieve_policy"}
_SAFE_DIAGNOSTIC_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,79}$")


class AdaptivePlanError(ValueError):
    """The model returned a plan that cannot safely be shown to a customer."""


def _bounded_text(value: Any, limit: int = 800) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _stable_id(*parts: Any) -> str:
    encoded = json.dumps(parts, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "q_" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _draft_from_model(raw: Any) -> dict[str, Any]:
    """Extract the legacy envelope from either supported adaptive shape.

    During rollout, a provider may return the five-key envelope beside the
    planner keys or nested under ``draft``.  Supporting both makes the change
    compatible with earlier staged prompt fixtures while the strict grounding
    validator still rejects unknown/invalid envelope values.
    """
    if not isinstance(raw, dict):
        return {}
    if isinstance(raw.get("draft"), dict):
        nested = raw["draft"]
        if any(k in nested for k in ("fields", "sources", "unsupported", "clarifications")):
            return deepcopy(nested)
    return {key: deepcopy(raw[key]) for key in (
        "fields", "sources", "unsupported", "clarifications", "explanation"
    ) if key in raw}


def _source_texts(source_text: str, source_messages: list[dict[str, Any]] | None) -> list[str]:
    values = [source_text or ""]
    for item in source_messages or []:
        if not isinstance(item, dict):
            continue
        if item.get("role") == "user" and isinstance(item.get("content"), str):
            values.append(item["content"])
    return values


def _trusted_observations(tool_result: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Expose only facts that came from the executed read-only tool.

    Planner prose is never accepted as a merchant assertion.  In particular,
    there is no model-generated ``pass``/``match`` status in this view.
    """
    if (
        not isinstance(tool_result, dict)
        or tool_result.get("tool") != "inspect_offers"
        or tool_result.get("status") != "ok"
        or tool_result.get("read_only") is not True
        or not isinstance(tool_result.get("offers"), list)
    ):
        return []
    observations: list[dict[str, Any]] = []
    for offer in tool_result["offers"]:
        if not isinstance(offer, dict):
            continue
        offer_id = offer.get("id")
        offer_hash = offer.get("offer_hash")
        facts = offer.get("facts")
        if (
            not isinstance(offer_id, str) or not offer_id.strip()
            or not isinstance(offer_hash, str) or not offer_hash.strip()
            or not isinstance(facts, dict)
            or offer.get("signed") is not True
            or offer.get("provenance") != "merchant-signed checkout payload"
        ):
            continue
        observations.append({
            "offer_id": offer_id[:160],
            "offer_hash": offer_hash[:160],
            "facts": deepcopy(facts),
            "signed": True,
            "provenance": "merchant-signed checkout payload",
        })
    return observations[:8]


def _verified_offer_facts(offer: Any) -> dict[str, Any] | None:
    """Return facts only when the adapter marked the signed payload as trusted."""
    if not isinstance(offer, dict):
        return None
    if (
        offer.get("signed") is not True
        or offer.get("provenance") != "merchant-signed checkout payload"
        or not isinstance(offer.get("offer_hash"), str)
        or not offer.get("offer_hash", "").strip()
        or not isinstance(offer.get("facts"), dict)
    ):
        return None
    return offer["facts"]


def _candidate_offer_check(domain: str, key: str, requirement: Any,
                           facts: dict[str, Any] | None) -> dict[str, Any]:
    """Map the deterministic rules result into an unapproved advisory check."""
    from app.profile_registry import get_profile
    from app.rules_engine import evaluate

    base = {
        "check_id": key,
        "requirement": deepcopy(requirement),
        "status": "UNKNOWN",
        "offer_value": None,
    }
    profile = get_profile(domain)
    if facts is None:
        base["message"] = "The signed offer facts cannot verify this candidate requirement."
        return base
    try:
        result = evaluate(profile, {key: deepcopy(requirement)}, facts)
    except (TypeError, ValueError, KeyError):
        base["message"] = "The signed offer facts cannot verify this candidate requirement."
        return base
    checks = result.get("checks") if isinstance(result, dict) else None
    check = checks[0] if isinstance(checks, list) and checks and isinstance(checks[0], dict) else None
    if check is None:
        base["message"] = "The signed offer facts cannot verify this candidate requirement."
        return base
    raw_status = check.get("status")
    if raw_status == "pass":
        base["status"] = "MATCH"
        base["offer_value"] = deepcopy(check.get("offer_value"))
        base["message"] = "The signed merchant fact matches the grounded draft requirement; advisory only."
    elif raw_status == "fail":
        base["status"] = "CONFLICT"
        base["offer_value"] = deepcopy(check.get("offer_value"))
        base["message"] = "The signed merchant fact conflicts with the grounded draft requirement; advisory only."
    else:
        # Rules-engine missing/invalid values are intentionally not surfaced as
        # offer claims. They remain unknown until a verified fact is available.
        base["status"] = "UNKNOWN"
        base["message"] = "Signed merchant facts cannot verify the grounded draft requirement; comparison is unknown."
    return base


def _draft_comparison(domain: str, fields: dict[str, Any], offer: dict[str, Any]) -> dict[str, Any]:
    """Build an advisory, unapproved comparison for one merchant offer."""
    facts = _verified_offer_facts(offer)
    checks = [
        _candidate_offer_check(domain, key, value, facts)
        for key, value in list(fields.items())[:30]
        if isinstance(key, str)
    ]
    if not checks:
        checks = [{
            "check_id": "candidate_requirements",
            "requirement": None,
            "status": "UNKNOWN",
            "offer_value": None,
            "message": "No typed candidate requirements were available for comparison.",
        }]
    return {
        "status": "UNAPPROVED",
        "checks": checks,
        "advisory": True,
        "basis": "grounded candidate fields versus verified merchant-signed facts",
    }


def _quote_is_customer_source(quote: Any, source_text: str,
                              source_messages: list[dict[str, Any]] | None) -> bool:
    if not isinstance(quote, str) or not quote.strip():
        return False
    folded = quote.casefold()
    return any(folded in candidate.casefold() for candidate in _source_texts(source_text, source_messages))


def source_quote_is_customer(quote: Any, source_text: str,
                             source_messages: list[dict[str, Any]] | None = None) -> bool:
    """Public provenance check used when persisting generic criteria."""
    return _quote_is_customer_source(quote, source_text, source_messages)


def _criteria_from_draft(draft: dict[str, Any], source_text: str, domain: str,
                         source_messages: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Create a conservative criterion view for the planner input.

    This is only context for the model.  It never replaces the model's
    source-grounded envelope and never turns an unsupported phrase into an
    enforceable field.
    """
    result: list[dict[str, Any]] = []
    fields = draft.get("fields") if isinstance(draft.get("fields"), dict) else {}
    from app.profile_registry import get_profile
    profile_fields = get_profile(domain).get("fields", {})
    sources = draft.get("sources") if isinstance(draft.get("sources"), dict) else {}
    for field, value in fields.items():
        quote = sources.get(field)
        result.append({
            "key": field,
            "field": field,
            "text": f"{field}: {value}",
            "source_quote": quote if _quote_is_customer_source(quote, source_text, source_messages) else None,
            "kind": "requirement",
            "verification": "supported" if field in profile_fields else "unsupported",
            "status": "captured",
        })
    for item in draft.get("clarifications") or []:
        if not isinstance(item, dict):
            continue
        quote = item.get("source_quote")
        if not _quote_is_customer_source(quote, source_text, source_messages):
            continue
        field = item.get("field") if isinstance(item.get("field"), str) else None
        result.append({
            "key": field or _stable_id("clarification", quote),
            "field": field,
            "text": _bounded_text(quote),
            "source_quote": quote,
            "kind": "preference" if item.get("reason") == "preference" else "ambiguity",
            "verification": "supported" if field in profile_fields else "unsupported",
            "status": "needs_clarification",
        })
    for item in draft.get("unsupported") or []:
        if not isinstance(item, str) or not item.strip():
            continue
        # Unsupported entries are expected to be copied from customer prose by
        # the grounding validator.  Keep only source-backed context here.
        if _quote_is_customer_source(item, source_text, source_messages):
            result.append({
                "key": _stable_id("unsupported", item),
                "field": None,
                "text": item,
                "source_quote": item,
                "kind": "requirement",
                "verification": "unsupported",
                "status": "needs_clarification",
            })
    return result[:40]


def _last_question_sentence(assistant_message: Any) -> str:
    if not isinstance(assistant_message, str):
        return ""
    matches = re.findall(r"[^.!?]{2,500}\?", assistant_message)
    return matches[-1].strip() if matches else ""


def _airport_question_scope_is_mixed(field: Any, text: str) -> bool:
    """Reject a one-field question that also asks for the other route end.

    Airport widget replies are serialized against the server-owned ``field``.
    A model question that says “which London airport ... and which Toronto
    airport” still has only one binding, so the UI would serialize every
    selected code into (for example) ``origin_airports``.  Fail closed at the
    planner boundary rather than allowing a geographically mixed choice set to
    become a typed requirement.  The next review pass can emit a field-scoped
    question; the customer can always edit the route in structured review.
    """
    if field not in {"origin_airports", "destination_airports"}:
        return False
    normalized = text.casefold()
    origin_terms = r"\b(?:depart(?:ure)?|origin|leave)\w*\b"
    destination_terms = r"\b(?:arriv(?:e|al)?|destination)\w*\b"
    has_origin = bool(re.search(origin_terms, normalized))
    has_destination = bool(re.search(destination_terms, normalized))
    return has_origin and has_destination


def airport_question_validation_feedback(raw_question: Any, domain: str) -> str | None:
    """Describe a malformed route question for the bounded review pass.

    This is feedback for the independent second model call.  It intentionally
    does not synthesize a replacement question; the reviewer must repair the
    candidate or leave the plan in ``review_required``.
    """
    if not isinstance(raw_question, dict) or domain != 'flight':
        return None
    field = raw_question.get('field') or raw_question.get('criterion_key')
    text = _bounded_text(raw_question.get('text') or raw_question.get('question'), 500)
    if _airport_question_scope_is_mixed(field, text):
        return (
            'The candidate airport question combines departure and arrival route ends. '
            'Repair it to target exactly one field (origin_airports or '
            'destination_airports), with catalog options only for that field; '
            'preserve multi-airport answers instead of forcing one airport.'
        )
    return None


def _safe_diagnostic_identifier(value: Any) -> str | None:
    """Return an identifier safe to include in a persisted diagnostic.

    Planner diagnostics are evidence about a rejected model shape, not a copy
    of model prose.  Keep only short lower-case identifiers; arbitrary text,
    HTML, punctuation, and long provider values are omitted entirely.
    """
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if _SAFE_DIAGNOSTIC_IDENTIFIER.fullmatch(value) else None


def planner_question_validation_feedback(
    raw_question: Any,
    *,
    domain: str,
    source_text: str = "",
    source_messages: list[dict[str, Any]] | None = None,
    criteria: list[dict[str, Any]] | None = None,
    draft: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return bounded, source-aware diagnostics for a rejected planner question.

    The normalizer deliberately fails closed when a question cannot be bound
    to a source-backed criterion or required profile field.  This companion
    validator explains that rejection to the independent reviewer without
    copying the rejected question, its ``why`` prose, or unsafe identifiers
    into the reviewer payload or the durable trace.  It never creates a
    replacement question.
    """
    from app.profile_registry import get_profile

    profile_fields = get_profile(domain).get("fields", {})
    source_criteria: list[str] = []
    criterion_by_key: dict[str, dict[str, Any]] = {}
    declined_keys: set[str] = set()
    for item in (criteria or [])[:40]:
        if not isinstance(item, dict):
            continue
        key = _safe_diagnostic_identifier(item.get("key") or item.get("field"))
        quote = item.get("source_quote")
        if not key:
            continue
        if item.get("status") == "declined":
            declined_keys.add(key)
            criterion_by_key.setdefault(key, item)
            continue
        if not _quote_is_customer_source(quote, source_text, source_messages):
            continue
        if key not in source_criteria:
            source_criteria.append(key)
        criterion_by_key.setdefault(key, item)

    fields = draft.get("fields") if isinstance(draft, dict) else {}
    fields = fields if isinstance(fields, dict) else {}
    required_missing = [
        field for field, spec in profile_fields.items()
        if isinstance(spec, dict) and spec.get("required") and field not in fields
    ]

    if not isinstance(raw_question, dict):
        return {
            "codes": ["question_missing"],
            "valid_criterion_keys": source_criteria[:20],
            "required_missing_fields": required_missing[:20],
        }

    codes: list[str] = []
    raw_key = raw_question.get("criterion_key") or raw_question.get("field") or raw_question.get("key")
    key = _safe_diagnostic_identifier(raw_key)
    if not key:
        codes.append("question_criterion_key_unsafe" if raw_key else "question_missing_criterion_key")
    text = _bounded_text(raw_question.get("text") or raw_question.get("question"), 500)
    why = _bounded_text(raw_question.get("why"), 500)
    if not text:
        codes.append("question_missing_text")
    if not why:
        codes.append("question_missing_why")
    answer_kind = raw_question.get("answer_kind") or raw_question.get("response_type") or "text"
    if answer_kind not in ANSWER_KINDS:
        codes.append("question_invalid_answer_kind")

    criterion = criterion_by_key.get(key) if key else None
    is_required_profile_gap = bool(
        key in profile_fields
        and key not in source_criteria
        and profile_fields[key].get("required")
    ) if key else False
    if key and key not in source_criteria and key not in declined_keys and not is_required_profile_gap:
        codes.append("question_criterion_key_unbound")
    if key in declined_keys:
        codes.append("question_declined_criterion")

    raw_field = raw_question.get("field")
    field = raw_field if isinstance(raw_field, str) and raw_field in profile_fields else None
    if raw_field is not None and field is None:
        codes.append("question_field_unbound")
    criterion_field = criterion.get("field") if isinstance(criterion, dict) else None
    if isinstance(criterion_field, str) and criterion_field in profile_fields and field is None:
        field = criterion_field
    if is_required_profile_gap and field is None:
        field = key
    if is_required_profile_gap and raw_field is not None and raw_field != key:
        codes.append("question_profile_field_mismatch")

    if (key in profile_fields and key not in source_criteria
            and not profile_fields[key].get("required") and not any(
        word in why.casefold()
        for word in {"offer", "policy", "term", "availability", "risk", "mismatch", "difference", "material", "affect"}
    )):
        codes.append("question_optional_profile_gap_reason_missing")

    criterion_texts = {
        str(value).strip().casefold()
        for value in (
            criterion.get("text") if isinstance(criterion, dict) else None,
            criterion.get("source_quote") if isinstance(criterion, dict) else None,
        )
        if isinstance(value, str) and value.strip()
    }
    if text and text.casefold() in criterion_texts:
        codes.append("question_repeats_source_text")
    if domain == "flight" and _airport_question_scope_is_mixed(raw_field or raw_key, text):
        codes.append("question_mixed_route_scope")

    # A diagnostic with no rejection code would add noise to the trace.  A
    # caller should only persist this object when the normalizer rejected the
    # question; the empty case is therefore intentionally omitted.
    if not codes:
        return None
    result: dict[str, Any] = {
        "codes": list(dict.fromkeys(codes))[:12],
        "valid_criterion_keys": source_criteria[:20],
        "required_missing_fields": required_missing[:20],
    }
    if key:
        result["criterion_key"] = key
    if field:
        result["field"] = field
    return result


def planner_validation_feedback(
    raw_plan: Any,
    normalized_plan: dict[str, Any] | None,
    *,
    domain: str,
    source_text: str = "",
    source_messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Explain only planner failures that survived normalization.

    A raw question may be repaired by ``_normalize_question`` (for example,
    when its text repeats a source phrase but the assistant message contains
    the actual customer-facing question).  Diagnostics are therefore gated on
    the normalized result: a question is rejected only when an ``ask_user``
    plan has no normalized question.  Invalid actions are reported separately,
    including when no question was supplied.
    """
    raw = raw_plan if isinstance(raw_plan, dict) else {}
    normalized = normalized_plan if isinstance(normalized_plan, dict) else {}
    criteria = raw.get("criteria") if isinstance(raw.get("criteria"), list) else None
    draft = _draft_from_model(raw)
    raw_action = raw.get("action")
    action_invalid = raw_action not in PLAN_ACTIONS
    question_diagnostic = None
    if raw_action == "ask_user" and normalized.get("question") is None:
        question_diagnostic = planner_question_validation_feedback(
            raw.get("question"),
            domain=domain,
            source_text=source_text,
            source_messages=source_messages,
            criteria=criteria,
            draft=draft,
        )
    if not action_invalid and question_diagnostic is None:
        return None
    if action_invalid:
        target_diagnostic = planner_question_validation_feedback(
            None,
            domain=domain,
            source_text=source_text,
            source_messages=source_messages,
            criteria=criteria,
            draft=draft,
        ) or {}
        diagnostic: dict[str, Any] = {
            "codes": ["planner_action_invalid"],
            "valid_criterion_keys": target_diagnostic.get("valid_criterion_keys", [])[:20],
            "required_missing_fields": target_diagnostic.get("required_missing_fields", [])[:20],
        }
        return diagnostic
    return question_diagnostic


def format_planner_question_validation_feedback(diagnostic: dict[str, Any] | None) -> str | None:
    """Format sanitized planner diagnostics for the independent reviewer."""
    if not isinstance(diagnostic, dict) or not diagnostic.get("codes"):
        return None
    codes = [code for code in diagnostic.get("codes", []) if isinstance(code, str)][:12]
    if not codes:
        return None
    prefix = (
        "planner_validation_failed"
        if "planner_action_invalid" in codes
        else "planner_question_validation_failed"
    )
    parts = [prefix, f"codes={','.join(codes)}"]
    for name in ("criterion_key", "field"):
        value = _safe_diagnostic_identifier(diagnostic.get(name))
        if value:
            parts.append(f"{name}={value}")
    for name in ("valid_criterion_keys", "required_missing_fields"):
        values = [
            value for value in diagnostic.get(name, [])
            if _safe_diagnostic_identifier(value)
        ][:20]
        if values:
            parts.append(f"{name}={','.join(values)}")
    parts.append("repair_question_with_bounded_targets")
    return ";".join(parts)[:1200]


def _normalize_question(raw: Any, *, domain: str, criteria: list[dict[str, Any]],
                        assistant_message: Any = None) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    text = _bounded_text(raw.get("text") or raw.get("question"), 500)
    why = _bounded_text(raw.get("why"), 500)
    key = raw.get("criterion_key") or raw.get("field") or raw.get("key")
    if not isinstance(key, str) or not key.strip() or not text or not why:
        return None
    kind = raw.get("answer_kind") or raw.get("response_type") or "text"
    if kind not in ANSWER_KINDS:
        return None
    answer_semantics = raw.get("answer_semantics")
    if answer_semantics not in {"requirement_boolean", "preference_boolean", None}:
        answer_semantics = None
    options: list[dict[str, str]] = []
    raw_options = raw.get("options")
    if isinstance(raw_options, list):
        for option in raw_options[:12]:
            if isinstance(option, str):
                label = option.strip()[:160]
                if label:
                    options.append({"label": label, "value": label, "answer": label})
            elif isinstance(option, dict):
                label = _bounded_text(option.get("label"), 160)
                value = _bounded_text(option.get("value") or label, 160)
                if label and value:
                    options.append({"label": label, "value": value, "answer": value})
    # Every question must target a source-backed criterion.  Unknown generic
    # criteria are permitted, but they still need a customer source quote.
    known_keys = {item.get("key") for item in criteria}
    from app.profile_registry import get_profile
    profile_fields = get_profile(domain).get("fields", {})
    is_profile_gap = key in profile_fields and key not in known_keys
    if key not in known_keys and not is_profile_gap:
        return None
    if is_profile_gap:
        # A required routing field can be missing because it was never stated;
        # the model may ask for it without fabricating customer provenance.
        # Optional fields need an observed offer/policy reason, otherwise the
        # request has silently become a fixed questionnaire again.
        if not profile_fields[key].get("required"):
            risk_words = {"offer", "policy", "term", "availability", "risk", "mismatch", "difference", "material", "affect"}
            if not any(word in why.casefold() for word in risk_words):
                return None
    question_id = _bounded_text(raw.get("id"), 80) or _stable_id(domain, key, text, kind)
    criterion_field = next(
        (item.get("field") for item in criteria if item.get("key") == key),
        None,
    )
    criterion = next((item for item in criteria if item.get("key") == key), None)
    if isinstance(criterion, dict) and criterion.get("status") == "declined":
        return None
    criterion_texts = {
        str(value).strip().casefold()
        for value in (
            criterion.get("text") if isinstance(criterion, dict) else None,
            criterion.get("source_quote") if isinstance(criterion, dict) else None,
        )
        if isinstance(value, str) and value.strip()
    }
    if text.casefold() in criterion_texts:
        # Some model responses repeat the source phrase as ``question.text``
        # while writing a real customer-facing question in the assistant
        # message. Recover only that actual model sentence; never synthesize a
        # backend question here.
        recovered = _last_question_sentence(assistant_message)
        if recovered and recovered.casefold() not in criterion_texts:
            text = recovered[:500]
        else:
            return None
    question_field = raw.get("field") if "field" in raw else (criterion_field or (key if is_profile_gap else None))
    if isinstance(question_field, str) and question_field not in profile_fields:
        return None
    if is_profile_gap and question_field != key:
        return None
    if domain == "flight" and _airport_question_scope_is_mixed(question_field, text):
        return None
    return {
        "id": question_id,
        "question_id": question_id,
        "criterion_key": key,
        "field": question_field if isinstance(question_field, str) else None,
        "question": text,
        "text": text,
        "why": why,
        "answer_kind": kind,
        "response_type": kind,
        "answer_semantics": answer_semantics,
        "options": options,
    }


def normalize_plan(raw: Any, *, domain: str, source_text: str,
                   source_messages: list[dict[str, Any]] | None = None,
                   tool_result: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate and normalize a model planner response.

    Invalid planner metadata is fail-closed into ``review_required``.  The
    legacy extraction envelope is returned separately and is still validated
    by :mod:`app.ai_grounding` in the pipeline.
    """
    draft = _draft_from_model(raw)
    if not draft:
        raise AdaptivePlanError("Adaptive response omitted the grounded draft envelope")
    raw_criteria = raw.get("criteria") if isinstance(raw, dict) else None
    criteria: list[dict[str, Any]] = []
    if isinstance(raw_criteria, list):
        from app.profile_registry import get_profile
        profile_fields = get_profile(domain).get("fields", {})
        draft_fields = draft.get("fields") if isinstance(draft.get("fields"), dict) else {}
        for item in raw_criteria[:40]:
            if not isinstance(item, dict):
                continue
            key = item.get("key") or item.get("field")
            text = _bounded_text(item.get("text") or item.get("requirement"), 500)
            quote = item.get("source_quote")
            kind = item.get("kind", "requirement")
            field = item.get("field") if isinstance(item.get("field"), str) else None
            # Never trust a model-provided verification label. A known profile
            # field remains a supported *kind* of requirement even while its
            # value is unresolved and represented as a clarification. The
            # status below carries that unresolved state; it must not be
            # downgraded into an untyped generic unsupported flag.
            verification = "supported" if field in profile_fields else "unsupported"
            if not isinstance(key, str) or not key.strip() or not text or kind not in CRITERION_KINDS:
                continue
            if not _quote_is_customer_source(quote, source_text, source_messages):
                # Merchant/tool prose is never allowed to become a customer
                # criterion.  Drop the item instead of inventing provenance.
                continue
            # ``max_total_cents`` is deliberately narrower than a generic
            # money mention: the reviewed field represents an all-in amount.
            # A model can still mention a nightly/per-person/per-room/unit
            # amount in its criteria, but that source must remain an
            # unsupported customer condition until an all-in basis is
            # confirmed.  Check every user source message because an adaptive
            # turn may keep the original request separate from the latest
            # reply.
            unit_priced = False
            if field == "max_total_cents":
                from app.ai_grounding import _price_unit_source_span
                unit_priced = any(
                    _price_unit_source_span(quote, candidate)
                    for candidate in _source_texts(source_text, source_messages)
                )
            status = item.get("status")
            if status not in {"captured", "needs_clarification", "declined", "unsupported"}:
                # Status is descriptive metadata, never an approval signal.
                # Infer a conservative value only when the model omitted it;
                # the grounded envelope remains the authority for verification.
                if field is None:
                    status = "needs_clarification" if kind == "ambiguity" else "unsupported"
                elif field in draft_fields:
                    status = "captured"
                else:
                    status = "needs_clarification"
            if unit_priced:
                # Keep the stable criterion key/source so the generated
                # question can ask for the all-in total, while making its
                # verification state explicit for the UI and evidence log.
                field = None
                verification = "unsupported"
                status = "needs_clarification"
            criteria.append({
                "key": key[:120], "field": field, "text": text,
                "source_quote": quote[:500], "kind": kind,
                "status": status,
                "verification": verification if verification in {"supported", "unsupported"} else "unsupported",
            })
    # The model may omit a field from its planner metadata while still
    # returning it in the grounded envelope.  Keep that source-backed
    # criterion visible to the UI rather than allowing planner metadata to
    # hide coverage gaps.
    grounded_criteria = _criteria_from_draft(draft, source_text, domain, source_messages)
    known_criteria = {item.get("key") for item in criteria}
    known_quotes = {item.get("source_quote") for item in criteria if item.get("source_quote")}
    for item in grounded_criteria:
        if (item.get("key") not in known_criteria
                and item.get("source_quote") not in known_quotes
                and len(criteria) < 40):
            criteria.append(item)
            known_criteria.add(item.get("key"))
            if item.get("source_quote"):
                known_quotes.add(item.get("source_quote"))
    if not criteria:
        criteria = grounded_criteria

    requested_action = raw.get("action") if isinstance(raw, dict) else None
    action = requested_action
    plan_invalid = action not in PLAN_ACTIONS
    if plan_invalid:
        action = "review_required"
    raw_question = raw.get("question") if isinstance(raw, dict) else None
    raw_question_text = (
        _bounded_text(raw_question.get("text") or raw_question.get("question"), 500)
        if isinstance(raw_question, dict) else ""
    )
    question_scope_error = (
        domain == "flight"
        and isinstance(raw_question, dict)
        and _airport_question_scope_is_mixed(
            raw_question.get("field") or raw_question.get("criterion_key"),
            raw_question_text,
        )
    )
    question = _normalize_question(
        raw_question,
        domain=domain,
        criteria=criteria,
        assistant_message=raw.get("assistant_message") if isinstance(raw, dict) else None,
    )
    if question is not None and question.get("criterion_key") not in {item.get("key") for item in criteria}:
        from app.profile_registry import get_profile
        field_name = question.get("field") or question.get("criterion_key")
        spec = get_profile(domain).get("fields", {}).get(field_name, {})
        criteria.append({
            "key": question.get("criterion_key"),
            "field": field_name if field_name in get_profile(domain).get("fields", {}) else None,
            "text": spec.get("label", field_name),
            "source_quote": None,
            "kind": "ambiguity",
            "verification": "supported" if field_name in get_profile(domain).get("fields", {}) else "unsupported",
            "status": "needs_clarification",
        })
    if action == "ask_user" and question is None:
        action = "review_required"
        plan_invalid = True
    if action != "ask_user":
        question = None
    message = _bounded_text(
        raw.get("assistant_message") if isinstance(raw, dict) else "",
        1000,
    )
    if plan_invalid:
        if question_scope_error:
            message = (
                "The generated route question combined departure and arrival airports. "
                "I kept those fields separate; review the captured route before continuing."
            )
        else:
            message = "I could not safely determine the next step from the interpreted request. Review the captured requirements before continuing."
    if not message:
        if action == "ask_user":
            message = question["question"] if question else "I need one more detail before I can review this request."
        elif action == "inspect_offers":
            message = "I checked the available merchant options against the details you gave me."
        elif action == "retrieve_policy":
            message = "I checked the merchant terms that affect this request."
        elif action == "ready_for_review":
            message = "The request is ready for your review before authorization."
        else:
            message = "I could not safely turn this into a complete next step yet."
    # Never persist arbitrary model-written offer claims.  The tool result is
    # the only allowed source for this UI context.
    observations = _trusted_observations(tool_result)
    result = {
        "action": action,
        "assistant_message": message,
        "question": question,
        "criteria": criteria,
        "offer_observations": observations,
        "draft": draft,
        "tool_result": deepcopy(tool_result) if tool_result is not None else None,
    }
    return result


def resolvable_question_feedback(
    raw_plan: Any,
    normalized_plan: Any,
    domain: str,
    source_text: str = "",
    source_messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Detect a date question whose source already contains one safe date.

    This is a bounded diagnostic for the independent review pass. It does
    not mutate the draft or answer the question. The provider may still
    reject the date for a reason outside this detector; the diagnostic only
    exists when the source-backed criterion resolves to one scalar date and
    the ordinary typed grounding validator accepts that value.
    """
    if not isinstance(normalized_plan, dict) or normalized_plan.get("action") != "ask_user":
        return None
    question = normalized_plan.get("question")
    if not isinstance(question, dict):
        return None

    from app.profile_registry import get_profile

    profile_fields = get_profile(domain).get("fields", {})
    key = question.get("criterion_key")
    if not isinstance(key, str):
        return None
    criteria = normalized_plan.get("criteria")
    if not isinstance(criteria, list):
        criteria = raw_plan.get("criteria") if isinstance(raw_plan, dict) else []
    criterion = next(
        (
            item for item in criteria
            if isinstance(item, dict)
            and (item.get("key") == key or item.get("field") == key)
        ),
        None,
    )
    if not isinstance(criterion, dict):
        return None

    field = question.get("field")
    if not isinstance(field, str) or field not in profile_fields:
        criterion_field = criterion.get("field")
        field = criterion_field if isinstance(criterion_field, str) else None
    if field not in profile_fields:
        return None
    # date_choice covers flight-style alternatives/ranges. Hotel date fields
    # are reviewed string slots whose profile role ends in ``_date``. Keeping
    # this profile-derived check avoids naming a specific commerce domain.
    spec = profile_fields[field]
    if not (
        isinstance(spec, dict)
        and (
            spec.get("type") == "date_choice"
            or (spec.get("type") == "string" and field.casefold().endswith("_date"))
        )
    ):
        return None
    if criterion.get("status") != "needs_clarification":
        return None

    draft = _draft_from_model(raw_plan)
    draft_fields = draft.get("fields") if isinstance(draft.get("fields"), dict) else {}
    if field in draft_fields and draft_fields.get(field) is not None:
        return None
    quote = criterion.get("source_quote")
    if not _quote_is_customer_source(quote, source_text, source_messages):
        return None

    from datetime import date
    from app.ai_grounding import validate_extraction
    from app.temporal import reference_for_quote, resolve_date_choice

    anchor = reference_for_quote(quote, source_messages)
    resolved = resolve_date_choice(quote, anchor)
    # Multiple dates/ranges, soft preferences, negations, and unresolved
    # yearless dates all return a non-scalar or None and therefore stay with
    # the model's question. This also avoids assigning hotel check-in/out
    # roles from one multi-date phrase.
    if not isinstance(resolved, str):
        return None
    if anchor:
        try:
            if date.fromisoformat(resolved) < date.fromisoformat(anchor):
                # A past booking date needs an upcoming-date clarification;
                # never tell the reviewer that it is already resolvable.
                return None
        except ValueError:
            return None

    probe = {
        "fields": {field: resolved},
        "sources": {field: quote},
        "unsupported": [],
        "clarifications": [],
        "explanation": "Review the captured requirement.",
    }
    try:
        grounded = validate_extraction(
            domain,
            source_text,
            probe,
            source_messages=source_messages,
        )
    except (TypeError, ValueError):
        return None
    if grounded.get("fields", {}).get(field) != resolved:
        return None
    return {
        "codes": ["question_answer_already_resolvable"],
        "field": field,
        "source_quote": quote[:500],
        "value": resolved,
    }


def _approved_context(domain: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Build a synthetic adapter request without making an authorization."""
    from app.profile_registry import digest, get_profile
    return {
        "id": "adaptive-read-only",
        "revision": 0,
        "domain": domain,
        "profile_digest": get_profile(domain)["digest"],
        "fields": deepcopy(fields),
        "unsupported": [],
        "actor": "adaptive-read-only",
        "draft_digest": digest({"domain": domain, "fields": fields}),
    }


def merchant_context(domain: str) -> dict[str, Any]:
    """Return the synthetic merchant's discovery and policy context.

    The shape intentionally resembles a merchant capability document.  It is
    informational input to the planner, not a source of customer intent.
    """
    if domain == "flight":
        capabilities = ["signed_itinerary_facts", "airport_options", "fare_terms"]
        misunderstandings = [
            "A lower fare can have more connections.",
            "A date range is different from one exact departure date.",
            "A named region can map to multiple arrival airports.",
        ]
    elif domain == "hotel":
        capabilities = ["signed_room_facts", "cancellation_terms", "amenities"]
        misunderstandings = [
            "Room price can differ from breakfast or cancellation terms.",
            "Room count and adult capacity are different constraints.",
        ]
    else:
        capabilities = ["signed_offer_facts", "return_policy", "price_terms"]
        misunderstandings = [
            "A product description does not prove every requested attribute.",
            "A price cap must be checked against the signed all-in amount.",
        ]
    return {
        "tool": "merchant_context",
        "domain": domain,
        "merchant": "Demo Travel",
        "provenance": "synthetic merchant context; informational only",
        "capabilities": capabilities,
        "common_misunderstandings": misunderstandings,
        "policies": {
            "currency": "USD",
            "price_basis": (
                "max_total_cents is an all-in total for the complete stay or purchase; "
                "per-night, per-person, per-room, and per-unit amounts require customer confirmation"
            ),
            "offers_are_synthetic": True,
            "checkout_requires_customer_approval": True,
            "merchant_facts_are_signed": True,
            "draft_comparison": (
                "Read-only advisory comparison only: statuses are UNAPPROVED, MATCH, "
                "CONFLICT, or UNKNOWN; it never authorizes or purchases an offer"
            ),
        },
    }


def retrieve_policy(domain: str) -> dict[str, Any]:
    """Execute a bounded, read-only merchant policy lookup."""
    context = merchant_context(domain)
    context["tool"] = "retrieve_policy"
    context["status"] = "ok"
    context["read_only"] = True
    context["policy_text"] = (
        "Synthetic Demo Travel offers disclose all-in price and the fields used "
        "for intent checks. A nightly, per-person, per-room, or per-unit amount "
        "is not an all-in total; customer confirmation is required before it can "
        "be converted to an all-in bound. Customer approval is required before "
        "any simulated purchase."
    )
    return context


def inspect_offers(domain: str, grounded_fields: dict[str, Any]) -> dict[str, Any]:
    """Inspect synthetic merchant offers and verify each checkout signature.

    The adapter never returns a shopping agent's prose.  It reads the signed
    checkout payload and exposes only normalized merchant facts, hashes, and
    coarse display metadata to the planner.
    """
    from demo.fixtures import offers_for
    from app.vi_adapter import normalize_offer, offer_hash, read_signed

    approved = _approved_context(domain, grounded_fields)
    rows: list[dict[str, Any]] = []
    for raw in offers_for(approved):
        token = raw.get("checkout_jwt")
        if not isinstance(token, str):
            continue
        payload = read_signed(token, "merchant", "intent-judge-checkout+jwt")
        facts = normalize_offer(payload)
        rows.append({
            "id": raw.get("id"),
            "offer_hash": offer_hash(token),
            "merchant": payload.get("merchant_id"),
            "facts": facts,
            "signed": True,
            "provenance": "merchant-signed checkout payload",
        })
    return {
        "tool": "inspect_offers",
        "domain": domain,
        "status": "ok",
        "read_only": True,
        "offers": rows,
        "count": len(rows),
    }


def _required_search_fields(domain: str) -> set[str]:
    if domain == "flight":
        return {"origin_airports", "destination_airports", "departure_date"}
    if domain == "hotel":
        return {"city", "checkin_date", "checkout_date"}
    return set()


def can_inspect_offers(domain: str, fields: dict[str, Any]) -> bool:
    """Only search when the domain has enough grounded routing facts."""
    required = _required_search_fields(domain)
    # An empty requirement set means this domain has no search adapter yet;
    # it must not silently turn a general request into synthetic offers.
    return bool(required) and required.issubset(set(fields))


def execute_tool(action: str, *, domain: str, fields: dict[str, Any],
                 tool_overrides: dict[str, Callable[..., dict[str, Any]]] | None = None) -> dict[str, Any] | None:
    """Run at most one allowlisted read-only tool selected by the model."""
    if action not in TOOL_ACTIONS:
        return None
    overrides = tool_overrides or {}
    if action == "inspect_offers":
        if not can_inspect_offers(domain, fields):
            return {
                "tool": action,
                "status": "blocked_missing_search_facts",
                "read_only": True,
                "required_fields": sorted(_required_search_fields(domain)),
            }
        fn = overrides.get(action, inspect_offers)
        result = fn(domain, deepcopy(fields))
        if not isinstance(result, dict):
            return {
                "tool": action,
                "status": "malformed_tool_result",
                "read_only": True,
            }
        offers = result.get("offers")
        if isinstance(offers, list):
            enriched = []
            for offer in offers[:8]:
                if not isinstance(offer, dict):
                    continue
                row = deepcopy(offer)
                row["draft_comparison"] = _draft_comparison(domain, fields, offer)
                enriched.append(row)
            result = deepcopy(result)
            result["offers"] = enriched
        return result
    fn = overrides.get(action, retrieve_policy)
    return fn(domain)


def prompt_context(domain: str) -> dict[str, Any]:
    """Describe available tools to the model without exposing implementation authority."""
    return {
        "domain": domain,
        "available_read_only_tools": [
            {
                "name": "inspect_offers",
                "when": "Only after grounded origin/destination/date (or hotel city/check-in/check-out) are present.",
                "returns": "merchant-signed facts, hashes, and synthetic options",
            },
            {
                "name": "retrieve_policy",
                "when": "When terms or common misunderstanding context could change the next question.",
                "returns": "merchant policy/context data",
            },
        ],
        "interpretation_rules": [
            "max_total_cents means an all-in total for the complete stay or purchase",
            "per-night, per-person, per-room, and per-unit prices are not all-in totals",
            "preserve unit-priced wording and ask the customer to confirm the all-in basis; never multiply automatically",
        ],
        "authority": "read_only_context_only; never approval, consent, payment, or purchase",
    }


def strip_plan_metadata(raw: Any) -> dict[str, Any]:
    """Return only the legacy envelope for strict grounding validation."""
    return _draft_from_model(raw)


def planner_public_view(plan: dict[str, Any]) -> dict[str, Any]:
    """Bound metadata safe to persist alongside an interpretation trace."""
    result = {
        "action": plan.get("action"),
        "assistant_message": plan.get("assistant_message"),
        "question": plan.get("question"),
        "criteria": plan.get("criteria", []),
        "offer_observations": plan.get("offer_observations", []),
    }
    return json.loads(json.dumps(result, ensure_ascii=True))

