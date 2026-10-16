# Faster conversation: latency, grounding, and UAT

This document records the `feature/faster-intent` work in the development
checkout. It addresses a real user trace, preserves the existing approval and
Verifiable Intent boundary, and records the failures and subsequent live retest.
It is a development record, not a release claim.

## The trigger and the actual fix

The user entered:

> tor to london and also no layovers and less than 800 $

The first run used four turns. Each turn consumed two model stages at roughly
20–22 seconds, so the eight-stage session allowance ended the conversation
after the fourth turn. This was a session-stage cutoff, not exhausted Azure
credit. The model proposed the request, but the validator did not yet ground
“no layovers” or the strict less-than price expression.

The new grounding rules normalize “no,” “zero,” and “without layovers” to
`max_connections: 0`. This is a connection limit, not a stronger `nonstop`
claim. A strict “less than $800” becomes `max_total_cents: 79999`. Foreign
currency and nightly terms remain separate and are preserved rather than
converted into an unrelated total.

The `adaptive_fast` path now uses one normal model call. It consumes a second
call only when the model selects a bounded read-only tool action. Its compact
source payload still carries the complete customer history and catalog
bindings, so the latency reduction does not discard prior evidence.

## Latency lab

The four-request comparison is recorded in
`artifacts/speed-lab-v16/report.json`.

| Request | Low reasoning | Medium reasoning |
|---|---:|---:|
| Flight | 6.799 s total; 5.859 s provider call | 11.056 s total; 10.544 s provider call |
| Hotel | 5.209 s total; 4.760 s provider call | 21.019 s total; two calls of 10.092 s and 10.267 s |

Low reasoning was selected for the fast path because it was faster in these
four requests. The sample does not establish a universal threshold or prove
that low reasoning is more accurate for every task.

## Independent v16 UI result

The independent UI run used six live stages. Observed timings were 7.713 s for
the initial turn, 7.648 s and 6.163 s for the next turns, 5.919 s for the
correction, and 12.048 s for the hotel request, which used two stages.

The no-layover and strict-budget grounding fix was visible. The conversation
still failed to retain a departure choice between `YYZ` and `YHM`, even after a
repeat. Both are valid catalog codes, but the model omitted them while saying
it needed a specific choice. Entering Manual Review was possible and proved
that the three-connection offer was held, but this is not a full conversational
pass. The failure report is `artifacts/fast-live-uat-report.md`.

## V17 prompt direction

The next prompt gives generic set semantics and the profile matching operator
`op=in`: an array represents all acceptable values, with OR/either meaning,
rather than an uncertain request to pick one value. The fresh v17 real-UI
retest failed with HTTP 502 after two calls and stopped without a workaround;
the report is `artifacts/fast-v17-retest-report.md`. There is no deployment or
success claim for this prompt.

A private diagnostic followed by one real model stage produced the correct raw
sets—origin `[YYZ, YHM]` and destination `[LHR, LGW]`. The source catalogue had
split the OR expression into separate chunks such as “Depart from YYZ” and
“and arrive at LHR”; grounding then dropped the second airport codes. The
current finding is therefore evidence-layer clipping of a correct AI proposal,
not proof that the model generally failed to understand the alternatives. The v18 fix keeps exact source alternatives together.

Saved v15 tasks are marked `refresh required`. One explicit refresh preserves
all messages, requires a new approval, and does not silently fall back to a
different parser or mode.

## V18 fresh UI result

The fresh v18 report is `artifacts/fast-v18-uat-report.md`. It used a cold
restarted local development server and a fresh headless DOM session without
request interception, seeding, offline parsing, manual airport selection,
booking, or payment.

The flight flow passed in three live turns: 6.614 s initially, 5.554 s for
the complete airport/date update, and 7.479 s for the correction. It retained
origin `[YYZ, YHM]`, destination `[LHR, LGW]`, November 12, 2026, strict
`79999` cents, and `max_connections: 0`. The intentional correction changed
only `max_connections` to `1`; no settled question, manual-airport step,
fallback, or repeated paid call occurred. Review and approval showed the
`$295` nonstop offer as Intent-checked and the `$280` three-connection offer
held with `Required: 1 / Offer: 3`. No purchase action was clicked.

The fresh Kyoto hotel flow used two model stages and took 13.377 s. It retained
the required breakfast and optional cancellation without asking either again,
then inspected two synthetic read-only offers. A selector harness timeout
occurred during review; the tester resumed the existing context and did not
repeat paid calls. That harness event is recorded transparently and is not a
conversational failure.

## Verification and budget boundary

The latest local count is 606 pytest passes. All eleven headless browser regression suites passed, including the visible
deferred-review warning and multiple-choice preservation. These deterministic
fixtures remain separate from live UI evidence. The v18 report above is a completed local
UAT artifact. No model calls were made for this documentation pass.

The operational configuration allows up to 1,500 calls and 64 stages per
session, with up to 31 follow-ups and a bounded two-cent minimum reservation
per application call. The shared monetary cap remains `$30`; the configured
stage ceiling is 1,500. Reservations are conservative application accounting,
not Azure billing. There is no repricing or ledger reset.

If a second budget reservation fails for capacity, the system preserves the
first grounded candidate, marks review as `review_required`, and shows a
system warning. It does not fabricate AI text. Provider errors continue to
propagate visibly.

Future deployment is development-only and remains pending CI and hosted UAT;
the v18 result is local evidence, not a deployment claim.
Production remains on the v15 runtime and its prior operational cap until an
explicit promotion. That distinction belongs in release engineering notes;
the user-facing product does not need an unprompted environment warning.

## Current boundary

The exact failing airport-choice flow and an intentional layover correction now
pass the local live conversation and review checks. This finite sample does
not establish perfect interpretation across all requests. The model remains
probabilistic; source grounding, explicit review, and deterministic signed-offer
checks remain necessary. Tool-assisted turns can still be slower than ordinary
clarification turns. No real purchase, payment, fallback, or automatic approval
is implied by these tests.
