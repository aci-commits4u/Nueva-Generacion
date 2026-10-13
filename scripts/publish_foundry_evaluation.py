#!/usr/bin/env python3
"""Publish saved reliability outcomes as one native Microsoft Foundry evaluation.

The run uses inline JSONL data and a deterministic Python grader.  It does not
declare a target, model, or sampling configuration, so the service evaluates
the stored responses without making another model call.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request


DEFAULT_ENDPOINT = (
    "https://victor-lead-foundry-20261012.services.ai.azure.com/api/projects/lead-team"
)
DEFAULT_EVALUATION_NAME = "historical reliability-development-v1"
DEFAULT_REPORT_GLOB = "evals/reports/reliability*.json"
GRADER_NAME = "canonical_intent_gold"
TERMINAL_STATUSES = {"completed", "failed", "cancelled", "canceled", "expired"}


# Microsoft Foundry's code-based evaluator contract is grade(sample, item) ->
# float in [0, 1].  The function reads only the supplied dataset item; it never
# reaches a model or a network.
GRADER_SOURCE = r'''def _same_value(a, b):
    if isinstance(a, list) and isinstance(b, list):
        if all(isinstance(x, str) for x in a + b):
            a, b = sorted(a), sorted(b)
    return a == b


def grade(sample: dict, item: dict) -> float:
    """Compare a stored response with its typed, source-aware gold labels."""
    try:
        response = item.get("response") or {}
        reference = item.get("reference") or {}
        query = item.get("query") or ""
        if not isinstance(response, dict) or not isinstance(reference, dict):
            return 0.0
        if response.get("error"):
            return 0.0

        fields = response.get("fields") or {}
        sources = response.get("sources") or {}
        unsupported = response.get("unsupported") or []
        clarifications = response.get("clarifications") or []
        expected = reference.get("expected_fields") or {}
        allowed_extra = reference.get("allowed_extra") or []
        groups = reference.get("unsupported_groups") or []
        clarification_groups = reference.get("clarification_groups") or []
        if not isinstance(fields, dict) or not isinstance(sources, dict):
            return 0.0
        if not isinstance(unsupported, list) or not isinstance(clarifications, list):
            return 0.0
        if not isinstance(expected, dict) or not isinstance(clarification_groups, list):
            return 0.0

        correct = [
            key for key, value in expected.items()
            if key in fields and _same_value(fields[key], value)
        ]
        invented = set(fields) - set(expected) - set(allowed_extra)
        ungrounded = [
            key for key in fields
            if not isinstance(sources.get(key), str)
            or not sources[key]
            or sources[key].casefold() not in query.casefold()
        ]
        invalid_clarifications = [
            clarification for clarification in clarifications
            if not isinstance(clarification, dict)
            or not all(
                isinstance(clarification.get(key), str) and clarification[key]
                for key in ("field", "source_quote", "reason")
            )
            or clarification["source_quote"].casefold() not in query.casefold()
        ]
        unsupported_text = " ".join(str(value) for value in unsupported).casefold()
        missed_groups = [
            group for group in groups
            if not any(str(token).casefold() in unsupported_text for token in group)
        ]
        clarification_text = " ".join(
            clarification["source_quote"]
            for clarification in clarifications
            if isinstance(clarification, dict)
            and isinstance(clarification.get("source_quote"), str)
        ).casefold()
        missed_clarifications = [
            group for group in clarification_groups
            if not any(str(token).casefold() in clarification_text for token in group)
        ]
        unnecessary_hold = bool(unsupported) and not groups and not reference.get(
            "allow_unsupported", False
        )
        passed = (
            len(correct) == len(expected)
            and not invented
            and not ungrounded
            and not invalid_clarifications
            and not missed_groups
            and not missed_clarifications
            and not unnecessary_hold
        )
        return 1.0 if passed else 0.0
    except Exception:
        return 0.0
'''


class PublicationError(RuntimeError):
    """A readable, secret-free publication failure."""


@dataclass(frozen=True)
class SourceRows:
    report_path: Path
    report: dict[str, Any]
    items: list[dict[str, Any]]
    stored_passed: int
    stored_failed: int


def _same_value(a: Any, b: Any) -> bool:
    if isinstance(a, list) and isinstance(b, list) and all(
        isinstance(value, str) for value in a + b
    ):
        a, b = sorted(a), sorted(b)
    return a == b


def _select_report(report_arg: str | None, pattern: str = DEFAULT_REPORT_GLOB) -> Path:
    if report_arg:
        path = Path(report_arg)
        if not path.is_file():
            raise PublicationError(f"report file does not exist: {path}")
        return path

    candidates = [path for path in Path(".").glob(pattern) if path.is_file()]
    if not candidates:
        raise PublicationError(f"no stored reports matched {pattern}")

    def sort_key(path: Path) -> tuple[datetime, float]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            created = datetime.fromisoformat(str(data.get("created_at", "")))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            created = datetime.min
        return created, path.stat().st_mtime

    return max(candidates, key=sort_key)


def _canonical_response(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {
            "fields": {},
            "sources": {},
            "unsupported": [],
            "clarifications": [],
            "error": "invalid_result",
        }
    fields = result.get("fields")
    sources = result.get("sources")
    unsupported = result.get("unsupported")
    clarifications = result.get("clarifications")
    return {
        "fields": fields if isinstance(fields, dict) else {},
        "sources": sources if isinstance(sources, dict) else {},
        "unsupported": unsupported if isinstance(unsupported, list) else [],
        "clarifications": clarifications if isinstance(clarifications, list) else [],
        "error": result.get("error"),
    }


def _rows_from_report(path: Path) -> SourceRows:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicationError(f"could not read report {path}: {exc}") from exc
    rows = report.get("rows")
    if not isinstance(rows, list) or not rows:
        raise PublicationError(f"report {path} has no rows")

    items: list[dict[str, Any]] = []
    stored_passed = 0
    stored_failed = 0
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise PublicationError(f"report row {index} is not an object")
        case = row.get("case")
        if not isinstance(case, dict):
            raise PublicationError(f"report row {index} has no case object")
        case_id = case.get("id")
        message = case.get("message")
        if not isinstance(case_id, str) or not isinstance(message, str):
            raise PublicationError(f"report row {index} is missing case.id or case.message")
        score = row.get("score")
        if isinstance(score, dict) and score.get("passed") is True:
            stored_passed += 1
        else:
            stored_failed += 1
        items.append(
            {
                "case_id": case_id,
                "query": message,
                "response": _canonical_response(row.get("result")),
                "reference": {
                    "expected_fields": case.get("expected_fields") or {},
                    "unsupported_groups": case.get("unsupported_groups") or [],
                    "clarification_groups": case.get("clarification_groups") or [],
                    "allow_unsupported": bool(case.get("allow_unsupported", False)),
                    "allowed_extra": case.get("allowed_extra") or [],
                },
            }
        )
    if not stored_passed or not stored_failed:
        raise PublicationError(
            "source report must preserve at least one stored pass and one stored failure"
        )
    return SourceRows(path, report, items, stored_passed, stored_failed)


def build_evaluation_payload(source: SourceRows, name: str) -> dict[str, Any]:
    """Build the native evaluation definition without a target or model grader."""
    label_revision = str(source.report.get("label_revision", "unspecified"))
    return {
        "name": name,
        "metadata": {
            "source_report": str(source.report_path),
            "contract": "intent-judge.gold.v1",
            "label_revision": label_revision,
            "target_inference": "none",
        },
        "data_source_config": {
            "type": "custom",
            "item_schema": {
                "type": "object",
                "properties": {
                    "case_id": {"type": "string"},
                    "query": {"type": "string"},
                    "response": {"type": "object", "additionalProperties": True},
                    "reference": {"type": "object", "additionalProperties": True},
                },
                "required": ["case_id", "query", "response", "reference"],
                "additionalProperties": False,
            },
        },
        "testing_criteria": [
            {
                "type": "python",
                "name": GRADER_NAME,
                "source": GRADER_SOURCE,
                "pass_threshold": 1.0,
            }
        ],
    }


def build_run_payload(source: SourceRows, name: str) -> dict[str, Any]:
    """Build an inline JSONL run; no target or sampling configuration is present."""
    label_revision = str(source.report.get("label_revision", "unspecified"))
    return {
        "name": name,
        "metadata": {
            "source_report": str(source.report_path),
            "stored_rows": str(len(source.items)),
            "label_revision": label_revision,
            "target_inference": "none",
        },
        "evaluation_level": "turn",
        "data_source": {
            "type": "jsonl",
            "source": {
                "type": "file_content",
                "content": [{"item": item} for item in source.items],
            },
        },
    }


def run_local_grader_self_test() -> dict[str, Any]:
    """Exercise the grader's independent source and group checks without APIs."""
    namespace: dict[str, Any] = {}
    exec(GRADER_SOURCE, namespace)
    grade = namespace["grade"]
    query = (
        "From Newark to Tampa in early November for under $300 round trip, "
        "preferably nonstop, arriving in the morning."
    )
    reference = {
        "expected_fields": {"max_total_cents": 29999},
        "unsupported_groups": [["round", "return"], ["arriv", "morning"]],
        "clarification_groups": [["preferably nonstop"], ["early November"]],
        "allow_unsupported": True,
    }
    response = {
        "fields": {"max_total_cents": 29999},
        "sources": {"max_total_cents": "under $300"},
        "unsupported": ["round trip", "arriving in the morning"],
        "clarifications": [
            {"field": "nonstop", "source_quote": "preferably nonstop", "reason": "preference"},
            {"field": "departure_date", "source_quote": "early November", "reason": "missing"},
        ],
    }
    passing_item = {"query": query, "response": response, "reference": reference}
    wrong_quote = json.loads(json.dumps(passing_item))
    wrong_quote["response"]["clarifications"][0]["source_quote"] = "not in request"
    missing_group = json.loads(json.dumps(passing_item))
    missing_group["response"]["unsupported"] = ["round trip"]
    missing_group["reference"]["unsupported_groups"] = [["round", "return"], ["wheelchair"]]
    scores = [grade({}, item) for item in (passing_item, wrong_quote, missing_group)]
    expected_scores = [1.0, 0.0, 0.0]
    if scores != expected_scores:
        raise PublicationError(
            f"local grader self-test failed: expected {expected_scores}, got {scores}"
        )
    return {"mode": "self-test", "cases": 3, "scores": scores}


def _get_token() -> str:
    for name in ("FOUNDRY_EVAL_BEARER_TOKEN", "AZURE_ACCESS_TOKEN"):
        token = os.environ.get(name)
        if token:
            return token
    try:
        result = subprocess.run(
            [
                "az",
                "account",
                "get-access-token",
                "--resource",
                "https://ai.azure.com",
                "--query",
                "accessToken",
                "-o",
                "tsv",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise PublicationError(
            "Azure CLI authentication failed; sign in with `az login` or provide an "
            "authorized bearer token through FOUNDRY_EVAL_BEARER_TOKEN"
        ) from exc
    token = result.stdout.strip()
    if not token:
        raise PublicationError("Azure CLI returned no Foundry bearer token")
    return token


class FoundryApi:
    def __init__(self, endpoint: str, token: str):
        self.base_url = endpoint.rstrip("/")
        if self.base_url.endswith("/openai/v1"):
            self.api_url = self.base_url
        else:
            self.api_url = self.base_url + "/openai/v1"
        self.token = token

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        url = self.api_url + "/" + path.lstrip("/")
        body = None
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        req = urllib_request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib_request.urlopen(req, timeout=60) as response:
                raw = response.read()
        except urllib_error.HTTPError as exc:
            raw = exc.read()
            detail = _api_error_detail(raw)
            raise PublicationError(f"Foundry API {exc.code} for {method} {path}: {detail}") from exc
        except (urllib_error.URLError, TimeoutError) as exc:
            raise PublicationError(f"Foundry API request failed for {method} {path}: {exc.reason if isinstance(exc, urllib_error.URLError) else exc}") from exc
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PublicationError(f"Foundry API returned non-JSON data for {method} {path}") from exc


def _api_error_detail(raw: bytes) -> str:
    try:
        value = json.loads(raw.decode("utf-8"))
        if isinstance(value, dict):
            error_value = value.get("error")
            if isinstance(error_value, dict):
                code = error_value.get("code")
                message = error_value.get("message")
                if code and message:
                    return f"{code}: {message}"
                if message:
                    return str(message)
            if value.get("message"):
                return str(value["message"])
    except (UnicodeDecodeError, json.JSONDecodeError):
        pass
    return "request rejected"


def _find_existing(evaluations: Any, name: str) -> dict[str, Any] | None:
    if not isinstance(evaluations, dict):
        return None
    values = evaluations.get("data")
    if not isinstance(values, list):
        return None
    for evaluation in values:
        if isinstance(evaluation, dict) and evaluation.get("name") == name:
            return evaluation
    return None


def _result_counts(run: dict[str, Any]) -> dict[str, Any]:
    counts = run.get("result_counts")
    return counts if isinstance(counts, dict) else {}


def publish(
    source: SourceRows,
    *,
    endpoint: str,
    evaluation_name: str = DEFAULT_EVALUATION_NAME,
    poll_seconds: float = 5.0,
    timeout_seconds: float = 180.0,
) -> dict[str, Any]:
    """Create/reuse one evaluation, run it once, and read both objects back."""
    client = FoundryApi(endpoint, _get_token())
    existing_response = client.request("GET", "evals?limit=100")
    evaluation = _find_existing(existing_response, evaluation_name)
    created = False
    updated = False
    effective_name = evaluation_name
    definition = build_evaluation_payload(source, evaluation_name)
    if evaluation is None:
        evaluation = client.request("POST", "evals", definition)
        created = True
    else:
        # The first publication used the original scorer.  Update its criteria
        # before the v2 run so the same evaluation retains both run records while
        # the second run uses the typed-clarification contract.
        update_payload = {
            "metadata": definition["metadata"],
            "data_source_config": definition["data_source_config"],
            "testing_criteria": definition["testing_criteria"],
        }
        try:
            evaluation = client.request("POST", f"evals/{evaluation['id']}", update_payload)
            updated = True
        except PublicationError:
            # Some project versions expose evaluation updates but reject changes
            # to existing criteria.  Keep the original evaluation/run intact and
            # create a versioned definition only in that capability case.
            effective_name = evaluation_name + "-v2"
            existing_v2 = _find_existing(existing_response, effective_name)
            if existing_v2 is not None:
                evaluation = existing_v2
            else:
                definition = build_evaluation_payload(source, effective_name)
                evaluation = client.request("POST", "evals", definition)
                created = True
    if not isinstance(evaluation, dict) or not evaluation.get("id"):
        raise PublicationError("Foundry create/list response did not contain an evaluation id")

    evaluation_id = str(evaluation["id"])
    readback_evaluation = client.request("GET", f"evals/{evaluation_id}")
    if not isinstance(readback_evaluation, dict) or readback_evaluation.get("id") != evaluation_id:
        raise PublicationError("evaluation readback did not return the created evaluation")

    run_name = f"{effective_name}-7-row-run"
    run_payload = build_run_payload(source, run_name)
    run = client.request("POST", f"evals/{evaluation_id}/runs", run_payload)
    if not isinstance(run, dict) or not run.get("id"):
        raise PublicationError("Foundry run response did not contain a run id")
    run_id = str(run["id"])
    deadline = time.monotonic() + timeout_seconds
    while str(run.get("status", "")).lower() not in TERMINAL_STATUSES:
        if time.monotonic() >= deadline:
            raise PublicationError(f"evaluation run {run_id} did not finish within {timeout_seconds:g}s")
        time.sleep(poll_seconds)
        run = client.request("GET", f"evals/{evaluation_id}/runs/{run_id}")
        if not isinstance(run, dict):
            raise PublicationError("Foundry run readback was not an object")

    return {
        "mode": "executed",
        "created": created,
        "updated": updated,
        "endpoint": client.api_url,
        "evaluation": {
            "id": evaluation_id,
            "name": readback_evaluation.get("name", effective_name),
            "object": readback_evaluation.get("object"),
            "testing_criteria": [
                criterion.get("name")
                for criterion in readback_evaluation.get("testing_criteria", [])
                if isinstance(criterion, dict)
            ],
        },
        "source": {
            "report": str(source.report_path),
            "rows": len(source.items),
            "stored_passed": source.stored_passed,
            "stored_failed": source.stored_failed,
        },
        "run": {
            "id": run_id,
            "name": run.get("name"),
            "status": run.get("status"),
            "report_url": run.get("report_url"),
            "result_counts": _result_counts(run),
            "per_testing_criteria_results": run.get("per_testing_criteria_results"),
            "model": run.get("model"),
        },
        "target_inference": False,
    }


def _dry_run_summary(source: SourceRows, name: str) -> dict[str, Any]:
    definition = build_evaluation_payload(source, name)
    run = build_run_payload(source, f"{name}-7-row-run")
    return {
        "mode": "dry-run",
        "evaluation_name": name,
        "source_report": str(source.report_path),
        "source_rows": len(source.items),
        "stored_passed": source.stored_passed,
        "stored_failed": source.stored_failed,
        "evaluation_data_source_type": definition["data_source_config"]["type"],
        "grader_type": definition["testing_criteria"][0]["type"],
        "run_data_source_type": run["data_source"]["type"],
        "target_inference": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", help="stored reliability report; defaults to newest reliability*.json")
    parser.add_argument("--name", default=DEFAULT_EVALUATION_NAME, help="native evaluation name")
    parser.add_argument("--endpoint", default=os.environ.get("FOUNDRY_PROJECT_ENDPOINT", DEFAULT_ENDPOINT))
    parser.add_argument("--execute", action="store_true", help="create/reuse the eval and run it once")
    parser.add_argument("--self-test", action="store_true", help="run the local grader checks without an API call")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.self_test:
            print(json.dumps(run_local_grader_self_test(), indent=2, sort_keys=True))
            return 0
        report_path = _select_report(args.report)
        source = _rows_from_report(report_path)
        if args.poll_seconds <= 0 or args.timeout_seconds <= 0:
            raise PublicationError("poll and timeout values must be positive")
        result = (
            publish(
                source,
                endpoint=args.endpoint,
                evaluation_name=args.name,
                poll_seconds=args.poll_seconds,
                timeout_seconds=args.timeout_seconds,
            )
            if args.execute
            else _dry_run_summary(source, args.name)
        )
    except PublicationError as exc:
        print(json.dumps({"mode": "error", "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
