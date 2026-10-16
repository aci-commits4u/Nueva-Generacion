#!/usr/bin/env python3
"""Run the isolated A/B trajectory adapter.

Safe default (no ``--live``): validate the exposed development fixtures only;
no server, model, app import, credential or environment mutation occurs.

Live example, with explicit finite caps::

    .venv/bin/python scripts/benchmark_trajectories.py \
      --live --arm-a-url http://127.0.0.1:8000 \
      --arm-b-url http://127.0.0.1:8100 \
      --max-conversations 2 --max-model-calls 12 \
      --output output/trajectory-report.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evals.trajectories import (DEFAULT_CASES, TrajectoryError, TrajectoryRunner,
                                load_trajectory_set)


def _positive(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def _select(payload: dict, family_ids: list[str] | None) -> dict:
    if not family_ids:
        return payload
    wanted = set(family_ids)
    families = payload.get("families", [])
    known = {item.get("id") for item in families if isinstance(item, dict)}
    unknown = wanted - known
    if unknown:
        raise TrajectoryError(f"Unknown family id(s): {', '.join(sorted(unknown))}")
    selected = [item for item in families if item.get("id") in wanted]
    return {**payload, "families": selected, "selection": "subset"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default=str(DEFAULT_CASES), help="Exposed trajectory JSON file.")
    parser.add_argument("--output", default="-", help="JSON report path, or '-' for stdout.")
    parser.add_argument("--family", action="append", dest="families", help="Run one family (repeatable).")
    parser.add_argument("--live", action="store_true", help="Make actual HTTP API calls. Omit for fixture validation.")
    parser.add_argument("--arm-a-url", help="A/control server base URL (required with --live).")
    parser.add_argument("--arm-b-url", help="B/ledger server base URL (required with --live).")
    parser.add_argument("--max-conversations", type=_positive,
                        help="Hard cap on total live A/B conversations.")
    parser.add_argument("--max-model-calls", type=_positive,
                        help="Hard cap on observed model calls; server ledger remains authoritative.")
    parser.add_argument("--repetitions", type=_positive, default=1,
                        help="Paired repetitions per family (default: 1).")
    parser.add_argument("--counterbalance", action="store_true",
                        help="Swap arm order on alternating repetitions.")
    parser.add_argument("--include-explanation", action="store_true",
                        help="Exercise the optional deterministic-decision explanation model call.")
    parser.add_argument("--timeout", type=float, default=30.0,
                        help="Per-request timeout in seconds (default: 30).")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.live:
        missing = [name for name, value in (("--arm-a-url", args.arm_a_url), ("--arm-b-url", args.arm_b_url),
                                             ("--max-conversations", args.max_conversations), ("--max-model-calls", args.max_model_calls)) if not value]
        if missing:
            parser.error("--live requires " + ", ".join(missing) + "; live caps are mandatory")
    try:
        payload = _select(load_trajectory_set(args.cases), args.families)
        # The default session factory is intentionally created here without
        # touching environment variables.  The timeout is applied by wrapping
        # the explicit constructor, keeping A and B independently configured.
        session_factory = None
        if args.live:
            from evals.trajectories import HttpApiSession
            session_factory = lambda url: HttpApiSession(url, timeout=args.timeout)
        report = TrajectoryRunner(
            payload,
            {"A": args.arm_a_url, "B": args.arm_b_url} if args.live else {},
            live=args.live,
            max_conversations=args.max_conversations,
            max_model_calls=args.max_model_calls,
            repetitions=args.repetitions,
            counterbalance=args.counterbalance,
            include_explanation=args.include_explanation,
            session_factory=session_factory,
        ).run()
    except TrajectoryError as exc:
        parser.error(str(exc))
    output = json.dumps(report, indent=2, ensure_ascii=True)
    if args.output == "-":
        print(output)
    else:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output + "\n")
        print(json.dumps({
            "output": str(target), "mode": report.get("mode"),
            "rows": len(report.get("rows", [])),
            "primary_complete_denominator": report.get("primary_complete_denominator"),
            "primary_complete_numerator": report.get("primary_complete_numerator"),
            "false_hold_numerator": report.get("false_hold_numerator"),
            "correct_refusal_numerator": report.get("correct_refusal_numerator"),
        }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
