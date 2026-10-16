"""The single strict model transport used by the intent-ledger pipeline.

This module deliberately contains no intent interpretation or repair logic.  It
turns one JSON-schema constrained Foundry request into a small, sanitized
proposal/trace pair.  Callers own reservations and outcome accounting; usage
is recorded here immediately after a successful provider response so a model
response cannot be counted as an unmetered call.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
from typing import Any, Mapping

from openai import APITimeoutError, OpenAI

from app.ai_errors import AIServiceError
from app.store import record_usage


DEFAULT_TIMEOUT_SECONDS = 35.0
PROMPT_VERSION = "intent-ledger-v5-coverage-question-contract"


def _prompt_version() -> str:
    """Use the rollout-owned version when the integration module is present."""

    try:
        from app.ai_config import prompt_version_for

        value = prompt_version_for("ledger")
        if isinstance(value, str) and value.strip():
            return value
    except Exception:
        # The transport remains importable in fixture/core-installation tests.
        pass
    return PROMPT_VERSION


def _failure(
    code: str,
    message: str,
    *,
    stage: str,
    retryable: bool = False,
    cause: Exception | None = None,
) -> AIServiceError:
    """Build a public error without copying provider details into it."""

    status = {
        "ai_timeout": 504,
        "ai_configuration": 503,
        "ai_provider": 503,
        "ai_interpretation": 502,
    }.get(code, 503)
    error = AIServiceError(
        code,
        message,
        status_code=status,
        retryable=retryable,
        stage=stage,
    )
    # Keep the exception chain useful to a local debugger while the public
    # message and traces remain free of endpoint/key/provider payloads.
    if cause is not None:
        error.__cause__ = cause
    # A stable public trace helps callers render a failure without exposing
    # provider exception text, URLs, request bodies, or credentials.
    error.trace = {
        "stage": stage,
        "provider": "foundry",
        "error_code": code,
        "tokens": {},
        "usage": {},
        "retry_count": 0,
    }
    return error


def _normalise_usage(value: Any) -> dict[str, int]:
    """Return only bounded integer token counters from SDK usage objects."""

    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        try:
            value = value.model_dump()
        except Exception:
            value = {}
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, int] = {}
    for source, target in (
        ("prompt_tokens", "prompt_tokens"),
        ("completion_tokens", "completion_tokens"),
        ("total_tokens", "total_tokens"),
    ):
        raw = value.get(source)
        if raw is None:
            continue
        try:
            parsed = int(raw)
        except (TypeError, ValueError, OverflowError):
            continue
        if parsed >= 0:
            result[target] = parsed
    if "total_tokens" not in result:
        result["total_tokens"] = result.get("prompt_tokens", 0) + result.get(
            "completion_tokens", 0
        )
    return result


def _configuration(
    *,
    endpoint: str | None,
    api_key: str | None,
    model: str | None,
) -> tuple[str, str, str]:
    """Resolve provider configuration at the transport boundary only.

    Tests and callers may pass all values directly.  Environment access stays
    in this one function so it can never leak into the prompt or trace.
    """

    resolved_endpoint = (endpoint if endpoint is not None else os.getenv("AZURE_OPENAI_ENDPOINT", "")).rstrip("/")
    resolved_key = api_key if api_key is not None else os.getenv("AZURE_OPENAI_API_KEY", "")
    resolved_model = model if model is not None else os.getenv("AZURE_OPENAI_DEPLOYMENT", "")
    if not resolved_endpoint or not resolved_key or not resolved_model:
        raise _failure(
            "ai_configuration",
            "Live AI configuration is incomplete.",
            stage="transport",
        )
    return resolved_endpoint, resolved_key, resolved_model


def _trace(
    *,
    stage: str,
    model: str,
    started: float,
    usage: Mapping[str, int],
    response_id: str | None,
    system_prompt: str,
    schema: Mapping[str, Any],
    reasoning_effort: str | None,
) -> dict[str, Any]:
    """Create a safe, attribution-friendly trace."""

    schema_bytes = json.dumps(
        schema, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        "stage": stage,
        "provider": "foundry",
        "model": model,
        "duration_ms": round((time.monotonic() - started) * 1000),
        "tokens": dict(usage),
        "usage": dict(usage),
        "response_id": response_id,
        "prompt_version": _prompt_version(),
        "prompt_sha256": hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(),
        "schema_sha256": hashlib.sha256(schema_bytes).hexdigest(),
        "output_format": "json-schema",
        "reasoning_effort": reasoning_effort,
        "retry_count": 0,
    }


def call_model(
    stage: str,
    *,
    system_prompt: str,
    payload: Mapping[str, Any],
    schema: Mapping[str, Any],
    model: str | None = None,
    endpoint: str | None = None,
    api_key: str | None = None,
    reasoning_effort: str | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Make exactly one strict JSON-schema model request.

    The function has no retry path.  A successful result is returned as
    ``{"proposal": ..., "trace": ...}``; callers can monkeypatch this one
    seam in deterministic tests without importing an SDK client.
    """

    if not isinstance(stage, str) or not stage.strip():
        raise ValueError("stage is required")
    if not isinstance(system_prompt, str) or not system_prompt.strip():
        raise ValueError("system_prompt is required")
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be a mapping")
    if not isinstance(schema, Mapping):
        raise ValueError("schema must be a mapping")
    try:
        timeout = float(timeout_seconds)
    except (TypeError, ValueError, OverflowError):
        timeout = DEFAULT_TIMEOUT_SECONDS
    if not math.isfinite(timeout) or timeout <= 0 or timeout > 120:
        raise ValueError("timeout_seconds must be between 0 and 120")

    resolved_endpoint, resolved_key, resolved_model = _configuration(
        endpoint=endpoint, api_key=api_key, model=model
    )
    started = time.monotonic()
    try:
        # max_retries=0 is intentional: reservations and the turn cap live in
        # the caller, so SDK retries would silently violate the model-call
        # budget and obscure the actual failure.
        client = OpenAI(
            base_url=resolved_endpoint + "/openai/v1/",
            api_key=resolved_key,
            max_retries=0,
            timeout=timeout,
        )
        request_kwargs: dict[str, Any] = {
            "model": resolved_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        payload, ensure_ascii=True, separators=(",", ":")
                    ),
                },
            ],
            "temperature": 0,
            "max_completion_tokens": 6000,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "intent_ledger_proposal_v1",
                    "strict": True,
                    "schema": dict(schema),
                },
            },
        }
        if reasoning_effort:
            request_kwargs["reasoning_effort"] = reasoning_effort
        response = client.chat.completions.create(**request_kwargs)
    except AIServiceError:
        raise
    except (APITimeoutError, TimeoutError) as exc:
        raise _failure(
            "ai_timeout",
            "Live AI did not finish this request. No fallback was used.",
            stage=stage,
            retryable=True,
            cause=exc,
        )
    except Exception as exc:
        raise _failure(
            "ai_provider",
            "Live AI provider is unavailable. No fallback was used.",
            stage=stage,
            retryable=True,
            cause=exc,
        )

    usage = _normalise_usage(getattr(response, "usage", None))
    if usage:
        try:
            record_usage(usage)
        except Exception:
            # Usage accounting is operational evidence; it must not turn a
            # valid, already-paid response into a fabricated interpretation.
            pass
    choices = getattr(response, "choices", None) or []
    if not choices:
        raise _failure(
            "ai_provider",
            "Live AI returned no proposal. No fallback was used.",
            stage=stage,
        )
    choice = choices[0]
    if getattr(choice, "finish_reason", None) == "length":
        raise _failure(
            "ai_interpretation",
            "Live AI returned an incomplete proposal. No fallback was used.",
            stage=stage,
            retryable=True,
        )
    message = getattr(choice, "message", None)
    content = getattr(message, "content", None)
    if not isinstance(content, str) or not content.strip():
        raise _failure(
            "ai_interpretation",
            "Live AI returned an empty proposal. No fallback was used.",
            stage=stage,
        )
    try:
        proposal = json.loads(content)
    except (TypeError, ValueError) as exc:
        raise _failure(
            "ai_interpretation",
            "Live AI returned an invalid proposal. No fallback was used.",
            stage=stage,
            cause=exc,
        )
    if not isinstance(proposal, dict):
        raise _failure(
            "ai_interpretation",
            "Live AI returned an invalid proposal. No fallback was used.",
            stage=stage,
        )
    response_id = getattr(response, "id", None)
    if response_id is not None and not isinstance(response_id, str):
        response_id = str(response_id)
    return {
        "proposal": proposal,
        "trace": _trace(
            stage=stage,
            model=resolved_model,
            started=started,
            usage=usage,
            response_id=response_id,
            system_prompt=system_prompt,
            schema=schema,
            reasoning_effort=reasoning_effort,
        ),
    }


class ModelProvider:
    """Small injectable facade useful for tests and future provider routing."""

    def __init__(self, **defaults: Any):
        self.defaults = dict(defaults)

    def call_json(self, stage: str, **kwargs: Any) -> dict[str, Any]:
        merged = dict(self.defaults)
        merged.update(kwargs)
        return call_model(stage, **merged)


# Names make the seam discoverable to fixture tests and keep the adapter easy
# to replace without introducing a second transport implementation.
request_json = call_model
strict_json_call = call_model
request_model = call_model
call_json = call_model

