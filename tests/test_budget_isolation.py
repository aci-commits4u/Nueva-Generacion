"""Regression coverage for preview session isolation and shared AI spend."""

import os

import pytest

from app.ai_errors import AIServiceError
import app.store as store_module
from app.store import (
    get_budget_store,
    get_store,
    record_ai_outcome,
    reserve_ai_call,
)


def _configure_environment(monkeypatch, session_path, budget_path):
    """Point one simulated deployment at its own sessions and shared ledger."""
    monkeypatch.setenv('STORE_BACKEND', 'sqlite')
    monkeypatch.setenv('SQLITE_PATH', str(session_path))
    monkeypatch.setenv('AI_BUDGET_SQLITE_PATH', str(budget_path))
    monkeypatch.setenv('AI_CALL_LIMIT', '500')
    monkeypatch.setenv('AI_DAILY_LIMIT', '200')
    monkeypatch.setenv('AI_SESSION_LIMIT', '8')
    monkeypatch.setenv('AI_EVAL_DAILY_LIMIT', '100')
    monkeypatch.setenv('AI_MONITOR_CALL_LIMIT', '40')
    monkeypatch.setenv('AI_RESERVATION_USD', '0.02')
    monkeypatch.setenv('AI_EMERGENCY_BUDGET_CENTS', '1000')
    get_store.cache_clear()
    get_budget_store.cache_clear()


def test_without_budget_override_legacy_store_remains_authoritative(monkeypatch, tmp_path):
    monkeypatch.setenv('STORE_BACKEND', 'sqlite')
    monkeypatch.setenv('SQLITE_PATH', str(tmp_path / 'state.sqlite3'))
    monkeypatch.delenv('AI_BUDGET_TABLE_NAME', raising=False)
    monkeypatch.delenv('AI_BUDGET_TABLE_CONNECTION_STRING', raising=False)
    monkeypatch.delenv('AI_BUDGET_SQLITE_PATH', raising=False)
    get_store.cache_clear()
    get_budget_store.cache_clear()

    assert get_budget_store() is get_store()


@pytest.mark.parametrize(
    ('session_table', 'budget_table', 'message'),
    [
        ('', 'IntentJudge', 'AZURE_TABLE_NAME'),
        ('IntentJudgeDev', '', 'AI_BUDGET_TABLE_NAME'),
        ('IntentJudgeDev', 'IntentJudgeDev', 'distinct'),
    ],
)
def test_hosted_development_fails_closed_before_store_creation(
    monkeypatch, tmp_path, session_table, budget_table, message
):
    monkeypatch.setenv('VERCEL', '1')
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.setenv('STORE_BACKEND', 'azure')
    monkeypatch.setenv('AZURE_TABLE_NAME', session_table)
    monkeypatch.setenv('AI_BUDGET_TABLE_NAME', budget_table)
    monkeypatch.setenv('AZURE_TABLE_CONNECTION_STRING', 'synthetic-only')
    get_store.cache_clear()
    get_budget_store.cache_clear()

    with pytest.raises(RuntimeError, match=message):
        get_store()
    with pytest.raises(RuntimeError, match=message):
        get_budget_store()


def test_hosted_development_uses_distinct_configured_tables(monkeypatch):
    class FakeAzureTableStore:
        def __init__(self, *, table_name=None, connection_string=None):
            self.table_name = table_name or os.getenv('AZURE_TABLE_NAME')
            self.connection_string = connection_string or os.getenv('AZURE_TABLE_CONNECTION_STRING')

    monkeypatch.setenv('VERCEL', '1')
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.setenv('STORE_BACKEND', 'azure')
    monkeypatch.setenv('AZURE_TABLE_NAME', 'IntentJudgeDev')
    monkeypatch.setenv('AI_BUDGET_TABLE_NAME', 'IntentJudge')
    monkeypatch.setenv('AZURE_TABLE_CONNECTION_STRING', 'synthetic-only')
    monkeypatch.setattr(store_module, 'AzureTableStore', FakeAzureTableStore)
    get_store.cache_clear()
    get_budget_store.cache_clear()

    session_store = get_store()
    budget_store = get_budget_store()

    assert session_store.table_name == 'IntentJudgeDev'
    assert budget_store.table_name == 'IntentJudge'
    assert session_store is not budget_store


def test_local_development_can_still_use_sqlite(monkeypatch, tmp_path):
    monkeypatch.delenv('VERCEL', raising=False)
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.setenv('STORE_BACKEND', 'sqlite')
    monkeypatch.setenv('SQLITE_PATH', str(tmp_path / 'local.sqlite3'))
    monkeypatch.delenv('AI_BUDGET_TABLE_NAME', raising=False)
    monkeypatch.delenv('AI_BUDGET_TABLE_CONNECTION_STRING', raising=False)
    monkeypatch.delenv('AI_BUDGET_SQLITE_PATH', raising=False)
    get_store.cache_clear()
    get_budget_store.cache_clear()

    assert get_store() is get_budget_store()


def test_dev_sessions_are_separate_while_global_ledger_is_shared(monkeypatch, tmp_path):
    budget_path = tmp_path / 'shared-budget.sqlite3'
    production_path = tmp_path / 'production.sqlite3'
    development_path = tmp_path / 'development.sqlite3'

    _configure_environment(monkeypatch, production_path, budget_path)
    production_store = get_store()
    production_budget = get_budget_store()
    production_store.mutate('production-session', lambda state: state.update(owner='production'))
    reserve_ai_call('production-session')

    _configure_environment(monkeypatch, development_path, budget_path)
    development_store = get_store()
    development_budget = get_budget_store()
    development_store.mutate('development-session', lambda state: state.update(owner='development'))
    reserve_ai_call('development-session')

    assert development_store.read('production-session') == {}
    assert production_store.read('development-session') == {}
    assert production_budget.read('global-ai-budget')['calls'] == 2
    assert development_budget.read('global-ai-budget')['calls'] == 2

    # The hashed per-session quota projection lives in the shared ledger, while
    # the human-readable session projection remains in each environment.
    assert production_store.read('production-session')['ai_calls'] == 1
    assert development_store.read('development-session')['ai_calls'] == 1


def test_shared_ledger_enforces_one_cap_across_deployments(monkeypatch, tmp_path):
    budget_path = tmp_path / 'shared-budget.sqlite3'
    production_path = tmp_path / 'production.sqlite3'
    development_path = tmp_path / 'development.sqlite3'

    _configure_environment(monkeypatch, production_path, budget_path)
    get_budget_store().mutate(
        'global-ai-budget',
        lambda state: state.update(calls=149, reserved_cents=2998, reserved_usd=29.98),
    )

    _configure_environment(monkeypatch, development_path, budget_path)
    reserve_ai_call('development-session')

    _configure_environment(monkeypatch, production_path, budget_path)
    with pytest.raises(AIServiceError) as exc:
        reserve_ai_call('production-session')

    assert exc.value.code == 'ai_budget_limit'
    ledger = get_budget_store().read('global-ai-budget')
    assert ledger['calls'] == 150
    assert ledger['reserved_cents'] == 3000


def test_runtime_quality_counters_stay_with_each_environment(monkeypatch, tmp_path):
    budget_path = tmp_path / 'shared-budget.sqlite3'
    production_path = tmp_path / 'production.sqlite3'
    development_path = tmp_path / 'development.sqlite3'

    _configure_environment(monkeypatch, production_path, budget_path)
    record_ai_outcome('adaptive_plan', 'passed', 'production-check')

    _configure_environment(monkeypatch, development_path, budget_path)
    record_ai_outcome('adaptive_plan', 'ai_interpretation', 'development-check')

    assert get_store().read('ai-runtime')['counts'] == {'adaptive_plan:ai_interpretation': 1}
    assert get_budget_store().read('global-ai-budget') == {}

    _configure_environment(monkeypatch, production_path, budget_path)
    assert get_store().read('ai-runtime')['counts'] == {'adaptive_plan:passed': 1}
    assert get_budget_store().read('global-ai-budget') == {}
