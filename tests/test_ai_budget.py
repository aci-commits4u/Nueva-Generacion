"""Regression coverage for usable, money-bounded AI stage capacity."""

import pytest

from app.ai_errors import AIServiceError
from app.store import ai_capacity, get_budget_store, get_store, reserve_ai_calls


@pytest.fixture
def budget(monkeypatch, tmp_path):
    """Use a fresh local ledger while preserving the hosted-store contract."""
    monkeypatch.setenv("STORE_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "budget.sqlite3"))
    monkeypatch.delenv("AI_BUDGET_SQLITE_PATH", raising=False)
    monkeypatch.delenv("AI_BUDGET_TABLE_NAME", raising=False)
    monkeypatch.delenv("AI_BUDGET_TABLE_CONNECTION_STRING", raising=False)
    monkeypatch.setenv("AI_RESERVATION_USD", "0.02")
    monkeypatch.setenv("AI_EMERGENCY_BUDGET_CENTS", "1000")
    monkeypatch.setenv("AI_DAILY_LIMIT", "2000")
    monkeypatch.setenv("AI_EVAL_DAILY_LIMIT", "2000")
    monkeypatch.setenv("AI_MONITOR_CALL_LIMIT", "2000")
    get_store.cache_clear()
    get_budget_store.cache_clear()
    yield get_store()
    get_store.cache_clear()
    get_budget_store.cache_clear()


@pytest.mark.parametrize(
    ("calls", "reserved_cents"),
    [(472, 2432), (500, 2500)],
)
def test_configured_1500_stage_ceiling_keeps_headroom_usable(
    budget, monkeypatch, calls, reserved_cents
):
    """Past 500 stages do not stop work while the shared money ledger has room."""
    monkeypatch.setenv("AI_CALL_LIMIT", "1500")
    budget.mutate(
        "global-ai-budget",
        lambda state: state.update(
            calls=calls,
            reserved_cents=reserved_cents,
            reserved_usd=reserved_cents / 100,
        ),
    )

    reserve_ai_calls("remaining-headroom", 2)

    ledger = budget.read("global-ai-budget")
    assert ledger["calls"] == calls + 2
    assert ledger["reserved_cents"] == reserved_cents + 4


def test_environment_value_cannot_expand_beyond_the_30_dollar_cap(
    budget, monkeypatch
):
    """A typo such as a million-stage limit cannot bypass the authorized cap."""
    monkeypatch.setenv("AI_CALL_LIMIT", "1000000")
    budget.mutate(
        "global-ai-budget",
        lambda state: state.update(calls=1500, reserved_cents=2998, reserved_usd=29.98),
    )

    capacity = ai_capacity("capped-session")
    assert capacity["call_lifetime_remaining_calls"] == 0
    assert capacity["monetary_remaining_calls"] == 1

    with pytest.raises(AIServiceError) as exc:
        reserve_ai_calls("capped-session", 1)
    assert exc.value.code == "ai_budget_limit"
    assert budget.read("global-ai-budget")["reserved_cents"] == 2998


def test_smaller_explicit_lifetime_cap_remains_authoritative(budget, monkeypatch):
    monkeypatch.setenv("AI_CALL_LIMIT", "5")

    reserve_ai_calls("small-cap", 3)
    with pytest.raises(AIServiceError) as exc:
        reserve_ai_calls("small-cap", 3)

    assert exc.value.code == "ai_budget_limit"
    assert budget.read("global-ai-budget")["calls"] == 3
    assert ai_capacity("small-cap")["call_lifetime_remaining_calls"] == 2


def test_default_session_capacity_allows_eight_stages(budget, monkeypatch):
    """The session default is no longer the old eight-stage audited ceiling."""
    monkeypatch.delenv("AI_SESSION_LIMIT", raising=False)
    monkeypatch.setenv("AI_CALL_LIMIT", "1500")

    reserve_ai_calls("long-session", 3)
    reserve_ai_calls("long-session", 3)
    reserve_ai_calls("long-session", 2)

    capacity = ai_capacity("long-session")
    assert capacity["session_remaining_calls"] == 56
    assert budget.read("long-session")["ai_calls"] == 8


def test_historical_reservation_is_retained_when_call_limit_increases(
    budget, monkeypatch
):
    monkeypatch.setenv("AI_CALL_LIMIT", "1500")
    budget.mutate(
        "global-ai-budget",
        lambda state: state.update(calls=472, reserved_usd=24.32),
    )

    reserve_ai_calls("historical-ledger", 1)

    ledger = budget.read("global-ai-budget")
    assert ledger["calls"] == 473
    assert ledger["reserved_cents"] == 2434
    assert ledger["reserved_usd"] == 24.34

