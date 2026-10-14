"""Synthetic quality reports and bounded authenticated production canaries.

The quality surface measures the adaptive contract rather than only field
accuracy. A useful planner must preserve exact customer provenance, avoid
asking for facts already supplied or declined, and only describe merchant
observations that came from an executed read-only tool. It never receives
purchase authority.
"""
from __future__ import annotations

import json
import os
import secrets
import statistics
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException

from app.ai_config import PROMPT_VERSION, selected_pipeline
from app.store import get_store
from evals.scoring import score_adaptive_case

ROOT = Path(__file__).resolve().parent.parent
ADAPTIVE_CASES = ROOT / 'evals' / 'adaptive_cases.json'


def _now():
    return datetime.now(timezone.utc).isoformat()


def _adaptive_cases():
    try:
        payload = json.loads(ADAPTIVE_CASES.read_text())
    except (OSError, ValueError):
        return []
    cases = payload.get('cases', []) if isinstance(payload, dict) else []
    return [case for case in cases if isinstance(case, dict) and case.get('id')]


def _case_messages(case):
    messages = deepcopy(case.get('source_messages') or [])
    if messages:
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
    return [{
        'role': 'user',
        'content': case.get('message', ''),
        'timestamp': _now(),
        'reference_date': datetime.now(timezone.utc).date().isoformat(),
    }]


def _case_source(case, messages):
    source = ' '.join(
        item.get('content', '') for item in messages
        if isinstance(item, dict) and item.get('role') == 'user'
        and isinstance(item.get('content'), str)
    ).strip()
    return source or case.get('message', '')


def display_report(report):
    """Expose interrupted work without allowing an automatic paid replay."""
    if report and report.get('status') == 'running':
        try:
            started = datetime.fromisoformat(report['started_at'])
            age = (datetime.now(timezone.utc) - started).total_seconds()
        except (KeyError, TypeError, ValueError):
            age = 10**9
        if age > 75:
            return {
                **report,
                'status': 'unavailable',
                'reason': 'The scheduled worker was interrupted. Paid inference will not be replayed for this day.',
            }
    return report


def _benchmark_summary(file):
    try:
        report = json.loads(file.read_text())
    except (OSError, ValueError, TypeError):
        return None
    rows = report.get('rows') if isinstance(report, dict) else []
    rows = rows if isinstance(rows, list) else []
    durations = [
        row.get('metadata', {}).get('duration_ms', row.get('duration_ms'))
        for row in rows if isinstance(row, dict)
    ]
    durations = [value for value in durations if isinstance(value, (int, float))]
    passed = report.get('passed')
    if not isinstance(passed, int):
        passed = sum(1 for row in rows if isinstance(row.get('score'), dict) and row['score'].get('passed'))
    case_count = report.get('completed_cases', report.get('cases_requested', report.get('cases', len(rows))))
    if isinstance(case_count, (list, tuple, dict, set)):
        case_count = len(case_count)
    if not isinstance(case_count, int):
        case_count = len(rows)
    metrics = [
        row.get('score', {}).get('adaptive_metrics', {}) for row in rows
        if isinstance(row, dict) and isinstance(row.get('score'), dict)
    ]

    def count(name):
        return sum(1 for item in metrics if item.get(name) is True)

    return {
        'variant': report.get('variant', 'unknown'),
        'split': report.get('split', 'unknown'),
        'cases': case_count,
        'passed': passed,
        'median_ms': round(statistics.median(durations)) if durations else 0,
        'model_calls': sum(
            len(row.get('result', {}).get('trace', []))
            for row in rows if isinstance(row, dict) and isinstance(row.get('result'), dict)
        ),
        'reserved_calls': report.get('reserved_calls'),
        'model': report.get('model'),
        'prompt_version': report.get('prompt_version'),
        'adaptive_metrics': {
            'source_coverage_passed': count('source_coverage_ok'),
            'tool_observations_grounded': count('tool_observations_are_executed'),
            'no_repeated_known_question': sum(
                1 for item in metrics if item.get('repeated_known_field') is False
            ),
            'no_question_for_declined': sum(
                1 for item in metrics if item.get('repeats_declined_preference') is False
            ),
            'authority_safe': count('authority_ok'),
        },
        'created_at': report.get('created_at'),
    }


def _public_monitor(report):
    """Keep the API report useful without publishing conversation or traces."""
    if not report:
        return None
    safe = {
        key: report.get(key) for key in (
            'date', 'case_id', 'status', 'started_at', 'completed_at',
            'prompt_version', 'variant', 'stages', 'reason', 'clock_context',
        ) if key in report
    }
    if isinstance(report.get('metrics'), dict):
        safe['metrics'] = report['metrics']
    return safe


def overview():
    benchmarks = []
    for file in sorted((ROOT / 'evals' / 'reports').glob('*.json')):
        summary = _benchmark_summary(file)
        if summary:
            benchmarks.append(summary)
    adaptive_experiments = []
    for file in sorted((ROOT / 'evals' / 'experiments').glob('adaptive-*.json')):
        summary = _benchmark_summary(file)
        if summary:
            adaptive_experiments.append(summary)
    today = datetime.now(timezone.utc).date().isoformat()
    current_state = get_store().read('quality-' + today) or get_store().read('quality-latest') or {}
    publication = ROOT / 'evals' / 'native-publication.json'
    native = None
    if publication.exists():
        try:
            native = json.loads(publication.read_text())
        except (OSError, ValueError):
            native = None
    return {
        'pipeline': selected_pipeline(),
        'prompt_version': PROMPT_VERSION,
        'benchmarks': benchmarks,
        'adaptive_experiments': adaptive_experiments,
        'adaptive_quality_contract': {
            'source_coverage': 'Every model criterion and typed field must cite an exact customer-source span.',
            'question_policy': 'No question for an already-known or explicitly declined detail.',
            'tool_provenance': 'Offer observations count only when backed by an executed read-only signed-facts lookup.',
            'authority_boundary': 'Planner output never authorizes, approves, or purchases.',
        },
        'monitor': _public_monitor(display_report(current_state.get('report'))),
        'runtime': get_store().read('ai-runtime'),
        'native_evaluation': native,
        'limitations': (
            'Synthetic holdouts measure implementation behavior; they do not guarantee complete understanding. '
            'Historical native benchmarks remain historical. Customer review and deterministic enforcement remain mandatory.'
        ),
    }


def canary(authorization):
    """Run one authenticated daily adaptive canary, at most once per UTC day."""
    secret = os.getenv('CRON_SECRET', '')
    if not secret or not secrets.compare_digest(
        (authorization or '').encode(), ('Bearer ' + secret).encode()
    ):
        raise HTTPException(401, 'Authenticated quality scheduler required.')
    date = datetime.now(timezone.utc).date()
    # The adversarial merchant-context fixture is exercised by the dedicated
    # benchmark harness, where its bounded tool-data injection is installed.
    # The daily canary remains a plain production-shaped request and never
    # pretends that an injection case ran when it did not.
    all_cases = _adaptive_cases()
    cases = [
        case for case in all_cases
        if not (case.get('expected_metrics') or {}).get('adversarial_tool_context')
    ] or all_cases
    if not cases:
        raise HTTPException(503, 'Adaptive quality cases are unavailable.')
    case = cases[date.toordinal() % len(cases)]
    key = 'quality-' + date.isoformat()
    owner = secrets.token_hex(12)
    variant = selected_pipeline()
    messages = _case_messages(case)
    source_text = _case_source(case, messages)

    def claim(state):
        if state.get('report'):
            state['report'] = display_report(state['report'])
            return False, state['report']
        report = {
            'date': date.isoformat(),
            'case_id': case['id'],
            'status': 'running',
            'variant': variant,
            'prompt_version': PROMPT_VERSION,
            'started_at': _now(),
            'clock_context': [
                {'timestamp': item.get('timestamp'), 'reference_date': item.get('reference_date')}
                for item in messages if isinstance(item, dict)
                and (item.get('timestamp') or item.get('reference_date'))
            ],
        }
        state.update(owner=owner, report=report)
        return True, report

    claimed, report = get_store().mutate(key, claim)
    get_store().mutate('quality-latest', lambda state: state.update(report=report))
    if not claimed:
        return report
    try:
        from app.ai_pipeline import run_pipeline
        result = run_pipeline(
            case['domain'], case.get('message', ''), key,
            variant=variant,
            purpose='monitor',
            source_text=source_text,
            source_messages=messages,
        )
        scored = score_adaptive_case(case, result, variant=variant)
        report.update(
            status='passed' if scored.get('passed') else 'failed',
            metrics=scored.get('adaptive_metrics', {}),
            stages=len(result.get('trace', [])) if isinstance(result, dict) else 0,
        )
    except Exception:
        # Provider details, source text, and credentials never reach the public
        # report. A failed worker is unavailable; the scheduler will not replay
        # it today because the claim remains durable.
        report.update(
            status='unavailable',
            reason='Live inference could not complete within its configured limits. No fallback was used.',
        )
    report['completed_at'] = _now()

    def finish(state):
        if state.get('owner') == owner:
            state['report'] = report
    get_store().mutate(key, finish)
    get_store().mutate('quality-latest', lambda state: state.update(report=report))
    return report
