"""Deterministic tests for the single B provider boundary."""

from types import SimpleNamespace

import pytest

from app import model_provider
from app.ai_errors import AIServiceError


def _response(content, *, finish_reason="stop", usage=None):
    choice = SimpleNamespace(
        finish_reason=finish_reason,
        message=SimpleNamespace(content=content),
    )
    return SimpleNamespace(
        id="resp-test",
        choices=[choice],
        usage=SimpleNamespace(
            model_dump=lambda: usage or {"prompt_tokens": 4, "completion_tokens": 3}
        ),
    )


def test_call_model_uses_one_strict_no_retry_transport(monkeypatch):
    seen = {}

    class FakeCompletions:
        def create(self, **kwargs):
            seen["request"] = kwargs
            return _response('{"ok": true}')

    class FakeClient:
        def __init__(self, **kwargs):
            seen["client"] = kwargs
            self.chat = SimpleNamespace(completions=FakeCompletions())

    usage = []
    monkeypatch.setattr(model_provider, "OpenAI", FakeClient)
    monkeypatch.setattr(model_provider, "record_usage", lambda value: usage.append(value))

    result = model_provider.call_model(
        "ledger_plan",
        endpoint="https://example.invalid",
        api_key="secret-test-key",
        model="deployment-test",
        system_prompt="Return the strict proposal.",
        payload={"customer_source_ids": ["t1p0e1habc"]},
        schema={"type": "object"},
        timeout_seconds=17,
        reasoning_effort="low",
    )

    assert result["proposal"] == {"ok": True}
    assert seen["client"] == {
        "base_url": "https://example.invalid/openai/v1/",
        "api_key": "secret-test-key",
        "max_retries": 0,
        "timeout": 17.0,
    }
    request = seen["request"]
    assert request["response_format"]["type"] == "json_schema"
    assert request["response_format"]["json_schema"]["strict"] is True
    assert request["reasoning_effort"] == "low"
    assert usage == [{"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7}]
    assert "secret-test-key" not in repr(result)
    assert result["trace"]["retry_count"] == 0
    assert result["trace"]["prompt_version"] == "intent-ledger-v6-readiness-question-contract"


def test_call_model_rejects_invalid_json_without_fallback(monkeypatch):
    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=lambda **kwargs: _response("not-json"))
            )

    monkeypatch.setattr(model_provider, "OpenAI", FakeClient)
    with pytest.raises(AIServiceError) as raised:
        model_provider.call_model(
            "ledger_plan",
            endpoint="https://example.invalid",
            api_key="key",
            model="deployment-test",
            system_prompt="Return JSON.",
            payload={},
            schema={"type": "object"},
        )
    assert raised.value.code == "ai_interpretation"
    assert "key" not in str(raised.value)

