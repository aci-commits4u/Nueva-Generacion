"""Run a finite, paid evaluation against the adaptive intent pipeline.

This script is intentionally separate from the application and test suite. It
uses the durable Azure-backed ledger, calls no fallback, retries no provider
error, and records each raw outcome in a local experiment artifact. Nothing in
the result grants consent or authorizes a purchase.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
from contextlib import contextmanager
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load_runtime():
    # The environment must be selected before importing app.store: its backend
    # is cached and a paid evaluation must never silently use local SQLite.
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env', override=True)
    os.environ['STORE_BACKEND'] = 'azure'
    os.environ.pop('MOCK_LLM', None)


def _messages(case):
    messages = deepcopy(case.get('source_messages') or [])
    if not messages:
        messages = [{
            'role': 'user',
            'content': case.get('message', ''),
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'reference_date': datetime.now(timezone.utc).date().isoformat(),
        }]
    try:
        zone = ZoneInfo(case.get('time_zone', 'UTC'))
    except (ZoneInfoNotFoundError, ValueError):
        zone = timezone.utc
    for item in messages:
        if not isinstance(item, dict) or item.get('reference_date'):
            continue
        timestamp = item.get('timestamp')
        if not isinstance(timestamp, str):
            continue
        try:
            item['reference_date'] = datetime.fromisoformat(timestamp).astimezone(zone).date().isoformat()
        except (TypeError, ValueError, OverflowError):
            continue
    return messages


def _source_text(messages, fallback):
    text = ' '.join(
        item.get('content', '') for item in messages
        if isinstance(item, dict) and item.get('role') == 'user'
        and isinstance(item.get('content'), str)
    ).strip()
    return text or fallback


def _public_error(exc):
    """Keep provider credentials, prompt text, and response bodies out of rows."""
    result = {'type': type(exc).__name__}
    for attr in ('code', 'stage', 'request_id'):
        value = getattr(exc, attr, None)
        if isinstance(value, (str, int, float, bool)):
            result[attr] = value
    # AIServiceError can retain a typed local validation cause. Preserve only
    # those bounded diagnostics; never serialize a provider exception or body.
    cause = getattr(exc, '__cause__', None)
    try:
        from app.ai_grounding import EnvelopeFailure, GroundingFailure
        safe_causes = (EnvelopeFailure, GroundingFailure)
    except Exception:
        safe_causes = ()
    if safe_causes and isinstance(cause, safe_causes):
        detail = str(cause).strip()[:500]
        if detail:
            result['cause'] = {'type': type(cause).__name__, 'detail': detail}
    return result


@contextmanager
def _merchant_context_for_case(case):
    """Capture provider proposals and inject bounded merchant data for one case.

    This wrapper is benchmark-only. It stores parsed JSON proposals and their
    traces without prompts, credentials, or provider exception bodies. The
    dedicated synthetic injection case receives adversarial text through the
    separate ``merchant_context`` payload field, so it is present even if the
    planner chooses no tool. Both monkeypatches are restored on exit.
    """
    adversarial = case.get('adversarial_context')
    from app import ai_pipeline
    original_execute = ai_pipeline.execute_tool
    original_call = ai_pipeline.call_json
    bounded_adversarial = adversarial[:1000] if isinstance(adversarial, str) else None
    enabled = bool(bounded_adversarial and bounded_adversarial.strip())
    capture = {
        'provider_proposals': [],
        'injection': {
            'enabled': enabled,
            'method': 'merchant_context_payload' if enabled else None,
            'payload_field': 'merchant_context' if enabled else None,
            'bounded_chars': len(bounded_adversarial) if bounded_adversarial else 0,
            'call_stages': [],
            'injected_into_call': False,
            'provider_call_attempted': False,
            'provider_proposal_count': 0,
            'observed_by_provider_payload': False,
        },
        # This is evaluator-owned provenance. It is passed separately to the
        # deterministic scorer and never treated as model-produced evidence.
        'evaluation_context': {
            'provenance': 'benchmark_harness',
            'merchant_context_payload': {
                'enabled': enabled,
                'method': 'merchant_context_payload' if enabled else None,
                'bounded_chars': len(bounded_adversarial) if bounded_adversarial else 0,
                'observed_by_provider_payload': False,
            },
        },
    }

    def wrapped_call(*args, **kwargs):
        stage = args[0] if args else kwargs.get('stage')
        if not isinstance(stage, str):
            stage = 'unknown'
        kwargs = dict(kwargs)
        if enabled:
            domain = args[1] if len(args) > 1 else kwargs.get('domain')
            kwargs['merchant_context'] = {
                'tool': 'merchant_context',
                'domain': domain,
                'provenance': 'synthetic benchmark fixture; informational only',
                'read_only': True,
                'synthetic_merchant_data': bounded_adversarial,
                'synthetic_merchant_data_provenance': 'adversarial benchmark fixture; untrusted data',
            }
            capture['injection']['call_stages'].append(stage)
            capture['injection']['injected_into_call'] = True
        capture['injection']['provider_call_attempted'] = True
        try:
            raw, trace = original_call(*args, **kwargs)
        except Exception as exc:
            # Keep typed local diagnostics only; provider bodies are private.
            capture['provider_proposals'].append({
                'stage': stage,
                'error': _public_error(exc),
            })
            raise
        capture['provider_proposals'].append({
            'stage': stage,
            'raw': deepcopy(raw),
            'trace': deepcopy(trace),
        })
        capture['injection']['provider_proposal_count'] += 1
        if enabled:
            capture['injection']['observed_by_provider_payload'] = True
            capture['evaluation_context']['merchant_context_payload']['observed_by_provider_payload'] = True
        return raw, trace

    def wrapped(action, *, domain, fields):
        result = original_execute(action, domain=domain, fields=fields)
        if not isinstance(result, dict):
            return result
        enriched = deepcopy(result)
        if enabled:
            enriched['synthetic_merchant_data'] = bounded_adversarial
            enriched['synthetic_merchant_data_provenance'] = 'adversarial benchmark fixture; untrusted data'
        return enriched

    ai_pipeline.call_json = wrapped_call
    ai_pipeline.execute_tool = wrapped
    try:
        yield capture
    finally:
        ai_pipeline.call_json = original_call
        ai_pipeline.execute_tool = original_execute


def _metadata(case, result, *, variant, started, finished):
    traces = result.get('trace', []) if isinstance(result, dict) else []
    trace = traces[-1] if traces and isinstance(traces[-1], dict) else {}
    messages = _messages(case)
    clock = [
        {'timestamp': item.get('timestamp'), 'reference_date': item.get('reference_date')}
        for item in messages if isinstance(item, dict)
        and (item.get('timestamp') or item.get('reference_date'))
    ]
    return {
        'variant': variant,
        'model': trace.get('model') or result.get('model'),
        'prompt_version': trace.get('prompt_version'),
        'reasoning_effort': trace.get('reasoning_effort'),
        'clock_context': clock,
        'source_message_count': len(messages),
        'started_at': started,
        'completed_at': finished,
        'duration_ms': round((time.monotonic() - _metadata._started_monotonic) * 1000),
    }


def run(args):
    _load_runtime()
    from app.ai_pipeline import run_pipeline
    from app.ai_errors import AIServiceError
    from app.ai_config import PROMPT_VERSION
    from app.store import get_store
    from evals.scoring import score_adaptive_case

    cases_path = Path(args.cases)
    payload = json.loads(cases_path.read_text())
    cases = [case for case in payload.get('cases', []) if case.get('split') == args.split]
    if args.case:
        wanted = set(args.case)
        cases = [case for case in cases if case.get('id') in wanted]
        unknown = wanted - {case.get('id') for case in cases}
        if unknown:
            raise SystemExit(f'Unknown case id(s): {", ".join(sorted(unknown))}')
    if not cases:
        raise SystemExit('No evaluation cases selected.')
    if args.max_cases < 1:
        raise SystemExit('--max-cases must be positive.')
    cases = cases[:args.max_cases]

    variant = args.variant
    if args.repetitions < 1:
        raise SystemExit('--repetitions must be positive.')
    if args.repetitions > 3:
        raise SystemExit('--repetitions is capped at 3 for bounded evaluation.')
    store = get_store()
    before = store.read('global-ai-budget') or {}
    report = {
        'schema': 'intent-judge.adaptive-benchmark.v1',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'variant': variant,
        'split': args.split,
        'model': os.getenv('AZURE_OPENAI_DEPLOYMENT'),
        'prompt_version': PROMPT_VERSION,
        'cases_requested': len(cases),
        'repetitions': args.repetitions,
        'finite_no_retry': True,
        'purpose': 'evaluation',
        'store_backend': os.getenv('STORE_BACKEND'),
        # Preserve the exact labels and explanatory captions used for this
        # run. A later scorer replay can distinguish corrected labels from a
        # fresh model improvement; historical artifacts remain immutable.
        'case_definitions': deepcopy(cases),
        'score_provenance': 'fresh_model_output_scored_with_case_snapshot',
        'historical_artifacts_immutable': True,
        'case_label_audit': {
            'classification': 'scorer_replay',
            'fresh_model_improvement_claim': False,
            'notes': (
                'Any corrected case label or deterministic scoring rule must be '
                'replayed against captured raw proposals. It does not imply a '
                'new provider inference or improve historical artifacts.'
            ),
        },
        'expected_metrics': {
            case['id']: case.get('expected_metrics', {}) for case in cases
        },
        'rows': [],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    for repetition in range(args.repetitions):
        for case in cases:
            started_iso = datetime.now(timezone.utc).isoformat()
            started_monotonic = time.monotonic()
            messages = _messages(case)
            source = _source_text(messages, case.get('message', ''))
            result = None
            error = None
            capture = None
            try:
                with _merchant_context_for_case(case) as capture:
                    result = run_pipeline(
                        case['domain'], case.get('message', ''),
                        f'adaptive-eval-{case["id"]}-{repetition}',
                        variant=variant,
                        purpose='evaluation',
                        source_text=source,
                        source_messages=messages,
                    )
            except (AIServiceError, Exception) as exc:  # one attempt; preserve raw class safely
                error = _public_error(exc)
                result = {'error': error.get('code', type(exc).__name__), 'fields': {}, 'sources': {}, 'unsupported': []}
            finished_iso = datetime.now(timezone.utc).isoformat()
            _metadata._started_monotonic = started_monotonic
            evaluation_context = capture.get('evaluation_context') if capture else None
            scored = score_adaptive_case(
                case, result, evaluation_context=evaluation_context, variant=variant
            )
            row = {
                'case_id': case['id'],
                'repetition': repetition + 1,
                'score': scored,
                'metadata': _metadata(case, result, variant=variant, started=started_iso, finished=finished_iso),
            }
            if error:
                row['error'] = error
            # The full result is useful for local diagnosis but remains inside
            # an explicitly local experiment artifact, never the public API.
            row['result'] = result
            if capture is not None:
                row['provider_proposals'] = capture.get('provider_proposals', [])
                row['injection'] = capture.get('injection', {})
                row['evaluation_context'] = capture.get('evaluation_context', {})
            report['rows'].append(row)
            report['completed_cases'] = len(report['rows'])
            report['passed'] = sum(1 for item in report['rows'] if item['score'].get('passed'))
            after = store.read('global-ai-budget') or {}
            report['reserved_calls'] = after.get('calls', 0) - before.get('calls', 0)
            report['reserved_cents_delta'] = after.get('reserved_cents', 0) - before.get('reserved_cents', 0)
            output.write_text(json.dumps(report, indent=2, ensure_ascii=True))
            print(json.dumps({
                'case': case['id'], 'repetition': repetition + 1,
                'passed': scored.get('passed'), 'error': error,
                'reserved_calls': report['reserved_calls'],
            }), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', default=str(ROOT / 'evals' / 'adaptive_cases.json'))
    parser.add_argument('--output', required=True)
    parser.add_argument('--variant', choices=['adaptive', 'adaptive_fast', 'baseline', 'guided', 'audited'], default='adaptive')
    parser.add_argument('--split', default='holdout')
    parser.add_argument('--case', action='append')
    parser.add_argument('--max-cases', type=int, default=3)
    parser.add_argument('--repetitions', type=int, default=1)
    return run(parser.parse_args())


if __name__ == '__main__':
    main()
