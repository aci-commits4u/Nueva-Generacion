"""Arm routing must not double reserve or silently migrate incumbent drafts."""
import sys
from types import SimpleNamespace

from app.ai_config import interpretation_call_count, prompt_version_for, PROMPT_VERSION, LEDGER_PROMPT_VERSION
from app.main import pinned_pipeline


def test_ledger_arm_has_own_version_and_bounded_call_advertisement():
    assert prompt_version_for('ledger')==LEDGER_PROMPT_VERSION
    assert prompt_version_for('adaptive_fast')==PROMPT_VERSION
    assert interpretation_call_count('ledger')==1
    assert interpretation_call_count('ledger',tool_loop=True)==2


def test_ledger_router_delegates_before_incumbent_reservation(monkeypatch):
    import app.ai_pipeline as pipeline
    calls=[]
    fake=SimpleNamespace(run_ledger_pipeline=lambda *a,**kw: calls.append((a,kw)) or {'pipeline':'ledger'})
    monkeypatch.setitem(sys.modules,'app.ledger_pipeline',fake)
    monkeypatch.setattr(pipeline,'reserve_ai_calls',lambda *a,**kw: (_ for _ in ()).throw(AssertionError('double reservation')))
    assert pipeline.run_pipeline('general','A lamp under $100','session',variant='ledger')=={'pipeline':'ledger'}
    assert calls[0][0]==('general','A lamp under $100','session')


def test_saved_arm_is_pinned_independently_of_new_intake_default(monkeypatch):
    monkeypatch.setenv('AI_PIPELINE_VERSION','ledger')
    assert pinned_pipeline({'pipeline':'adaptive_fast'})=='adaptive_fast'
    assert pinned_pipeline({'ai_runs':[{'pipeline':'adaptive'}]})=='adaptive'


def test_ledger_canary_does_not_call_or_score_legacy_cases(monkeypatch):
    import app.quality as quality
    monkeypatch.setenv('CRON_SECRET','synthetic-test')
    monkeypatch.setenv('AI_PIPELINE_VERSION','ledger')
    monkeypatch.setattr(quality,'_adaptive_cases',lambda: (_ for _ in ()).throw(AssertionError('wrong scorer')))
    result=quality.canary('Bearer synthetic-test')
    assert result['status']=='skipped'
    assert result['prompt_version']==LEDGER_PROMPT_VERSION
