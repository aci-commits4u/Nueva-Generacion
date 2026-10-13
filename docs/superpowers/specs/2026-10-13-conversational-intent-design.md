# Conversational intent and measured AI quality

Victor wants an AI layer that visibly reasons about requirements, asks useful follow-ups, and improves through repeatable testing. The previous single extraction prompt and large form under-deliver that experience. Earlier authorization to choose recommended defaults, record choices and deploy persists. The optional flow question has not changed the recommended conversational direction.

## Product direction

A focused assistant conversation with a live requirements panel, followed by a concise explicit approval review, signed offer comparison and evidence. Flight, hotel and limited general domains share the framework. Keep Python/FastAPI and static vanilla modules. Use Swiss/Minimalist product typography, white/cool-gray surfaces, charcoal navigation and teal actions. The generated conversation reference establishes geometry, not fake metrics or functionality. Every displayed status must reflect real state.

## AI engineering

Build a synthetic labeled corpus covering straightforward requests, negation, ambiguity, unsupported requirements, contradictory instructions, relative dates, time windows, strict price boundaries and injection. Separate development and holdout cases before tuning. Compare the existing baseline, a few-shot grounded extractor and extraction plus an independent coverage audit. Score against deterministic labels: exact field values, omissions, forbidden assumptions, unsupported coverage, source grounding, latency and tokens. Choose from observed results, not model size or agent count. Preserve failed experiments and uncertainty; no perfect-understanding claim.

Each production draft records stage/model/latency and source quotations. AI output remains a proposal. The audit can improve extraction but cannot authorize, create no preferences, change rules or purchase. Source quotations must match user conversation text. Missing and unsupported requirements remain visible. Provider errors never silently switch modes.

## Conversation contracts

`POST /api/intents` produces a draft with messages, provenance, trace and ranked questions. `POST /api/intents/{id}/clarify` consumes revision and a user message, reinterprets the full conversation, retains unsupported conditions conservatively and invalidates prior approval/offers. Check revision before inference and again during the conditional state write. Bound messages/turns and input size. Questions come from the reviewed profile; required gaps first, optional preferences second. Typed quick answers can fill the same review fields without a model purchase decision.

Approval still requires every profile field to be explicitly answered or explicitly no preference, the exact reviewed revision/digest and confirmation. Additional unsupported conditions hold checkout. Final approval/evidence retain conversation and source provenance. Existing sessions remain readable, and any new clarification invalidates old decisions for new execution.

## Continuous quality

Pure unit, semantic-label/scorer and enforcement tests run in GitHub Actions on pushes and pull requests without secrets. Live benchmarking is a deliberate bounded command. A secret-authenticated daily Vercel cron runs one rotating synthetic canary case through the selected pipeline, records a truthful result and never silently changes the model or grants approvals. Duplicate daily invocation is idempotent; missing secret rejects. The public quality view exposes synthetic benchmark summaries and canary status only, not user text or credentials. Failure/paused checks are visible, never fabricated PASS.

Separate interactive, evaluation and monitor daily counters so experiments do not consume the public demo's daily allocation. All purposes share the existing 200-call/$20 lifetime reservation cap; no reset, emergency increase or unbounded loop. Per-session interactive cap remains 8. Evaluation daily cap 60, monitoring at most two model calls/day and 40 lifetime. Preserve recorded usage. A exhausted evaluation/monitor budget pauses those checks without an automatic offline substitute.

## Security invariants

AI never approves; rules_engine alone emits PASS/HOLD/BLOCK. Customer-approved structured fields are authoritative, signed merchant checkout facts only, missing facts HOLD, signature/expiry/unknown-constraint gates unwaivable, exceptions exact-value/hash bound, native price exceptions require revised signed authorization, synthetic commerce only. Stable environment keys and durable Azure ETag state remain. Recheck these boundaries with changed conversation/revision and replay tests. No private keys, API keys or session cookies in traces, reports or Git.

## Verification and release

Observe failing tests before implementation, preserve the original live benchmark, evaluate candidates and untouched holdout, exercise real multi-turn Foundry and desktop/mobile flows, test cron authorization/idempotency and hosted persistence, obtain a fresh independent final review, then deploy the separate Vercel project. Keep the existing production available until the revised flow is verified. Document measured improvement and any remaining failures. This is a tested student prototype with simulated commerce.
