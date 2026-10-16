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

## Hosted v18 failure and selective v19 review

V18 runtime `9795d35` reached the development deployment after exact-source CI
38929689667 passed. The hosted variation then failed: the customer supplied
both airport sets and November 12, 2026 in one comma-separated reply. The model
retained the airports and zero layovers but classified the exact date as
ambiguous and asked for it again. No manual date entry or retry was credited
as success. See `artifacts/hosted-acceptance-failure-20261016.md`.

V19 keeps ordinary turns at one AI pass and selectively adds a reviewer when
an exact source-backed date contradicts the model's proposed question. The
detector uses the existing temporal and grounding validators as feedback; it
does not insert a date into the customer's requirements. The second AI role
must produce a source-grounded claim. Ambiguous alternatives, qualified dates,
and past booking dates do not trigger that correction as if already answered.
Questions repaired by the reviewer are not restored from the first pass.
Stale assistant prose attached to a suppressed answered question is omitted
from the current chat while immutable run history remains available.

The exact hosted-failure variant then passed a fresh local v19 DOM run in two
live stages: 7.182 s initially and 4.473 s for the multi-detail reply. All five
fields appeared correctly in review without a repeated date or layover
question. After explicit optional choices, approval succeeded, the three-
connection purchase returned HTTP 409, the matching simulated purchase
completed, evidence downloaded, and the receipt survived reload. Root checked
11 evidence properties, including canonical digest, trusted issuer signature,
VI chain, exact approved date/airport sets/price/zero connections and absence
of exceptions. See `artifacts/local-v19-uat-report.md`.

That test also exposed a local review-validation error being labeled as a
connection interruption. The UI now shows the actual unanswered-field message
and makes no approval request until it is resolved. The browser regression
checks this distinction.

## V19 selective reviewer laboratory result (October 16, 2026)

The saved v18 failure was replayed through the v19 selective reviewer with one
bounded evaluation stage. The candidate had asked for a departure date even
though the verified second customer turn already said “November 12, 2026.” The
deterministic diagnostic supplied `question_answer_already_resolvable` as
review context; no second attempt or fallback was used.

The live reviewer returned a grounded draft containing departure date
`2026-11-12`, origin airports `[YYZ, YHM]`, destination airports `[LHR, LGW]`,
`max_connections: 0`, and `max_total_cents: 79999`. It retired the date
question and returned `review_required` with `question: null`. Grounding passed.
The single call took 4.4 seconds and used 5,020 prompt tokens plus 536
completion tokens. The complete local result is retained in the ignored lab
artifact at
`/Users/victor/Nueva-Generacion-dev/ignored/artifacts/selective-review-lab-v19.json`.
It is development evidence only and is not a deployment or purchase claim.

## Hosted v19 acceptance and release

The development deployment is READY at
**https://intent-judge-perfected-dev.vercel.app/**. Runtime source
`a670e0cb65f9b161faa2fb61baf9afaa655bf53f` is deployment
`dpl_5pyLdGTs4br2VpKuPanxWmTxXF6N`; [exact-source CI
38932105356](https://github.com/aci-commits4u/Nueva-Generacion/actions/runs/38932105356)
passed 616 pytest checks and all eleven browser suites before deployment.

A fresh hosted DOM session repeated the exact v18 failing inputs. Both airport
sets, November 12, 2026, strict `79999` cents, and zero connections persisted.
There was no remaining question about the date, airports, budget, nonstop, or
layovers. The two live responses took **11.789 s** and **6.887 s**, consuming
two model stages total. These hosted timings include the application path;
the faster local measurements above are not presented as hosted latency.

Explicit review and optional choices led to the signed comparison. The bad
three-connection purchase returned HTTP 409; the matching simulated purchase
completed. Evidence downloaded and the receipt restored after reload. Root
independently verified eleven digest, trusted issuer signature, VI chain,
purchase binding, and approved-intent properties in the downloaded packet.
No real booking or payment occurred. Evidence is retained in
`artifacts/hosted-v19-uat-report.md`, `hosted-v19-evidence.json`, and
`hosted-v19-signature-verification.json`. A deployment-scoped runtime scan
returned no error/fatal log counts after acceptance.

Production remained READY on `dpl_GnMbCwaXUYxyyToc5w8oZQqLf4En`, runtime
`f505c4c48203d3f8b4f881c639cc8c43db37aade`. No production promotion occurred.

The model inventory was inspected read-only. This resource has only
`gpt-oss-120b` deployed. Microsoft documents strict structured outputs for
`gpt-oss-20b`, but this account exposed no deployable SKU/quota for it. No model
resource was created. The selected change therefore improves the existing
live model path rather than claiming an untested provider replacement.

## Verification and budget boundary

The latest local count is 616 pytest passes. All eleven headless browser regression suites passed, including the visible
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

The v19 development release and hosted acceptance are complete as recorded
above.
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
