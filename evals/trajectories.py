"""Executable A/B trajectory evaluation adapter.

The development trajectory file is deliberately an exposed challenge set.  It
contains frozen customer turns and state oracles, but it is not a claim about
model quality.  In live mode this module talks to two independently configured
HTTP servers.  It owns no application configuration and never changes process
environment variables while a request is in flight.

The small replay session at the bottom is for harness tests only.  It is not a
replacement for the live HTTP adapter and rows produced from it are labelled as
offline harness validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.cookiejar import CookieJar
import hashlib
import json
from pathlib import Path
import time
from typing import Any, Callable, Iterable, Mapping, MutableMapping, Protocol
from urllib.parse import urlsplit
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPCookieProcessor


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CASES = ROOT / "evals" / "ledger_trajectories.json"
SCHEMA = "intent-judge.trajectory-development.v1"
ARMS = ("A", "B")
SECRET_KEYS = {
    "authorization", "cookie", "set-cookie", "api_key", "apikey",
    "secret", "password", "token", "checkout_jwt", "signature",
}


class TrajectoryError(ValueError):
    """Raised for an invalid challenge set or an invalid adapter contract."""


class SessionLike(Protocol):
    def request(self, method: str, path: str, body: Mapping[str, Any] | None = None) -> "ApiResult":
        ...


@dataclass
class ApiResult:
    """One HTTP attempt, including failures and timing."""

    status: int | None
    payload: Any = None
    text: str = ""
    latency_ms: float = 0.0
    headers: dict[str, str] = field(default_factory=dict)
    error: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 300

    def public(self) -> dict[str, Any]:
        value = {
            "status": self.status,
            "payload": _safe_copy(self.payload),
            "text": self.text[:2000],
            "latency_ms": round(self.latency_ms, 3),
            "headers": {str(k).lower(): str(v) for k, v in self.headers.items()
                        if str(k).lower() not in SECRET_KEYS},
        }
        if self.error:
            value["error"] = _safe_copy(self.error)
        return value


def _safe_copy(value: Any, *, depth: int = 0) -> Any:
    """Bound local artifacts and remove credential-shaped response values."""
    if depth > 12:
        return "[truncated]"
    if isinstance(value, Mapping):
        result = {}
        for key, child in value.items():
            normalized = str(key).casefold().replace("-", "_")
            if normalized in SECRET_KEYS or normalized.endswith("_jwt"):
                result[str(key)] = "[redacted]"
            else:
                result[str(key)] = _safe_copy(child, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [_safe_copy(item, depth=depth + 1) for item in value[:200]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value[:10000] if isinstance(value, str) else value
    return str(value)[:1000]


class HttpApiSession:
    """Cookie-isolated, single-attempt HTTP client for one server endpoint."""

    def __init__(self, base_url: str, *, timeout: float = 30.0,
                 opener: Any | None = None):
        base_url = str(base_url or "").strip().rstrip("/")
        if not base_url.startswith(("http://", "https://")):
            raise TrajectoryError("Each arm URL must be an http(s) URL.")
        self.base_url = base_url
        self.timeout = float(timeout)
        self._opener = opener or build_opener(HTTPCookieProcessor(CookieJar()))

    def request(self, method: str, path: str,
                body: Mapping[str, Any] | None = None) -> ApiResult:
        if not path.startswith("/"):
            raise TrajectoryError(f"API path must start with '/': {path!r}")
        encoded = None
        headers = {
            "Accept": "application/json",
            "User-Agent": "intent-judge-trajectory-harness/1",
            "X-Intent-Judge-Evaluation": "trajectory-v1",
        }
        if body is not None:
            encoded = json.dumps(body, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(self.base_url + path, data=encoded,
                          headers=headers, method=method.upper())
        started = time.monotonic()
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                raw = response.read()
                text = raw.decode("utf-8", errors="replace")
                payload = _decode_payload(text)
                return ApiResult(int(response.status), payload, text,
                                 (time.monotonic() - started) * 1000,
                                 dict(response.headers.items()))
        except HTTPError as exc:
            raw = exc.read()
            text = raw.decode("utf-8", errors="replace")
            return ApiResult(int(exc.code), _decode_payload(text), text,
                             (time.monotonic() - started) * 1000,
                             dict(exc.headers.items()) if exc.headers else {},
                             {"type": "http_error", "code": int(exc.code)})
        except (URLError, TimeoutError, OSError) as exc:
            # A failed network attempt is a retained row, never a retry.
            return ApiResult(None, None, "",
                             (time.monotonic() - started) * 1000, {},
                             {"type": type(exc).__name__, "detail": str(exc)[:500]})


def _decode_payload(text: str) -> Any:
    try:
        return json.loads(text) if text else None
    except json.JSONDecodeError:
        return None


def _json_equal(left: Any, right: Any) -> bool:
    return json.dumps(left, sort_keys=True, separators=(",", ":"), ensure_ascii=True) == json.dumps(
        right, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _profile_fields(domain: str) -> list[str]:
    try:
        profile = json.loads((ROOT / "profiles" / f"{domain}.json").read_text())
    except (OSError, json.JSONDecodeError):
        return []
    fields = profile.get("fields") if isinstance(profile, Mapping) else None
    return list(fields) if isinstance(fields, Mapping) else []


def _field_view(domain: str, fields: Any) -> dict[str, Any]:
    """Canonical exact field view: absent optional fields are explicit nulls."""
    values = _as_dict(fields)
    names = _profile_fields(domain)
    if not names:
        return values
    return {name: values.get(name) for name in names}


def _profile(domain: str) -> dict[str, Any]:
    try:
        return json.loads((ROOT / "profiles" / f"{domain}.json").read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise TrajectoryError(f"Cannot load local profile for {domain}: {exc}") from exc


def _profile_digest(domain: str) -> str:
    profile = _profile(domain)
    encoded = json.dumps(profile, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _local_offer_evaluation(domain: str, fields: Mapping[str, Any], facts: Mapping[str, Any],
                            unsupported: Iterable[Any]) -> dict[str, Any]:
    """Mirror the deterministic profile operators without importing app code."""
    profile = _profile(domain)
    checks: list[dict[str, Any]] = []
    for key, required in fields.items():
        if required is None:
            continue
        spec = profile.get("fields", {}).get(key)
        value = facts.get(spec.get("fact")) if isinstance(spec, Mapping) else None
        status = "missing"
        if isinstance(spec, Mapping) and value is not None:
            op, type_name = spec.get("op"), spec.get("type")
            valid = ((type_name == "integer" and type(value) is int and type(required) is int) or
                     (type_name == "boolean" and type(value) is bool and type(required) is bool) or
                     (type_name == "string" and type(value) is str and type(required) is str) or
                     (type_name == "strings" and type(value) is str and type(required) is list) or
                     (type_name == "date_choice" and type(value) is str and
                      (isinstance(required, str) or isinstance(required, Mapping))))
            if valid:
                if op == "lte":
                    ok = value <= required
                elif op == "gte":
                    ok = value >= required
                elif op == "eq":
                    ok = value == required
                elif op == "in":
                    ok = value in required
                elif op == "date_choice":
                    if isinstance(required, str):
                        ok = value == required
                    elif "dates" in required:
                        ok = value in required["dates"]
                    else:
                        ok = required["start"] <= value <= required["end"]
                else:
                    ok = False
                status = "pass" if ok else "fail"
            else:
                status = "missing"
        if key == "max_total_cents" and facts.get("currency") != "USD":
            status = "missing" if facts.get("currency") is None else "fail"
        checks.append({"check_id": key, "status": status, "requirement": required,
                       "offer_value": value})
    for index, item in enumerate(unsupported):
        checks.append({"check_id": f"unsupported_{index}", "status": "missing",
                       "requirement": item, "offer_value": None})
    status = "PASS" if all(check["status"] == "pass" for check in checks) else "HOLD"
    return {"status": status, "checks": checks}


def _canonical_url(value: str) -> str:
    parsed = urlsplit(str(value).strip())
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path.rstrip('/')}"


def load_trajectory_set(path: str | Path = DEFAULT_CASES) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise TrajectoryError(f"Cannot read trajectory set {path}: {exc}") from exc
    validate_trajectory_set(payload)
    return payload


def validate_trajectory_set(payload: Mapping[str, Any], *, require_balance: bool = True) -> None:
    if payload.get("schema") != SCHEMA:
        raise TrajectoryError(f"Expected schema {SCHEMA!r}.")
    if payload.get("status") != "exposed_development":
        raise TrajectoryError("The executable file must be labelled exposed_development.")
    arms = payload.get("arm_expectations")
    if not isinstance(arms, Mapping) or arms.get("A", {}).get("pipeline") != "adaptive_fast" or arms.get("B", {}).get("pipeline") != "ledger":
        raise TrajectoryError("Arm expectations must pin A=adaptive_fast and B=ledger.")
    ledger_expectations = payload.get("ledger_expectations")
    if (not isinstance(ledger_expectations, Mapping) or
            ledger_expectations.get("history_required") is not True or
            ledger_expectations.get("preserve_unrelated_active_records") is not True):
        raise TrajectoryError("Ledger expectations must require history and unrelated-record preservation.")
    turn_oracles = ledger_expectations.get("turn_oracles")
    if not isinstance(turn_oracles, Mapping):
        raise TrajectoryError("Ledger expectations must include explicit per-turn turn_oracles.")
    families = payload.get("families")
    if not isinstance(families, list) or (require_balance and len(families) < 12):
        raise TrajectoryError("At least 12 exposed development families are required.")
    counts = {domain: 0 for domain in ("flight", "hotel", "general")}
    ids: set[str] = set()
    for family in families:
        if not isinstance(family, Mapping):
            raise TrajectoryError("Every family must be an object.")
        family_id = family.get("id")
        domain = family.get("domain")
        if not isinstance(family_id, str) or not family_id or family_id in ids:
            raise TrajectoryError("Family IDs must be unique non-empty strings.")
        if domain not in counts:
            raise TrajectoryError(f"Unsupported family domain: {domain!r}.")
        ids.add(family_id)
        counts[domain] += 1
        turns = family.get("turns")
        if not isinstance(turns, list) or not turns:
            raise TrajectoryError(f"{family_id}: turns are required.")
        for index, turn in enumerate(turns):
            if not isinstance(turn, Mapping) or not isinstance(turn.get("message"), str):
                raise TrajectoryError(f"{family_id}: turn {index} needs a message.")
            if not isinstance(turn.get("expected_fields"), Mapping):
                raise TrajectoryError(f"{family_id}: turn {index} needs exact expected_fields.")
            if not isinstance(turn.get("preserved_fields", {}), Mapping):
                raise TrajectoryError(f"{family_id}: turn {index} preserved_fields must be an object.")
            if not isinstance(turn.get("retracted_fields", []), list):
                raise TrajectoryError(f"{family_id}: turn {index} retracted_fields must be a list.")
            checks = turn.get("known_question_checks", {})
            if not isinstance(checks, Mapping):
                raise TrajectoryError(f"{family_id}: turn {index} known_question_checks must be an object.")
            if "required_generic_meaning" not in checks:
                raise TrajectoryError(f"{family_id}: turn {index} must declare required_generic_meaning.")
            oracle = turn.get("ledger_expectation")
            if oracle is None:
                family_oracles = turn_oracles.get(family_id)
                oracle = family_oracles[index] if isinstance(family_oracles, list) and index < len(family_oracles) else None
            if not isinstance(oracle, Mapping):
                raise TrajectoryError(f"{family_id}: turn {index} needs an explicit ledger expectation.")
            if type(oracle.get("revision_delta")) is not int or oracle.get("revision_delta") < 1:
                raise TrajectoryError(f"{family_id}: turn {index} needs a positive revision_delta.")
            if not isinstance(oracle.get("expected_record_fields"), list):
                raise TrajectoryError(f"{family_id}: turn {index} needs expected_record_fields.")
            if not isinstance(oracle.get("retracted_fields", []), list) or not isinstance(oracle.get("no_preference_fields", []), list):
                raise TrajectoryError(f"{family_id}: turn {index} ledger field expectations must be lists.")
            if oracle.get("preserve_unrelated_active_records") is not True:
                raise TrajectoryError(f"{family_id}: turn {index} must require unrelated-record preservation.")
        completion = family.get("completion")
        if not isinstance(completion, Mapping):
            raise TrajectoryError(f"{family_id}: completion oracle is required.")
        if completion.get("outcome") not in {"complete", "hold"}:
            raise TrajectoryError(f"{family_id}: completion.outcome must be complete or hold.")
        required_completion_flags = (
            ("trusted_positive_facts", "complete_user_details", "exact_approval_required")
            if completion.get("outcome") == "complete" else
            ("trusted_conflict_facts", "requires_refusal")
        )
        if any(completion.get(key) is not True for key in required_completion_flags):
            raise TrajectoryError(f"{family_id}: completion must declare deterministic eligibility flags.")
        offers = family.get("offer_paths")
        if not isinstance(offers, list) or not offers:
            raise TrajectoryError(f"{family_id}: signed offer paths are required.")
        for offer in offers:
            if not isinstance(offer, Mapping) or not isinstance(offer.get("name"), str):
                raise TrajectoryError(f"{family_id}: invalid offer path.")
            if offer.get("expected_check_status") not in {"PASS", "HOLD", "BLOCK"}:
                raise TrajectoryError(f"{family_id}: offer path needs expected_check_status.")
            if offer.get("name") == "alternative" and family.get("domain") == "general":
                if offer.get("role") != "synthetic_alternative" or not isinstance(offer.get("note"), str) or not offer.get("note"):
                    raise TrajectoryError(f"{family_id}: general alternatives need an explicit synthetic role/note.")
        source = family.get("source_expectations")
        if not isinstance(source, Mapping) or source.get("customer_turns_only") is not True:
            raise TrajectoryError(f"{family_id}: source_expectations.customer_turns_only must be true.")
        if family.get("semantic_adjudication", {}).get("status") != "pending_blinded_adjudication":
            raise TrajectoryError(f"{family_id}: semantic usefulness must require blinded adjudication.")
    if require_balance and any(counts[domain] < 4 for domain in counts):
        raise TrajectoryError(f"Need four families per domain; got {counts}.")


def _question_from_payload(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    for candidate in (
        payload.get("question"),
        _as_dict(payload.get("adaptive_plan")).get("question"),
        _as_dict(payload.get("ledger_transition")).get("question"),
    ):
        if isinstance(candidate, Mapping):
            return dict(candidate)
    questions = payload.get("questions")
    if isinstance(questions, list) and questions and isinstance(questions[0], Mapping):
        return dict(questions[0])
    return None


def _pipeline_metadata(payload: Mapping[str, Any]) -> dict[str, Any]:
    runs = payload.get("ai_runs")
    runs = runs if isinstance(runs, list) else []
    # Each response repeats the persisted run history.  A turn's metrics must
    # describe the newly appended run only; summing the complete history on
    # every turn would double-count stages and tokens.
    metric_runs = runs[-1:] if runs else []
    traces: list[Mapping[str, Any]] = []
    for run in metric_runs:
        if isinstance(run, Mapping) and isinstance(run.get("trace"), list):
            traces.extend(item for item in run["trace"] if isinstance(item, Mapping))
    # ``trace`` is retained only as a compatibility fallback for older API
    # envelopes.  ai_runs is the authoritative persisted provenance path.
    if not runs and not traces:
        direct = payload.get("trace")
        if not isinstance(direct, list):
            direct = payload.get("traces")
        traces = [item for item in (direct or []) if isinstance(item, Mapping)]
    stages: dict[str, int] = {}
    tokens: dict[str, float] = {}
    models: list[str] = []
    for trace in traces:
        if not isinstance(trace, Mapping):
            continue
        stage = trace.get("stage")
        if isinstance(stage, str):
            stages[stage] = stages.get(stage, 0) + 1
        model = trace.get("model")
        if isinstance(model, str) and model not in models:
            models.append(model)
        usage = trace.get("tokens") or trace.get("usage")
        if isinstance(usage, Mapping):
            for key, value in usage.items():
                if isinstance(value, (int, float)):
                    tokens[str(key)] = tokens.get(str(key), 0) + value
    run_models = [run.get("model") for run in metric_runs if isinstance(run, Mapping) and isinstance(run.get("model"), str)]
    run_pipelines = [run.get("pipeline") for run in metric_runs if isinstance(run, Mapping) and isinstance(run.get("pipeline"), str)]
    return {
        "pipeline": payload.get("pipeline") or (run_pipelines[-1] if run_pipelines else None),
        "model": payload.get("model") or (run_models[-1] if run_models else (models[-1] if models else None)),
        "prompt_version": payload.get("prompt_version") or next(
            (trace.get("prompt_version") for trace in reversed(traces) if trace.get("prompt_version")), None
        ),
        "trace_count": len(traces),
        "stage_counts": stages,
        "tokens": tokens,
        "trace": _safe_copy(traces),
        "source_quotes": _safe_copy(payload.get("sources", {})),
    }


def _raw_and_compiled(payload: Mapping[str, Any]) -> tuple[Any, dict[str, Any]]:
    transition = _as_dict(payload.get("ledger_transition"))
    runs = payload.get("ai_runs") if isinstance(payload.get("ai_runs"), list) else []
    traces = [trace for run in runs if isinstance(run, Mapping)
              for trace in (run.get("trace") if isinstance(run.get("trace"), list) else [])
              if isinstance(trace, Mapping)]
    latest = traces[-1] if traces else {}
    raw = (latest.get("raw_proposal") or payload.get("raw_proposal") or
           payload.get("proposal") or transition.get("raw_proposal") or transition.get("proposal"))
    compiled = {
        "fields": _safe_copy(payload.get("fields", {})),
        "sources": _safe_copy(payload.get("sources", {})),
        "unsupported": _safe_copy(payload.get("unsupported", [])),
        "clarifications": _safe_copy(payload.get("clarifications", [])),
        "criteria": _safe_copy(payload.get("criteria", [])),
        "intent_ledger": _safe_copy(payload.get("intent_ledger")),
        "revision": payload.get("revision"),
        "digest": payload.get("digest"),
        "ledger_history": _safe_copy(_as_dict(payload.get("intent_ledger")).get("history")),
    }
    return _safe_copy(raw), compiled


def _question_checks(turn: Mapping[str, Any], question: Mapping[str, Any] | None,
                    prior_questions: list[dict[str, Any]]) -> dict[str, Any]:
    checks = _as_dict(turn.get("known_question_checks"))
    forbidden_targets = set(checks.get("forbidden_targets") or [])
    forbidden_terms = [str(item).casefold() for item in (checks.get("forbidden_terms") or [])]
    key = (question or {}).get("criterion_key") or (question or {}).get("field")
    text = str((question or {}).get("question") or "")
    target_pass = not key or key not in forbidden_targets
    term_pass = not any(term and term in text.casefold() for term in forbidden_terms)
    repeated = False
    if question:
        repeated = any(
            ((question.get("question_id") and question.get("question_id") == old.get("question_id")) or
             (key and key == (old.get("criterion_key") or old.get("field"))))
            for old in prior_questions
        )
    required_meaning = checks.get("required_generic_meaning")
    generic_meaning_present = not required_meaning or bool(question)
    return {
        "target": key,
        "text": text,
        "forbidden_target_pass": target_pass,
        "forbidden_term_pass": term_pass,
        "repeated_target_observed": repeated,
        "required_generic_meaning": required_meaning,
        "generic_meaning_question_present": generic_meaning_present,
        # A field/key comparison cannot establish whether a question is useful.
        "semantic_usefulness": "pending_blinded_adjudication",
        "adjudication_required": True,
    }


def _expected_field_match(domain: str, expected: Mapping[str, Any], actual: Mapping[str, Any]) -> bool:
    expected_view = _field_view(domain, expected)
    actual_view = _field_view(domain, actual)
    return _json_equal(expected_view, actual_view)


def _turn_match(domain: str, turn: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    expected = _as_dict(turn.get("expected_fields"))
    actual = _as_dict(payload.get("fields"))
    exact = _expected_field_match(domain, expected, actual)
    preserved_results = {}
    for key, value in _as_dict(turn.get("preserved_fields")).items():
        preserved_results[key] = {"expected": value, "actual": actual.get(key),
                                 "passed": _json_equal(actual.get(key), value)}
    retracted_results = {}
    for key in turn.get("retracted_fields", []):
        retracted_results[str(key)] = {"actual": actual.get(key),
                                       "passed": actual.get(key) is None}
    unsupported_expected = turn.get("expected_unsupported")
    unsupported_actual = payload.get("unsupported", [])
    unsupported_pass = True
    if isinstance(unsupported_expected, list):
        unsupported_pass = all(item in unsupported_actual for item in unsupported_expected)
    unsupported_contains = turn.get("expected_unsupported_contains", [])
    if isinstance(unsupported_contains, list) and unsupported_contains:
        actual_text = " ".join(str(item) for item in unsupported_actual).casefold()
        unsupported_pass = unsupported_pass and all(
            str(item).casefold() in actual_text for item in unsupported_contains
        )
    return {
        "exact_fields": exact,
        "expected_fields": _safe_copy(_field_view(domain, expected)),
        "actual_fields": _safe_copy(_field_view(domain, actual)),
        "preserved": preserved_results,
        "retracted": retracted_results,
        "unsupported_expected": _safe_copy(unsupported_expected),
        "unsupported_contains": _safe_copy(unsupported_contains),
        "unsupported_actual": _safe_copy(unsupported_actual),
        "unsupported_preserved": unsupported_pass,
        "passed": exact and all(x["passed"] for x in preserved_results.values()) and
                  all(x["passed"] for x in retracted_results.values()) and unsupported_pass,
    }


def _ledger_record_key(record: Any) -> str | None:
    if not isinstance(record, Mapping):
        return None
    for key in ("field", "key", "criterion_key", "name"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _ledger_record_active(record: Any) -> bool:
    if not isinstance(record, Mapping):
        return False
    if record.get("active") is False:
        return False
    return record.get("status", "active") in {"active", "needs_clarification", "unresolved", "no_preference"}


def _ledger_state_check(payload: Mapping[str, Any], arm: str, *, family_id: str | None = None,
                        turn_index: int | None = None, previous_ledger: Mapping[str, Any] | None = None,
                        expected: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if arm != "B":
        return {"required": False, "passed": True, "oracle_checked": False}
    ledger = payload.get("intent_ledger")
    expected = expected if isinstance(expected, Mapping) else {}
    revision = ledger.get("revision") if isinstance(ledger, Mapping) else None
    history = ledger.get("history") if isinstance(ledger, Mapping) else None
    records = ledger.get("records") if isinstance(ledger, Mapping) else None
    shape_ok = (isinstance(ledger, Mapping) and type(revision) is int and revision >= 1 and
                isinstance(records, list) and isinstance(history, list) and bool(history))
    previous_revision = previous_ledger.get("revision") if isinstance(previous_ledger, Mapping) else None
    revision_delta = revision - previous_revision if isinstance(revision, int) and isinstance(previous_revision, int) else revision
    expected_delta = expected.get("revision_delta", 1)
    revision_ok = shape_ok and revision_delta == expected_delta
    expected_fields = {str(item) for item in expected.get("expected_record_fields", []) if isinstance(item, str)}
    retracted = {str(item) for item in expected.get("retracted_fields", []) if isinstance(item, str)}
    no_preference = {str(item) for item in expected.get("no_preference_fields", []) if isinstance(item, str)}
    current_by_key = {key: record for record in records or [] if (key := _ledger_record_key(record))}
    expected_records_ok = all(key in current_by_key and _ledger_record_active(current_by_key[key])
                              for key in expected_fields)
    retracted_ok = all(
        key not in current_by_key or not _ledger_record_active(current_by_key[key]) or
        current_by_key[key].get("status") in {"retracted", "superseded", "removed", "inactive"}
        for key in retracted
    )
    no_preference_ok = all(
        key in current_by_key and current_by_key[key].get("status") == "no_preference"
        for key in no_preference
    )
    preserve_ok = True
    previous_records = previous_ledger.get("records", []) if isinstance(previous_ledger, Mapping) else []
    if expected.get("preserve_unrelated_active_records") is True:
        for old in previous_records if isinstance(previous_records, list) else []:
            key = _ledger_record_key(old)
            if not key or key in retracted or key in no_preference or not _ledger_record_active(old):
                continue
            current = current_by_key.get(key)
            # Compare the semantic record while allowing revision/timestamp/status
            # bookkeeping to change.  A missing or changed unrelated value is a
            # ledger failure even if the projected fields happen to look right.
            if not current or not _ledger_record_active(current):
                preserve_ok = False
                break
            old_value = {k: v for k, v in old.items() if k not in {"id", "revision", "updated_at", "created_at", "status", "active"}}
            new_value = {k: v for k, v in current.items() if k not in {"id", "revision", "updated_at", "created_at", "status", "active"}}
            if not _json_equal(old_value, new_value):
                preserve_ok = False
                break
    passed = shape_ok and revision_ok and expected_records_ok and retracted_ok and no_preference_ok and preserve_ok
    return {
        "required": True, "passed": passed, "oracle_checked": True,
        "family_id": family_id, "turn_index": turn_index,
        "revision": revision, "previous_revision": previous_revision,
        "revision_delta": revision_delta, "expected_revision_delta": expected_delta,
        "history_count": len(history) if isinstance(history, list) else 0,
        "shape_pass": shape_ok, "expected_records_pass": expected_records_ok,
        "retracted_fields": sorted(retracted), "retracted_pass": retracted_ok,
        "no_preference_fields": sorted(no_preference), "no_preference_pass": no_preference_ok,
        "preserve_unrelated_pass": preserve_ok,
    }


def _payload_error(result: ApiResult, operation: str) -> dict[str, Any] | None:
    if result.ok:
        return None
    detail = result.payload.get("detail") if isinstance(result.payload, Mapping) else None
    error = result.payload.get("error") if isinstance(result.payload, Mapping) else None
    value = {"operation": operation, "status": result.status, "type": "api_error"}
    if isinstance(detail, str):
        value["detail"] = detail[:500]
    if isinstance(error, Mapping):
        value["error"] = _safe_copy(error)
    if result.error:
        value["transport"] = _safe_copy(result.error)
    return value


def _validate_live_provenance(payload: Mapping[str, Any], arm: str,
                              customer_messages: Iterable[str]) -> dict[str, Any] | None:
    expected_pipeline = "adaptive_fast" if arm == "A" else "ledger"
    conversation_view = _as_dict(payload.get("conversation_view"))
    actual_mode = payload.get("mode") or conversation_view.get("mode")
    actual_pipeline = payload.get("pipeline") or conversation_view.get("pipeline")
    if actual_mode != "live" or actual_pipeline != expected_pipeline:
        return {"type": "engine_mismatch", "expected_mode": "live",
                "expected_pipeline": expected_pipeline,
                "actual_mode": actual_mode, "actual_pipeline": actual_pipeline}
    runs = payload.get("ai_runs")
    if not isinstance(runs, list) or not runs:
        return {"type": "missing_ai_runs_provenance", "pipeline": expected_pipeline}
    for index, run in enumerate(runs):
        if not isinstance(run, Mapping) or run.get("mode") != "live" or run.get("pipeline") != expected_pipeline:
            return {"type": "invalid_ai_runs_provenance", "index": index,
                    "expected_mode": "live", "expected_pipeline": expected_pipeline}
        trace = run.get("trace")
        if not isinstance(trace, list) or not trace:
            return {"type": "empty_ai_trace", "index": index}
        has_stage = any(isinstance(item, Mapping) and isinstance(item.get("stage"), str) and item.get("stage")
                        for item in trace)
        has_model = isinstance(run.get("model"), str) and bool(run.get("model")) or any(
            isinstance(item, Mapping) and isinstance(item.get("model"), str) and item.get("model")
            for item in trace
        )
        if not has_stage or not has_model:
            return {"type": "missing_model_stage_metadata", "index": index,
                    "has_stage": has_stage, "has_model": has_model}
    if arm == "B":
        ledger = payload.get("intent_ledger")
        if (not isinstance(ledger, Mapping) or type(ledger.get("revision")) is not int or
                not isinstance(ledger.get("records"), list) or not isinstance(ledger.get("history"), list)):
            return {"type": "missing_ledger_history", "required": ["revision", "records", "history"]}
    customer_messages = list(customer_messages)
    source_text = " ".join(str(item) for item in customer_messages)
    fields = _as_dict(payload.get("fields"))
    sources = _as_dict(payload.get("sources"))
    for field, value in fields.items():
        if value is None:
            continue
        quote = sources.get(field)
        if not isinstance(quote, str) or not quote.strip():
            return {"type": "missing_source_quote", "field": field}
        if quote.casefold() not in source_text.casefold():
            return {"type": "source_quote_not_in_customer_turns", "field": field}
    for field, quote in sources.items():
        if isinstance(quote, str) and quote.strip() and quote.casefold() not in source_text.casefold():
            return {"type": "source_quote_not_in_customer_turns", "field": field}
    # Persisted provenance may include exact message indexes.  Validate the
    # references when present, while leaving semantic entailment to blinded
    # adjudication rather than treating an index as a quality judgment.
    for index, run in enumerate(runs):
        refs = run.get("source_message_indexes") if isinstance(run, Mapping) else None
        if not isinstance(refs, Mapping):
            continue
        run_sources = _as_dict(run.get("sources")) or sources
        for field, message_indexes in refs.items():
            if not isinstance(message_indexes, list) or any(
                type(message_index) is not int or message_index < 0 or message_index >= len(customer_messages)
                for message_index in message_indexes
            ):
                return {"type": "invalid_source_message_lineage", "index": index, "field": field}
            if field in fields and fields.get(field) is not None:
                quote = run_sources.get(field)
                if not isinstance(quote, str) or not quote.strip() or not message_indexes:
                    return {"type": "missing_source_message_lineage", "index": index, "field": field}
                if any(quote.casefold() not in str(customer_messages[message_index]).casefold()
                       for message_index in message_indexes):
                    return {"type": "source_message_lineage_mismatch", "index": index, "field": field}
    return None


def _validate_evidence(evidence: Mapping[str, Any], receipt: Mapping[str, Any],
                       approved: Mapping[str, Any]) -> tuple[bool, str | None]:
    if evidence.get("schema") != "intent-judge.evidence.v1":
        return False, "invalid_evidence_schema"
    if evidence.get("purchase") != receipt:
        return False, "evidence_purchase_mismatch"
    if evidence.get("approved_requirements") != approved:
        return False, "evidence_approved_requirements_mismatch"
    if not isinstance(evidence.get("signed_evidence"), str) or not evidence["signed_evidence"]:
        return False, "evidence_signature_missing"
    recorded_digest = evidence.get("digest")
    if not isinstance(recorded_digest, str):
        return False, "evidence_digest_missing"
    # The application computes the packet digest before appending its signed
    # evidence token; reproduce that canonical binding exactly.
    without_digest = {key: value for key, value in evidence.items()
                      if key not in {"digest", "signed_evidence"}}
    if recorded_digest != _digest(without_digest):
        return False, "evidence_digest_mismatch"
    return True, None


def _budget_calls(payload: Any) -> int | None:
    if not isinstance(payload, Mapping):
        return None
    value = payload.get("ai_calls")
    return value if isinstance(value, int) and value >= 0 else None


def _response_payload(result: ApiResult) -> dict[str, Any]:
    return result.payload if isinstance(result.payload, Mapping) else {}


class TrajectoryRunner:
    """Run exposed families through independently configured A/B HTTP servers."""

    def __init__(self, cases: Mapping[str, Any] | Iterable[Mapping[str, Any]],
                 arm_urls: Mapping[str, str] | None = None, *, live: bool = False,
                 max_conversations: int | None = None,
                 max_model_calls: int | None = None,
                 repetitions: int = 1, counterbalance: bool = False,
                 include_explanation: bool = False,
                 session_factory: Callable[[str], SessionLike] | None = None,
                 run_id: str | None = None):
        if isinstance(cases, Mapping):
            self.payload = dict(cases)
            self.families = list(cases.get("families", []))
        else:
            self.families = [dict(item) for item in cases]
            self.payload = {"schema": SCHEMA, "status": "exposed_development", "families": self.families}
        validate_trajectory_set(self.payload, require_balance=self.payload.get("selection") != "subset")
        if any(family.get("request_mode", "live") != "live" for family in self.families):
            raise TrajectoryError("Trajectory API runs must use mode=live; offline mode is fixture validation only.")
        self.arm_urls = {str(key): str(value) for key, value in (arm_urls or {}).items()}
        unknown = set(self.arm_urls) - set(ARMS)
        if unknown:
            raise TrajectoryError(f"Unknown arm(s): {', '.join(sorted(unknown))}")
        self.live = bool(live)
        self.max_conversations = max_conversations
        self.max_model_calls = max_model_calls
        self.repetitions = repetitions
        self.counterbalance = bool(counterbalance)
        self.include_explanation = bool(include_explanation)
        self.session_factory = session_factory or (lambda url: HttpApiSession(url))
        self.run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self._model_calls_reserved = 0
        self._last_server_calls: dict[str, int] = {}
        self._last_server_remaining: dict[str, int] = {}
        self._validated_arms: set[str] = set()
        self._arm_contracts: dict[str, dict[str, Any]] = {}
        if self.live:
            if set(self.arm_urls) != set(ARMS):
                raise TrajectoryError("Live A/B evaluation requires both --arm-a-url and --arm-b-url.")
            if not isinstance(max_conversations, int) or max_conversations < 2 or max_conversations % 2:
                raise TrajectoryError("Live mode requires an even --max-conversations cap for complete A/B pairs.")
            if not isinstance(max_model_calls, int) or max_model_calls < 1:
                raise TrajectoryError("Live mode requires a positive --max-model-calls.")
            if type(repetitions) is not int or repetitions < 1:
                raise TrajectoryError("--repetitions must be positive.")
        elif any(value is not None and value < 0 for value in (max_conversations, max_model_calls)):
            raise TrajectoryError("Evaluation limits cannot be negative.")

    def run(self) -> dict[str, Any]:
        started = datetime.now(timezone.utc).isoformat()
        if not self.live:
            rows = [self._dry_row(family) for family in self.families]
            return self._report(rows, started, datetime.now(timezone.utc).isoformat(), "offline_harness_validation")
        self._validate_arm_contracts()
        rows: list[dict[str, Any]] = []
        limit = self.max_conversations or 0
        for repetition in range(self.repetitions):
            for family in self.families:
                if len(rows) + 2 > limit:
                    break
                arms = ("B", "A") if self.counterbalance and repetition % 2 else ARMS
                for arm in arms:
                    rows.append(self._run_live_family(family, arm, len(rows) + 1, repetition + 1))
            if len(rows) + 2 > limit:
                break
        return self._report(rows, started, datetime.now(timezone.utc).isoformat(), "live_api_trajectory")

    def _validate_arm_contracts(self) -> None:
        canonical = [_canonical_url(self.arm_urls[arm]) for arm in ARMS]
        if canonical[0] == canonical[1]:
            raise TrajectoryError("A and B must use distinct server endpoints.")
        for arm in ARMS:
            session = self.session_factory(self.arm_urls[arm])
            health = session.request("GET", "/api/health")
            payload = _response_payload(health)
            if not health.ok or payload.get("status") != "ok" or payload.get("environment") != "development":
                raise TrajectoryError(f"Arm {arm} failed development health contract; no live requests started.")
            # The demo API creates the cookie-backed session on this GET.  The
            # status endpoint is session-scoped and can legitimately return
            # 401 until this initialization has happened.
            session_init = session.request("GET", "/api/session")
            session_payload = _response_payload(session_init)
            if (not session_init.ok or session_payload.get("environment") != "development"):
                raise TrajectoryError(
                    f"Arm {arm} failed demo-session initialization contract "
                    f"(status={session_init.status!r}); no live requests started."
                )
            status = session.request("GET", "/api/ai/status")
            status_payload = _response_payload(status)
            expected = "adaptive_fast" if arm == "A" else "ledger"
            if not status.ok or status_payload.get("pipeline") != expected:
                raise TrajectoryError(
                    f"Arm {arm} engine mismatch: expected {expected}, got {status_payload.get('pipeline')!r}."
                )
            self._arm_contracts[arm] = {
                "base_url": self.arm_urls[arm],
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "health": health.public(),
                "session_init": session_init.public(),
                "first_status": status.public(),
                "decoded_pipeline": status_payload.get("pipeline"),
                "expected_pipeline": expected,
            }
            self._validated_arms.add(arm)

    def _ledger_oracle(self, family: Mapping[str, Any], index: int) -> Mapping[str, Any]:
        turn = family.get("turns", [])[index]
        explicit = turn.get("ledger_expectation") if isinstance(turn, Mapping) else None
        if isinstance(explicit, Mapping):
            return explicit
        all_oracles = _as_dict(self.payload.get("ledger_expectations")).get("turn_oracles")
        family_oracles = all_oracles.get(family.get("id")) if isinstance(all_oracles, Mapping) else None
        if isinstance(family_oracles, list) and index < len(family_oracles) and isinstance(family_oracles[index], Mapping):
            return family_oracles[index]
        return {}

    def _dry_row(self, family: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "family_id": family["id"], "domain": family["domain"], "arm": "dry-run",
            "status": "not_run", "mode": "offline_harness_validation",
            "primary_complete_eligible": False, "primary_complete": False,
            "false_hold": False, "correct_refusal": False,
            "positive_eligible": False, "false_hold_eligible": False,
            "refusal_eligible": False, "correct_refusal_eligible": False,
            "raw_proposal_available": False, "compiled_state_available": False,
            "raw_vs_compiled_comparison": "not_exercised",
            "semantic_adjudication": family.get("semantic_adjudication"),
            "metadata": {"arm": "dry-run", "source": family.get("source", "exposed-development"),
                         "model": None, "prompt_version": None, "pipeline": None,
                         "provider_stage_counts": {}, "time_ms": 0, "errors": [],
                         "token_metrics": {}, "availability": {"model": False,
                         "prompt_version": False, "tokens": False,
                         "customer_source_quotes": False}},
            "fixture_checks": {"schema": True, "turns": len(family.get("turns", [])),
                               "signed_offer_paths_declared": bool(family.get("offer_paths")),
                               "customer_turns_only": family.get("source_expectations", {}).get("customer_turns_only") is True},
            "message": "No API calls made; this row validates harness fixtures only.",
        }

    def _budget_guard(self, session: SessionLike, arm: str, observed_calls: int,
                      budget_start: int | None, row: MutableMapping[str, Any]) -> tuple[int, dict[str, Any] | None]:
        status = session.request("GET", "/api/session")
        current = _budget_calls(status.payload)
        snapshot = {"status": status.status, "ai_calls": current,
                    "latency_ms": round(status.latency_ms, 3)}
        if status.error:
            snapshot["error"] = _safe_copy(status.error)
        if not status.ok or current is None:
            return observed_calls, {"operation": "server_budget", "type": "invalid_session_counter",
                                    "server_count_authoritative": True, "snapshot": snapshot}
        if current is not None and budget_start is not None:
            observed_calls = max(observed_calls, current - budget_start)
        previous = row.setdefault("counter_state", {}).get("ai_calls")
        if isinstance(previous, int) and current < previous:
            snapshot["previous_ai_calls"] = previous
            return observed_calls, {"operation": "server_budget", "type": "non_monotonic_session_counter",
                                    "server_count_authoritative": True, "snapshot": snapshot}
        row["counter_state"]["ai_calls"] = current
        # The application-wide allowance is authoritative.  The session count
        # above is retained for per-trajectory accounting, while this status
        # endpoint prevents the harness from treating a local counter as a
        # reservation or resetting a shared ledger.
        ledger = session.request("GET", "/api/ai/status")
        ledger_payload = _response_payload(ledger)
        snapshot["ledger_status"] = ledger.status
        snapshot["remaining_calls"] = ledger_payload.get("remaining_calls")
        snapshot["session_remaining_calls"] = ledger_payload.get("session_remaining_calls")
        snapshot["ledger_available"] = ledger_payload.get("available")
        if ledger.error:
            snapshot["ledger_error"] = _safe_copy(ledger.error)
        planned = ledger_payload.get("interpretation_calls_max")
        remaining = ledger_payload.get("remaining_calls")
        session_remaining = ledger_payload.get("session_remaining_calls")
        if (not ledger.ok or type(planned) is not int or planned < 1 or
                type(remaining) is not int or remaining < 0 or
                type(session_remaining) is not int or session_remaining < 0 or
                ledger_payload.get("available") is not True):
            return observed_calls, {"operation": "server_budget", "type": "invalid_or_unavailable_ledger_counter",
                                    "server_count_authoritative": True, "snapshot": snapshot}
        previous_remaining = row.setdefault("counter_state", {}).get("remaining_calls")
        if isinstance(previous_remaining, int) and remaining > previous_remaining:
            snapshot["previous_remaining_calls"] = previous_remaining
            return observed_calls, {"operation": "server_budget", "type": "non_monotonic_remaining_counter",
                                    "server_count_authoritative": True, "snapshot": snapshot}
        row["counter_state"]["remaining_calls"] = remaining
        row["counter_state"]["session_remaining_calls"] = session_remaining
        row.setdefault("budget_snapshots", []).append(_safe_copy(snapshot))
        if remaining < planned or session_remaining < planned:
            return observed_calls, {"operation": "server_budget", "type": "insufficient_server_budget_for_pessimistic_reservation",
                                    "server_count_authoritative": True, "planned_calls": planned,
                                    "snapshot": snapshot}
        if self._model_calls_reserved + planned > int(self.max_model_calls or 0):
            return observed_calls, {"operation": "model_call_budget", "type": "local_cap_reached",
                                    "max_model_calls": self.max_model_calls,
                                    "server_ai_calls": current,
                                    "server_remaining_calls": remaining,
                                    "pessimistic_calls_reserved": self._model_calls_reserved,
                                    "pessimistic_calls_requested": planned,
                                    "server_count_authoritative": True}
        # Reserve the server-reported worst case before POST. A provider error
        # still consumes this reservation, so failed rows cannot be retried or
        # silently excluded from the finite run cap.
        self._model_calls_reserved += planned
        row["metadata"]["reserved_model_calls"] = row["metadata"].get("reserved_model_calls", 0) + planned
        row["metadata"]["interpretation_calls_max"] = planned
        return observed_calls, None

    def _observe_server_counters(self, session: SessionLike, row: MutableMapping[str, Any]) -> dict[str, Any] | None:
        status = session.request("GET", "/api/session")
        ledger = session.request("GET", "/api/ai/status")
        session_payload = _response_payload(status)
        ledger_payload = _response_payload(ledger)
        current = _budget_calls(session_payload)
        remaining = ledger_payload.get("remaining_calls")
        session_remaining = ledger_payload.get("session_remaining_calls")
        snapshot = {"session_status": status.status, "ai_calls": current,
                    "ledger_status": ledger.status, "remaining_calls": remaining,
                    "session_remaining_calls": session_remaining}
        previous = row.setdefault("counter_state", {}).get("ai_calls")
        previous_remaining = row["counter_state"].get("remaining_calls")
        if (not status.ok or current is None or not ledger.ok or
                type(remaining) is not int or remaining < 0 or
                type(session_remaining) is not int or session_remaining < 0):
            return {"operation": "server_budget", "type": "invalid_counter_after_request",
                    "server_count_authoritative": True, "snapshot": snapshot}
        if isinstance(previous, int) and current < previous:
            return {"operation": "server_budget", "type": "non_monotonic_session_counter",
                    "server_count_authoritative": True, "snapshot": snapshot}
        if isinstance(previous, int):
            planned = row.get("metadata", {}).get("interpretation_calls_max")
            if type(planned) is int and current - previous > planned:
                return {"operation": "server_budget", "type": "server_counter_overshoot",
                        "server_count_authoritative": True, "planned_calls": planned,
                        "observed_delta": current - previous, "snapshot": snapshot}
        if isinstance(previous_remaining, int) and remaining > previous_remaining:
            return {"operation": "server_budget", "type": "non_monotonic_remaining_counter",
                    "server_count_authoritative": True, "snapshot": snapshot}
        row["counter_state"].update(ai_calls=current, remaining_calls=remaining,
                                     session_remaining_calls=session_remaining)
        row.setdefault("budget_snapshots", []).append(snapshot)
        return None

    def _run_live_family(self, family: Mapping[str, Any], arm: str, ordinal: int,
                         repetition: int) -> dict[str, Any]:
        session = self.session_factory(self.arm_urls[arm])
        started = time.monotonic()
        row: dict[str, Any] = {
            "family_id": family["id"], "domain": family["domain"], "arm": arm,
            "repetition": repetition, "run_id": f"{self.run_id}-{ordinal}", "mode": "live_api_trajectory",
            "status": "started", "turns": [], "offer_paths": [], "errors": [],
            "raw_proposals": [], "compiled_states": [], "semantic_adjudication": family.get("semantic_adjudication"),
            "metadata": {"source": family.get("source", "exposed-development"),
                         "arm": arm,
                         "prompt_version": None, "model": None, "pipeline": None,
                         "stage_counts": {}, "tokens": {}, "latency_ms": 0.0,
                         "request_count": 0, "server_counts_authoritative": True,
                         "explanation_attempted": False, "explanation_exercised": False,
                         "raw_proposal_status": "unavailable_control_trace" if arm == "A" else "pending",
                         "raw_vs_compiled_comparison": "incomplete" if arm == "A" else "pending"},
        }
        observed_calls = 0
        budget_start: int | None = None
        init = session.request("GET", "/api/session")
        row["metadata"]["request_count"] += 1
        row["metadata"]["latency_ms"] += init.latency_ms
        row["session_start"] = init.public()
        budget_start = _budget_calls(init.payload)
        ledger_start = session.request("GET", "/api/ai/status")
        row["metadata"]["server_budget_before"] = ledger_start.public()
        if not init.ok:
            row["errors"].append(_payload_error(init, "session"))
            return self._finish_row(row, family, started, "session_error")
        draft: dict[str, Any] = {}
        prior_questions: list[dict[str, Any]] = []
        for index, turn in enumerate(family["turns"]):
            previous_ledger = _as_dict(draft.get("intent_ledger")) if draft else None
            observed_calls, guard_error = self._budget_guard(session, arm, observed_calls, budget_start, row)
            if guard_error:
                row["errors"].append(guard_error)
                break
            body = {"domain": family["domain"], "mode": family.get("request_mode", "live"),
                    "message": turn["message"]} if index == 0 else {
                        "revision": draft.get("revision"), "message": turn["message"]}
            path = "/api/intents" if index == 0 else f"/api/intents/{draft.get('id')}/clarify"
            result = session.request("POST", path, body)
            row["metadata"]["request_count"] += 1
            row["metadata"]["latency_ms"] += result.latency_ms
            payload = _response_payload(result)
            provenance_error = None
            if result.ok:
                draft = payload
                provenance_error = _validate_live_provenance(
                    payload, arm, [item["message"] for item in family["turns"][:index + 1]]
                )
                if provenance_error:
                    row["errors"].append({"operation": f"turn_{index + 1}", **provenance_error})
                observed = _pipeline_metadata(payload)
                metadata = row["metadata"]
                metadata["pipeline"] = observed.get("pipeline") or metadata.get("pipeline")
                metadata["model"] = observed.get("model") or metadata.get("model")
                metadata["prompt_version"] = observed.get("prompt_version") or metadata.get("prompt_version")
                metadata["stage_counts"] = _merge_counts(metadata.get("stage_counts", {}), observed.get("stage_counts", {}))
                metadata["tokens"] = _merge_numbers(metadata.get("tokens", {}), observed.get("tokens", {}))
                metadata["customer_source_quotes"] = _safe_copy(observed.get("source_quotes", {}))
                raw, compiled = _raw_and_compiled(payload)
                if arm == "A":
                    # The control currently exposes only compiled state in its
                    # public trace.  Do not infer an unexposed model candidate.
                    raw = None
                elif raw is None:
                    row["errors"].append({"operation": f"turn_{index + 1}",
                                          "type": "missing_raw_proposal_instrumentation"})
                else:
                    row["metadata"]["raw_proposal_status"] = "observed"
                    row["metadata"]["raw_vs_compiled_comparison"] = "available"
                row["raw_proposals"].append(raw)
                row["compiled_states"].append(compiled)
            else:
                row["errors"].append(_payload_error(result, f"turn_{index + 1}"))
            counter_error = self._observe_server_counters(session, row)
            if counter_error:
                row["errors"].append(counter_error)
            question = _question_from_payload(payload)
            question_result = _question_checks(turn, question, prior_questions)
            if question:
                prior_questions.append(question)
            row["turns"].append({
                "index": index, "request": {"method": "POST", "path": path, "body": _safe_copy(body)},
                "response": result.public(), "expected": {
                    "fields": _safe_copy(turn.get("expected_fields")),
                    "preserved_fields": _safe_copy(turn.get("preserved_fields", {})),
                    "retracted_fields": _safe_copy(turn.get("retracted_fields", [])),
                    "known_question_checks": _safe_copy(turn.get("known_question_checks", {})),
                },
                "question": _safe_copy(question),
                "question_checks": question_result,
                "provenance_checks": {"passed": result.ok and provenance_error is None,
                                      "error": _safe_copy(provenance_error)},
                "ledger_checks": _ledger_state_check(
                    payload, arm, family_id=family.get("id"), turn_index=index,
                    previous_ledger=previous_ledger, expected=self._ledger_oracle(family, index),
                ),
                "field_checks": _turn_match(family["domain"], turn, payload),
                "metadata": observed if result.ok else {},
            })
            if counter_error or provenance_error or (arm == "B" and row["turns"][-1]["ledger_checks"].get("passed") is False):
                break
        row["session_after_turns"] = session.request("GET", "/api/session").public()
        row["metadata"]["request_count"] += 1
        ledger_end = session.request("GET", "/api/ai/status")
        row["metadata"]["server_budget_after"] = ledger_end.public()
        # Review is always populated from the server's current draft.  Expected
        # fields are never copied into this request, so a manual rescue cannot
        # masquerade as an AI success.
        review_base = dict(draft)
        row["review"] = self._review(session, family, review_base, row)
        reviewed = row["review"].get("response", {}) if isinstance(row.get("review"), Mapping) else {}
        review_payload = reviewed.get("payload") if isinstance(reviewed, Mapping) and isinstance(reviewed.get("payload"), Mapping) else {}
        review_binding_ok = bool(
            isinstance(reviewed, Mapping) and reviewed.get("status") and 200 <= reviewed["status"] < 300 and
            review_payload.get("id") == review_base.get("id") and
            review_payload.get("revision") == (review_base.get("revision") + 1 if type(review_base.get("revision")) is int else None)
        )
        if arm == "B" and review_binding_ok:
            review_ledger = review_payload.get("intent_ledger")
            review_binding_ok = (isinstance(review_ledger, Mapping) and
                                 review_ledger.get("revision") == review_payload.get("revision"))
        row["review_revision_binding_verified"] = review_binding_ok
        if not review_binding_ok:
            row["errors"].append({"operation": "review", "type": "review_revision_binding_mismatch"})
        if isinstance(reviewed, Mapping) and reviewed.get("status") and 200 <= reviewed["status"] < 300:
            draft = dict(review_payload)
        row["approval"] = self._approve(session, draft, row)
        approved = row["approval"].get("response", {}) if isinstance(row.get("approval"), Mapping) else {}
        approval_payload = approved.get("payload") if isinstance(approved, Mapping) else {}
        if isinstance(approval_payload, Mapping) and isinstance(approval_payload.get("offers"), list):
            row["offer_paths"] = self._offers(
                session, family, draft, approval_payload.get("approved"),
                approval_payload["offers"], row, arm=arm, budget_start=budget_start,
            )
        return self._finish_row(row, family, started, "finished")

    def _review(self, session: SessionLike, family: Mapping[str, Any], draft: Mapping[str, Any], row: MutableMapping[str, Any]) -> dict[str, Any]:
        intent_id = draft.get("id")
        if not isinstance(intent_id, str):
            return {"attempted": False, "response": {"status": None, "error": {"type": "missing_intent_id"}},
                    "manual_rescue": False}
        domain = family["domain"]
        fields = _as_dict(draft.get("fields"))
        profile_fields = _profile_fields(domain)
        review_fields = {key: fields.get(key) for key in profile_fields}
        body = {"revision": draft.get("revision"), "fields": review_fields,
                "unsupported": list(draft.get("unsupported", [])) if isinstance(draft.get("unsupported"), list) else [],
                "confirmation": True}
        result = session.request("POST", f"/api/intents/{intent_id}/answers", body)
        row["metadata"]["request_count"] += 1
        row["metadata"]["latency_ms"] += result.latency_ms
        error = _payload_error(result, "review")
        if error:
            row["errors"].append(error)
        return {"attempted": True, "manual_rescue": False,
                "source": "server_compiled_fields_only", "response": result.public(),
                "submitted_fields": _safe_copy(review_fields),
                "submitted_unsupported": _safe_copy(body["unsupported"])}

    def _approve(self, session: SessionLike, draft: Mapping[str, Any], row: MutableMapping[str, Any]) -> dict[str, Any]:
        intent_id = draft.get("id")
        if not isinstance(intent_id, str):
            return {"attempted": False, "response": {"status": None, "error": {"type": "missing_intent_id"}}}
        body = {"revision": draft.get("revision"), "digest": draft.get("digest"), "confirmation": True}
        result = session.request("POST", f"/api/intents/{intent_id}/approve", body)
        row["metadata"]["request_count"] += 1
        row["metadata"]["latency_ms"] += result.latency_ms
        error = _payload_error(result, "approve")
        if error:
            row["errors"].append(error)
        return {"attempted": True, "response": result.public()}

    def _offers(self, session: SessionLike, family: Mapping[str, Any], draft: Mapping[str, Any],
                approved: Any, offers: list[Any], row: MutableMapping[str, Any], *, arm: str,
                budget_start: int | None) -> list[dict[str, Any]]:
        paths: list[dict[str, Any]] = []
        intent_id = draft.get("id")
        if not isinstance(approved, Mapping):
            row["errors"].append({"operation": "approve", "type": "missing_approved_requirements"})
            return [{"name": path.get("name"), "error": {"type": "missing_approved_requirements"}}
                    for path in family.get("offer_paths", [])]
        reviewed_fields = draft.get("fields") if isinstance(draft.get("fields"), Mapping) else {}
        draft_ledger = draft.get("intent_ledger") if isinstance(draft.get("intent_ledger"), Mapping) else None
        approval_ledger_binding_ok = True
        if arm == "B":
            approval_ledger_binding_ok = bool(
                draft_ledger is not None and
                approved.get("intent_ledger_digest") == _digest(draft_ledger) and
                approved.get("intent_ledger_revision") == draft_ledger.get("revision") == draft.get("revision")
            )
        approved_binding_ok = bool(
            approved.get("id") == draft.get("id") and
            approved.get("revision") == draft.get("revision") and
            _json_equal(approved.get("fields"), reviewed_fields) and
            _json_equal(approved.get("unsupported", []), draft.get("unsupported", [])) and
            approved.get("draft_digest") == draft.get("digest") and
            approval_ledger_binding_ok
        )
        row["approval_binding_verified"] = approved_binding_ok
        row["approval_ledger_binding_verified"] = approval_ledger_binding_ok
        if not approved_binding_ok:
            row["errors"].append({
                "operation": "approve", "type": "approved_requirements_binding_mismatch",
                "required": ["id", "revision", "fields", "unsupported", "draft_digest"],
            })
        approved_digest = _digest(approved) if approved_binding_ok else None
        profile_digest = _profile_digest(family["domain"])
        approved_schema_ok = (approved.get("domain") == family["domain"] and
                              approved.get("profile_digest") == profile_digest and
                              isinstance(approved.get("fields"), Mapping) and approved_binding_ok)
        if not approved_schema_ok:
            row["errors"].append({"operation": "approve", "type": "approved_requirements_schema_mismatch",
                                   "expected_profile_digest": profile_digest})
        for offer_path in family.get("offer_paths", []):
            index = offer_path.get("offer_index")
            if not isinstance(index, int) or index < 0 or index >= len(offers):
                paths.append({"name": offer_path.get("name"), "expected": _safe_copy(offer_path),
                              "error": {"type": "fixture_offer_index_missing", "offer_count": len(offers)}})
                continue
            offer = offers[index]
            offer_id = offer.get("id") if isinstance(offer, Mapping) else None
            path_row: dict[str, Any] = {"name": offer_path["name"], "offer_index": index,
                                        "expected": _safe_copy(offer_path), "offer": _safe_copy(offer)}
            offer_shape_ok = (isinstance(offer, Mapping) and offer.get("signed") is True and
                              isinstance(offer.get("id"), str) and isinstance(offer.get("offer_hash"), str) and
                              isinstance(offer.get("facts"), Mapping))
            path_row["offer_shape_verified"] = offer_shape_ok
            if not offer_shape_ok:
                path_row["error"] = {"type": "unverified_signed_offer_view"}
                paths.append(path_row)
                continue
            check = session.request("POST", "/api/check", {"intent_id": intent_id, "offer_id": offer_id})
            row["metadata"]["request_count"] += 1
            row["metadata"]["latency_ms"] += check.latency_ms
            path_row["check"] = check.public()
            check_payload = _response_payload(check)
            actual_status = check_payload.get("status")
            local = _local_offer_evaluation(family["domain"], approved.get("fields", {}),
                                            _as_dict(check_payload.get("facts")), approved.get("unsupported", []))
            path_row["local_evaluation"] = local
            path_row["check_status_match"] = actual_status == offer_path.get("expected_check_status")
            path_row["verified_check"] = bool(
                check.ok and isinstance(check_payload.get("facts"), Mapping) and
                check_payload.get("offer_hash") == offer.get("offer_hash") and
                check_payload.get("approved_digest") == approved_digest and
                check_payload.get("facts") == offer.get("facts") and
                actual_status == local.get("status") and approved_schema_ok
            )
            if self.include_explanation and check.ok and isinstance(check_payload.get("id"), str):
                row["metadata"]["explanation_attempted"] = True
                _, explanation_guard = self._budget_guard(
                    session, arm, 0, budget_start, row,
                )
                if explanation_guard:
                    row["errors"].append({"operation": f"explain_{offer_path['name']}", **explanation_guard})
                else:
                    explanation = session.request("POST", f"/api/decisions/{check_payload['id']}/explain")
                    row["metadata"]["request_count"] += 1
                    row["metadata"]["latency_ms"] += explanation.latency_ms
                    path_row["explanation"] = explanation.public()
                    if explanation.ok:
                        row["metadata"]["explanation_exercised"] = True
                    else:
                        error = _payload_error(explanation, f"explain_{offer_path['name']}")
                        if error:
                            row["errors"].append(error)
                    explanation_counter_error = self._observe_server_counters(session, row)
                    if explanation_counter_error:
                        row["errors"].append(explanation_counter_error)
            if not check.ok:
                error = _payload_error(check, f"check_{offer_path['name']}")
                if error:
                    row["errors"].append(error)
                paths.append(path_row)
                continue
            decision_id = check_payload.get("id")
            purchase = session.request("POST", "/api/purchase", {
                "decision_id": decision_id,
                "idempotency_key": f"trajectory-{row['run_id']}-{offer_path['name']}",
            })
            row["metadata"]["request_count"] += 1
            row["metadata"]["latency_ms"] += purchase.latency_ms
            path_row["purchase"] = purchase.public()
            path_row["purchase_status_match"] = purchase.status == offer_path.get("expected_purchase_status")
            if purchase.ok:
                receipt = _response_payload(purchase)
                purchase_id = receipt.get("id")
                path_row["receipt_binding_verified"] = bool(
                    isinstance(receipt.get("id"), str) and
                    receipt.get("decision_id") == decision_id and
                    receipt.get("offer_id") == offer_id and
                    receipt.get("offer_hash") == offer.get("offer_hash") and
                    receipt.get("approved_digest") == approved_digest and
                    receipt.get("mode") == "simulated" and receipt.get("outcome") == "confirmed"
                )
                if isinstance(purchase_id, str):
                    evidence = session.request("GET", f"/api/purchases/{purchase_id}/evidence")
                    row["metadata"]["request_count"] += 1
                    row["metadata"]["latency_ms"] += evidence.latency_ms
                    path_row["evidence"] = evidence.public()
                    evidence_payload = _response_payload(evidence)
                    evidence_ok, evidence_error = _validate_evidence(evidence_payload, receipt, approved)
                    path_row["evidence_status_match"] = evidence.ok and evidence_ok
                    path_row["evidence_signature_presence"] = bool(
                        isinstance(evidence_payload.get("signed_evidence"), str) and
                        evidence_payload.get("signed_evidence")
                    )
                    # The harness verifies packet binding and signature-token
                    # presence only.  It does not import keys or claim crypto
                    # verification for the development fixture.
                    path_row["evidence_cryptographic_verification"] = False
                    if evidence_error:
                        path_row["evidence_error"] = evidence_error
            elif purchase.status == 409:
                path_row["receipt_binding_verified"] = False
            elif purchase.status != offer_path.get("expected_purchase_status"):
                error = _payload_error(purchase, f"purchase_{offer_path['name']}")
                if error:
                    row["errors"].append(error)
            path_row["verified_path"] = bool(
                approved_binding_ok and path_row.get("verified_check") and
                path_row.get("check_status_match") and path_row.get("purchase_status_match") and
                ((offer_path.get("expected_check_status") == "PASS" and local.get("status") == "PASS" and
                  purchase.status == offer_path.get("expected_purchase_status") == 200 and
                  path_row.get("receipt_binding_verified") and path_row.get("evidence_status_match")) or
                 (offer_path.get("expected_check_status") in {"HOLD", "BLOCK"} and
                  local.get("status") == offer_path.get("expected_check_status") and
                  purchase.status == offer_path.get("expected_purchase_status") == 409))
            )
            paths.append(path_row)
        return paths

    def _finish_row(self, row: MutableMapping[str, Any], family: Mapping[str, Any],
                    started: float, status: str) -> dict[str, Any]:
        row["status"] = status
        row["metadata"]["duration_ms"] = round((time.monotonic() - started) * 1000, 3)
        row["metadata"]["latency_ms"] = round(float(row["metadata"].get("latency_ms", 0.0)), 3)
        row["metadata"]["time_ms"] = row["metadata"]["duration_ms"]
        row["metadata"]["provider_stage_counts"] = dict(row["metadata"].get("stage_counts", {}))
        row["metadata"]["token_metrics"] = dict(row["metadata"].get("tokens", {}))
        row["metadata"]["availability"] = {
            "model": row["metadata"].get("model") is not None,
            "prompt_version": row["metadata"].get("prompt_version") is not None,
            "tokens": bool(row["metadata"].get("tokens")),
            "customer_source_quotes": bool(row["metadata"].get("customer_source_quotes")),
            "raw_proposal": row["metadata"].get("raw_proposal_status") == "observed",
            "raw_vs_compiled": row["metadata"].get("raw_vs_compiled_comparison") == "available",
        }
        start_calls = _budget_calls(_as_dict(row.get("session_start")).get("payload"))
        end_calls = row.get("counter_state", {}).get("ai_calls")
        if isinstance(start_calls, int) and isinstance(end_calls, int):
            row["metadata"]["server_ai_calls_delta"] = max(0, end_calls - start_calls)
        row["metadata"]["errors"] = _safe_copy(row.get("errors", []))
        row["raw_proposal"] = row.get("raw_proposals", [])[-1] if row.get("raw_proposals") else None
        row["compiled_state"] = row.get("compiled_states", [])[-1] if row.get("compiled_states") else None
        row["raw_proposal_available"] = row["metadata"].get("raw_proposal_status") == "observed"
        row["compiled_state_available"] = bool(row.get("compiled_states"))
        row["raw_vs_compiled_comparison"] = row["metadata"].get("raw_vs_compiled_comparison", "incomplete")
        row["final_state"] = row.get("compiled_state")
        return score_live_row(dict(row), family)

    def _report(self, rows: list[dict[str, Any]], started: str,
                finished: str, mode: str) -> dict[str, Any]:
        complete = sum(1 for row in rows if row.get("primary_complete"))
        denominator = sum(1 for row in rows if row.get("primary_complete_eligible"))
        false_holds = sum(1 for row in rows if row.get("false_hold"))
        refusals = sum(1 for row in rows if row.get("correct_refusal"))
        false_hold_denominator = sum(1 for row in rows if row.get("false_hold_eligible"))
        correct_refusal_denominator = sum(1 for row in rows if row.get("correct_refusal_eligible"))
        provider_stage_counts: dict[str, int] = {}
        for row in rows:
            provider_stage_counts = _merge_counts(
                provider_stage_counts,
                row.get("metadata", {}).get("provider_stage_counts", {}) or {},
            )
        paired: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = f"{row.get('family_id')}#r{row.get('repetition', 1)}"
            paired.setdefault(key, {})[str(row.get("arm"))] = {
                "primary_complete": bool(row.get("primary_complete")),
                "status": row.get("status"),
            }
        by_arm_domain: dict[str, dict[str, int]] = {}
        for row in rows:
            key = f"{row.get('arm')}:{row.get('domain')}"
            bucket = by_arm_domain.setdefault(key, {
                "attempted": 0, "primary_complete_numerator": 0,
                "primary_complete_denominator": 0, "positive_eligible": 0,
                "positive_completed": 0, "false_hold": 0,
                "false_hold_denominator": 0, "refusal_eligible": 0,
                "correct_refusal_denominator": 0, "correct_refusal": 0,
                "provider_failures": 0, "model_failures": 0, "budget_failures": 0,
                "harness_failures": 0,
            })
            bucket["attempted"] += 1
            bucket["primary_complete_denominator"] += int(bool(row.get("primary_complete_eligible")))
            bucket["primary_complete_numerator"] += int(bool(row.get("primary_complete")))
            bucket["positive_eligible"] += int(bool(row.get("positive_eligible")))
            bucket["positive_completed"] += int(bool(row.get("positive_completion")))
            bucket["false_hold"] += int(bool(row.get("false_hold")))
            bucket["false_hold_denominator"] += int(bool(row.get("false_hold_eligible")))
            bucket["refusal_eligible"] += int(bool(row.get("refusal_eligible")))
            bucket["correct_refusal_denominator"] += int(bool(row.get("correct_refusal_eligible")))
            bucket["correct_refusal"] += int(bool(row.get("correct_refusal")))
            bucket["provider_failures"] += int(bool(row.get("provider_failure")))
            bucket["model_failures"] += int(bool(row.get("model_failure")))
            bucket["budget_failures"] += int(bool(row.get("budget_failure")))
            bucket["harness_failures"] += int(bool(row.get("harness_failure")))
        return {
            "schema": "intent-judge.trajectory-report.v1",
            "mode": mode, "created_at": started, "completed_at": finished,
            "case_set_schema": self.payload.get("schema"),
            "case_set_status": self.payload.get("status"),
            "case_set_label_audit": _safe_copy(self.payload.get("label_audit")),
            "arms": list(ARMS), "base_urls_configured": sorted(self.arm_urls),
            "arm_contracts": _safe_copy(self._arm_contracts),
            "live": self.live, "run_id": self.run_id,
            "limits": {"max_conversations": self.max_conversations,
                       "max_model_calls": self.max_model_calls,
                       "repetitions": self.repetitions,
                       "counterbalance": self.counterbalance},
            "no_retries": True, "server_ledger_counts_authoritative": True,
            "semantic_usefulness": "pending_blinded_adjudication",
            "explanation_calls": {
                "requested": self.include_explanation,
                "attempted": sum(1 for row in rows if row.get("metadata", {}).get("explanation_attempted")),
                "exercised": any(row.get("metadata", {}).get("explanation_exercised") for row in rows),
                "non_2xx_failures": sum(
                    1 for row in rows for error in row.get("errors", [])
                    if isinstance(error, Mapping) and str(error.get("operation", "")).startswith("explain_")
                ),
                "coverage_claim": "explicitly exercised" if self.include_explanation else "not exercised; no whole-conversation explanation coverage claim",
            },
            "primary_complete_numerator": complete,
            "primary_complete_denominator": denominator,
            "fixture_rows": len(rows),
            "false_hold_numerator": false_holds,
            "false_hold_denominator": false_hold_denominator,
            "correct_refusal_numerator": refusals,
            "correct_refusal_denominator": correct_refusal_denominator,
            "eligibility_reasons": {
                "false_hold": ["expected_outcome_complete", "trusted_positive_facts",
                                "complete_user_details", "exact_approval_required"],
                "correct_refusal": ["expected_outcome_hold", "trusted_conflict_facts",
                                    "requires_refusal"],
                "provider_failures_remain_in_primary_denominator": True,
            },
            "errors_retained": sum(len(row.get("errors", [])) for row in rows),
            "model_failure_rows": sum(1 for row in rows if row.get("model_failure")),
            "provider_stage_counts": provider_stage_counts,
            "pessimistic_model_calls_reserved": self._model_calls_reserved,
            "arm_domain_metrics": by_arm_domain,
            "paired_family_outcomes": paired,
            "paired_family_count": sum(1 for value in paired.values() if set(value) >= set(ARMS)),
            "rows": rows,
            "evidence_cryptographic_verification": False,
            "evidence_claim": "harness validation only" if not self.live else "live API transitions; no quality claim without adjudication",
        }


def _merge_counts(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, int]:
    result = {str(key): int(value) for key, value in left.items() if isinstance(value, (int, float))}
    for key, value in right.items():
        if isinstance(value, (int, float)):
            result[str(key)] = result.get(str(key), 0) + int(value)
    return result


def _merge_numbers(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, float]:
    result = {str(key): float(value) for key, value in left.items() if isinstance(value, (int, float))}
    for key, value in right.items():
        if isinstance(value, (int, float)):
            result[str(key)] = result.get(str(key), 0) + float(value)
    return result


def score_live_row(row: MutableMapping[str, Any], family: Mapping[str, Any]) -> dict[str, Any]:
    """Apply deterministic state/authority checks to one retained trajectory."""
    completion = _as_dict(family.get("completion"))
    outcome = completion.get("outcome")
    turn_checks = [turn.get("field_checks", {}) for turn in row.get("turns", [])]
    turns_pass = bool(turn_checks) and all(check.get("passed") for check in turn_checks)
    provenance_pass = bool(row.get("turns")) and all(
        turn.get("provenance_checks", {}).get("passed") is True
        for turn in row.get("turns", [])
    )
    ledger_pass = all(turn.get("ledger_checks", {}).get("passed", True)
                      for turn in row.get("turns", []))
    question_checks = [turn.get("question_checks", {}) for turn in row.get("turns", [])]
    known_questions_pass = all(
        check.get("forbidden_target_pass", True) and check.get("forbidden_term_pass", True)
        and not check.get("repeated_target_observed", False)
        for check in question_checks
    )
    generic_meaning_checks = [
        check for check in question_checks if check.get("required_generic_meaning")
    ]
    review = row.get("review") or {}
    review_response = _as_dict(review.get("response"))
    approval_response = _as_dict(_as_dict(row.get("approval")).get("response"))
    approval_payload = _as_dict(approval_response.get("payload"))
    review_ok = review_response.get("status", 0) in range(200, 300)
    approval_ok = approval_response.get("status", 0) in range(200, 300)
    review_binding_ok = row.get("review_revision_binding_verified") is True
    approval_binding_ok = row.get("approval_binding_verified") is True
    offer_paths = row.get("offer_paths") or []
    expected_positive = next((path for path in offer_paths if path.get("name") == "positive"), None)
    expected_conflict = next((path for path in offer_paths if path.get("name") == "conflicting"), None)
    declared_paths_ok = bool(offer_paths) and all(path.get("verified_path") is True for path in offer_paths)
    positive_ok = bool(expected_positive and expected_positive.get("verified_path") and
                       expected_positive.get("check_status_match") is True and
                       _as_dict(expected_positive.get("check", {}).get("payload")).get("status") == "PASS" and
                       expected_positive.get("purchase_status_match") and
                       _as_dict(expected_positive.get("purchase", {})).get("status") == 200 and
                       expected_positive.get("evidence_status_match"))
    conflict_ok = bool(expected_conflict and expected_conflict.get("verified_path") and
                       expected_conflict.get("check_status_match") is True and
                       _as_dict(expected_conflict.get("check", {}).get("payload")).get("status") in {"HOLD", "BLOCK"} and
                       expected_conflict.get("purchase_status_match") and
                       _as_dict(expected_conflict.get("purchase", {})).get("status") == 409)
    authority_ok = not any(
        isinstance(path.get("purchase", {}).get("payload"), Mapping) and
        path.get("purchase", {}).get("payload", {}).get("approved")
        for path in offer_paths
    )
    errors = [error for error in row.get("errors", []) if isinstance(error, Mapping)]
    budget_codes = {"ai_budget_limit", "ai_session_limit", "ai_daily_limit"}
    budget_failure = any(
        str(error.get("type", "")).startswith(("server_budget", "model_call_budget")) or
        isinstance(error.get("error"), Mapping) and error.get("error", {}).get("code") in budget_codes
        for error in errors
    )
    model_failure = any(
        error.get("type") == "api_error" and isinstance(error.get("error"), Mapping) and
        error.get("error", {}).get("code") == "ai_interpretation"
        for error in errors
    )
    provider_failure = any(
        error.get("type") == "api_error" and
        (error.get("status") is None or isinstance(error.get("status"), int) and error.get("status", 0) >= 500) and
        not (isinstance(error.get("error"), Mapping) and error.get("error", {}).get("code") == "ai_interpretation")
        for error in errors
    )
    harness_failure = any(error.get("type") in {
        "engine_mismatch", "missing_ai_runs_provenance", "invalid_ai_runs_provenance",
        "empty_ai_trace", "missing_model_stage_metadata", "missing_source_quote",
        "source_quote_not_in_customer_turns", "invalid_source_message_lineage",
        "missing_source_message_lineage", "source_message_lineage_mismatch",
        "review_revision_binding_mismatch", "approved_requirements_binding_mismatch",
        "missing_ledger_history", "invalid_counter_after_request", "non_monotonic_session_counter",
        "non_monotonic_remaining_counter", "invalid_or_unavailable_ledger_counter",
        "server_counter_overshoot",
    } for error in errors)
    positive_eligible = bool(
        outcome == "complete" and completion.get("trusted_positive_facts") is True and
        completion.get("complete_user_details") is True and completion.get("exact_approval_required") is True
    )
    refusal_eligible = bool(
        outcome == "hold" and completion.get("trusted_conflict_facts") is True and
        completion.get("requires_refusal") is True
    )
    positive_eligibility_reasons = [
        "expected_outcome_complete" if outcome == "complete" else "expected_outcome_not_complete",
        "trusted_positive_facts" if completion.get("trusted_positive_facts") is True else "untrusted_or_unsatisfiable_positive_facts",
        "complete_user_details" if completion.get("complete_user_details") is True else "incomplete_user_details",
        "exact_approval_required" if completion.get("exact_approval_required") is True else "exact_approval_not_declared",
    ]
    refusal_eligibility_reasons = [
        "expected_outcome_hold" if outcome == "hold" else "expected_outcome_not_hold",
        "trusted_conflict_facts" if completion.get("trusted_conflict_facts") is True else "untrusted_conflict_facts",
        "requires_refusal" if completion.get("requires_refusal") is True else "refusal_not_declared",
    ]
    if outcome == "complete":
        primary = turns_pass and provenance_pass and ledger_pass and known_questions_pass and review_ok and review_binding_ok and approval_ok and approval_binding_ok and positive_ok and declared_paths_ok and authority_ok and not review.get("manual_rescue")
        false_hold = bool(
            not primary and not provider_failure and not budget_failure and not harness_failure and
            positive_eligible and
            expected_positive and
            _as_dict(expected_positive.get("check", {}).get("payload")).get("status") in {"HOLD", "BLOCK"} and
            _as_dict(expected_positive.get("purchase", {})).get("status") == 409 and
            expected_positive.get("local_evaluation", {}).get("status") == "PASS"
        )
        correct_refusal = False
    else:
        primary = turns_pass and provenance_pass and ledger_pass and known_questions_pass and review_ok and review_binding_ok and approval_ok and approval_binding_ok and conflict_ok and declared_paths_ok and authority_ok and not review.get("manual_rescue")
        false_hold = False
        correct_refusal = primary and not provider_failure and not budget_failure and not harness_failure
    row.update({
        "primary_complete_eligible": True,
        "primary_complete": bool(primary),
        "false_hold": bool(false_hold),
        "false_refusal": bool(false_hold),
        "correct_refusal": bool(correct_refusal),
        "provider_failure": provider_failure,
        "model_failure": model_failure,
        "budget_failure": budget_failure,
        "harness_failure": harness_failure,
        "positive_eligible": positive_eligible,
        "refusal_eligible": refusal_eligible,
        "false_hold_eligible": positive_eligible,
        "correct_refusal_eligible": refusal_eligible,
        "false_hold_eligibility_reasons": positive_eligibility_reasons,
        "correct_refusal_eligibility_reasons": refusal_eligibility_reasons,
        "turns_pass": turns_pass,
        "known_question_checks_pass": known_questions_pass,
        "generic_meaning_checks_pending": bool(generic_meaning_checks),
        "provenance_checks_pass": provenance_pass,
        "ledger_checks_pass": ledger_pass,
        "authority_checks_pass": authority_ok,
        "review_revision_binding_verified": review_binding_ok,
        "approval_binding_verified": approval_binding_ok,
        "manual_rescue": bool(review.get("manual_rescue")),
        "expected_outcome": outcome,
        "positive_completion": positive_ok,
        "conflicting_offer_refusal": conflict_ok,
        "declared_offer_paths_verified": declared_paths_ok,
        "raw_proposal_vs_compiled_state": {
            "raw_proposals": row.get("raw_proposals", []),
            "compiled_states": row.get("compiled_states", []),
            "raw_available": row.get("raw_proposal_available", False),
            "compiled_available": row.get("compiled_state_available", bool(row.get("compiled_states"))),
            "comparison": row.get("raw_vs_compiled_comparison", "incomplete"),
            "claim": ("A raw candidate unavailable; comparison incomplete" if row.get("arm") == "A" else
                      ("B raw candidate observed" if row.get("raw_proposal_available") else
                       ("B raw instrumentation missing" if row.get("arm") == "B" else "not exercised offline"))),
        },
    })
    return dict(row)


class ReplayApiSession:
    """Deterministic HTTP-like test double; rows are labelled offline only."""

    def __init__(self, responses: Mapping[tuple[str, str], Any] | None = None):
        self.responses = dict(responses or {})
        self.requests: list[dict[str, Any]] = []

    def request(self, method: str, path: str, body: Mapping[str, Any] | None = None) -> ApiResult:
        self.requests.append({"method": method.upper(), "path": path, "body": _safe_copy(body)})
        value = self.responses.get((method.upper(), path), self.responses.get(("*", path)))
        if callable(value):
            value = value(method.upper(), path, body)
        if isinstance(value, ApiResult):
            return value
        if isinstance(value, tuple):
            status, payload = value
            return ApiResult(int(status), payload, json.dumps(payload, ensure_ascii=True))
        if value is None:
            return ApiResult(404, {"detail": "Replay response not configured"}, "", error={"type": "replay_missing"})
        return ApiResult(200, value, json.dumps(value, ensure_ascii=True))


def run_offline_fixture_validation(path: str | Path = DEFAULT_CASES) -> dict[str, Any]:
    """Validate exposed fixtures without making application or provider calls."""
    payload = load_trajectory_set(path)
    runner = TrajectoryRunner(payload, live=False)
    return runner.run()


__all__ = [
    "ApiResult", "DEFAULT_CASES", "HttpApiSession", "ReplayApiSession",
    "SCHEMA", "TrajectoryError", "TrajectoryRunner", "load_trajectory_set",
    "run_offline_fixture_validation", "score_live_row", "validate_trajectory_set",
]
