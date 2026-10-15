# Messy hidden user testing

This record captures an independent headless run against the real deployed UI
on October 14, 2026. It used visible-page typing and clicking with no route
interception, mocks, direct API calls, source access, offline fallback, or
Explain action. Five live sends consumed ten model stages: two original
prompts, two fresh flight repeats after a harness aria-label mismatch, and one
flight clarification. No checkout was attempted because neither case reached
approved offer-ready state.

## Flight: slow start, useful recovery, unresolved constraints

The first flight prompt was:

> I’m trying to get to Tromsø from Lisbon for a short work trip late January, probably around the 22nd, but the date can slide a day or two. I need one checked bag and I really don’t want a red-eye or a connection longer than four hours. Keep the fare around €750 if possible; if the cheap option is a long layover, ask me first.

At the ten-second capture, the page showed Foundry availability and an
“Interpreting and checking coverage…” state with the submit control disabled.
The UI clearly gave the request a 90-second deadline and saved the text, so
this is a latency observation rather than a terminal failure.

The later repeat finished at roughly 30 seconds and generated a useful date
question. The tester answered visibly:

> Please use €750 all-in as the hard maximum for the round trip. Keep the dates flexible by a day or two around January 22, 2027, and keep my other preferences: one checked bag, no red-eye, and no connection longer than four hours. If nothing fits under €750, ask me before proceeding.

The UI normalized the date window to January 20–24, 2027 and retained the
round-trip, checked-bag, no-red-eye, and maximum-four-hour-connection clauses
as unsupported conditions. It then asked for the maximum amount in US dollars
and cents. The request remained held with no offer or checkout.

This exposed two guidance issues: the date example used January 20–24, 2026
even though the request was for 2027, and the next question demanded a USD
amount after the customer supplied euros. The flow preserved the constraints,
but the conversion boundary and examples need clearer handling.

## Hotel: safe hold, no useful next question

The exact hotel prompt was:

> I’m heading to Tbilisi for a ceramics residency in early April next year, probably four nights around the 3rd but I might make it five. I’d like somewhere quiet and walkable to the old town, roughly €140 a night, and a late check-in after 11pm. A colleague may join so twin beds would be useful, but breakfast is completely optional and I can skip it if that makes the search easier. Please avoid party hostels.

At approximately 20, 50, and 90 seconds, the rendered UI remained at
“Review needed before proceeding” and said it could not safely determine the
next step. It retained Tbilisi and surfaced the ambiguities around the date,
four-versus-five nights, and the nightly price. It did not invent a date,
price, hotel, or purchase. The visible record showed one captured criterion,
three still open, and eleven follow-ups remaining, but it produced no useful
question. This is a real planner failure, not a safe successful clarification.

The isolated hotel context was closed before a follow-up could be attempted,
and the six-send budget prevented starting another hotel session plus a
clarification. Root later read the actual hotel intent beginning `kJ25…` and
found persisted normalized state for both roles with `review_required` at
approximately 8.2 and 8.1 seconds. The raw hotel model output was not stored,
so this run does not prove the exact internal cause.

An archived v6 raw-model mismatch between `price_limit_basis` and
`price_limit` shows one plausible failure mode: the normalizer can discard a
useful planner question when the model's field names do not match its contract.
That artifact is diagnostic context, not proof that it caused this hotel run.

## v10 follow-up

Runtime `e289d14d4461bf006296d3cd534bb72c5168a461` is READY as
`dpl_Gt7ZpCUmVx3UgfTEBhNo8akBJ9tA`, using prompt
`intent-envelope-v10-planner-repair-feedback`. CI run
`38595018587` passed 500 pytest tests and ten browser suites; the offline and
intercepted browser results are separate from live Foundry behavior.

The same Tbilisi prompt now generated a useful date question at about 20
seconds. After the visible clarification, the UI retained April 3–7, 2027 and
asked a second useful question for the total USD budget at about 45 seconds.
The review visibly retained the original five unsupported conditions: the
foreign-currency nightly preference, quiet and walkable location, late
check-in, twin beds, and avoiding party hostels. It did not show the typed
`$175` USD nightly cap or the optional April 8 extension from the clarification,
so the artifact did not prove that those new conditions survived the review.
Azure matching-draft readback now confirms that both v10 model roles omitted
the `$175` nightly cap and April 8 extension before UI review. This is a
provider coverage failure, not a sidebar rendering issue. Asking for a total
USD amount after a nightly cap was correct because those are different
constraints. There was no approval or purchase.

The London portion consumed two fresh contexts. The first stopped on a harness
locator/text change before selection; the second selected `YTZ` and `YYZ`, but
the bounded runner stopped when the button changed from “Choose one or more →”
to “Use 2 airports →”. It never reached the departure question, natural-
language correction, or review. Those four v10 live sends are evidence of
improved hotel planning and a test-harness/control-label boundary, not proof
that the London correction path passed. The isolated contexts are now closed.

The repair adds planner rejection feedback to the second Foundry role and
sanitized diagnostic codes. It keeps the fail-closed behavior: no static
fallback question or alias guess is used. Frontend guidance uses dollar
examples without inventing dates.

## Targeted provider experiment

A targeted v11 provider experiment used a new payload and prompt. It retained
the `$175` USD nightly cap but still omitted the optional April 8 extension
after two model stages. The saved failure artifact is
`artifacts/planner-v11-live-coverage-experiment.json`; it must remain separate
from the UI UAT and is not a replacement for the v10 report.

The next repair is a narrow cross-domain literal money/date coverage guard
with prompt version `v12-literal-coverage`. When an exact customer clause is
not represented, the server will preserve it as unsupported while still
allowing the model to generate a useful question. This does not guarantee
complete coverage, add static questions, grant AI approval, or introduce a
third model call or automatic retry.

## v12 provider and release evidence

Runtime `cbf2885075451b54c3851e78471a0c399aced399` is READY as
`dpl_5BEptpVzzSRHLyifhcLoqwB3BfBi` at the public perfected URL, using prompt
`intent-envelope-v12-literal-coverage`. CI run `38599896732` passed 516 pytest
tests and ten browser suites in 16,918 ms; those offline/intercepted results
remain distinct from live UI evidence.

A targeted v12 provider experiment, not a UI UAT, passed all six checks. It
retained the `$175` nightly cap and optional April 8 extension, kept the
April 3–7 selection unchanged, did not turn `$175` into a total, and produced
no duplicate date flag. The saved artifact is
`artifacts/planner-v12-live-coverage-experiment.json`.

The live model emitted both literal clauses in that run, so the guard added
zero flags. Deterministic regressions also prove that omission from either
mock model role triggers retention of the held, source-backed clauses. The
guard supports explicit money/date literal identities only: it does not
guarantee semantic coverage, infer typed values, generate approval, or add an
extra model call. The source fixes prevent neighboring-unit or optional-clause
bleeding, retain money operators, reject raw model proposals as coverage,
distinguish corrections from ranges, and bound overflow.

## v12 live UI outcome

The archived v12 UI reports make the limits concrete. The Tbilisi
coverage-audit reference is `9e6037c156e8`; after the clarification error, the
old draft remained and the new April dates, `$175` cap, and April 8 option were
not saved. The Valparaíso initial reference is `010b8b2171c2`; it reached a
terminal error with no draft, useful question, clarification control, or
review path. No purchase was attempted in either hotel/general case.

The separate v12 London run completed four turns and reached first review with
the corrected route state, but purchase was not completed because the test
harness lost the context/locator path. Its report is
`artifacts/v12-flight-uat-20261014/report.json`. These results are UI-only
evidence and remain separate from provider experiments; they do not establish
that v12 solved the broader coverage problem.

The hotel improvement is therefore bounded: useful date and total questions
were observed in v10, while v12 still lost the clarification after a live
error. The London review path reached the corrected state, but its purchase
step was not completed.

## V13 headless UI UAT checkpoint

The v13 public runtime used source commit
`40d65516c5676326372bcc56b7fae8cb474bbb67`, deployment
`dpl_5fShL2wRVkcUXjJJmiHiwxock91Z`, and prompt
`intent-envelope-v13-source-references`. CI run
`38607867597` reported 529 pytest passes and ten browser suites; those suites
were offline or intercepted and are separate from live Foundry behavior.

In an independent headless UI run, the Tbilisi hotel submission failed before
producing a useful question at roughly 40 seconds, with reference
`79d7c6f7d1ed`. The Valparaíso submission failed the same way at roughly 50
seconds, with reference `4fceddc0a615`. Both rendered a terminal
`adaptive_review`/`ai_interpretation` error before a clarification control,
review path, answer, approval, or purchase. Only two of four planned live
sends were used; no retry or fallback was attempted. The complete report is
`artifacts/messy-hidden-v13-20261014/REPORT.md`.

A separate WAW→BER flight run completed one live send in about 25 seconds and
captured seven fields without asking again. The tester had accidentally chosen
explicit “No Preference” values for nonstop, economy, and one-way before
approval. A $295 simulated purchase downloaded and reloaded with zero
exceptions, but the $280 connecting offer matched because the nonstop rule had
been removed. This is not acceptance of the intended nonstop hold. The run is
recorded in `artifacts/v13-flight-uat-20261014/final-verification.json`. The generated
AI prose also incorrectly said both offers met the request; that remains an
open model-quality defect.

The ambiguous-money tester stopped the harness after ten seconds while it was
still loading, before a proper terminal state was observed, and saved no
authorization. That case is inconclusive rather than a product pass or
failure. The five-step mobile tutorial passed its Next/Back
interaction without overflow. Three additional bounded headless testers—four
hotel sends, one flight send, and one ambiguous-money send—were still pending
at this checkpoint.

## V14 final headless UI outcomes

The v14 headless runs are separate from the earlier v13 failures and from
provider-only experiments. Four hotel retention checks passed through live
interpretation and first review, but the Valparaíso case still asked about
breakfast even though the customer had marked it optional. That is a real
coverage defect under repair for v15; it is not evidence of complete semantic
understanding.

The independent flight run captured all seven requested fields. A global “No
Preference” was left blank, while nonstop, cabin, and one-way remained
explicitly preserved. The `$295` matching offer passed; the `$280` connecting
offer was held and had no purchase control. The tester purchased the `$295`
offer, downloaded and reloaded the receipt, and observed zero exceptions. The
evidence files are `artifacts/v14-flight-uat-20261014/final-verification.json`
and `artifacts/v14-flight-uat-20261014/root-signature-verification.json`;
all eleven proof checks passed,
including configured issuer and merchant signatures, exact offer hash, and
approval digest. The saved JSON was 53,538 bytes. This verifies the synthetic
receipt path, not production payment accuracy or approval authority.
A later root verification reports fourteen checks all true, including signed
evidence, the VI chain, and native receipt verification; that remains
historical v14 evidence.

The independent ambiguous-money harness closed after a 6 ms loading-word
predicate while the draft was still initial; it never reached a proper
terminal state and is inconclusive. A separate persistent headless run sent
the same ambiguous request once and reached a terminal question after 21,094
ms: “Could you clarify what you are trying to achieve with ‘getting a certain
amount of money in Florida under $300’?” It produced zero typed fields, kept
four required fields open, held the unsupported goal, and did not assume a
flight or a `$300` budget. Its report and screenshot are
`artifacts/root-v14-ambiguous-ui/report.json` and
`artifacts/root-v14-ambiguous-ui/terminal.png`.

These root-run and independent-harness results must remain separate. At the
v14 checkpoint, the optional-breakfast repair and its prompt rule were pending
v15; the v15 outcome is recorded below. No claim of complete coverage or
production readiness follows from the v14 passes.

## V15 explicit optional-field repair

The v15 source is commit `f505c4c48203d3f8b4f881c639cc8c43db37aade`, READY as
deployment `dpl_GnMbCwaXUYxyyToc5w8oZQqLf4En`, using prompt
`intent-envelope-v15-explicit-optionals`. The local suite reports 542 pytest
passes. CI run `38610946939` is green: 542 pytest tests in 15.31 seconds,
ten browser suites in 16,566 ms, plus syntax and deadline checks. The public
URL is unchanged.

The backend optional-field compiler now treats explicit nonbinding language
such as “optional” or “can skip” as a reviewable `None` value with a sourced
declined criterion. It suppresses a repeated question without turning the
choice into `false` or AI consent; a later positive answer can override it.
“Cannot skip,” “can't skip,” and “not optional” remain binding and are never
dropped. Optional status cannot bleed into another positive field. The prompt
also recognizes nonbinding language. A missing required criterion may be null
only with the `needs_clarification` status; other null statuses remain invalid.

The final hotel run used two live sends: the exact original Valparaíso request
and its exact follow-up. Review retained the alternate dates, €120 nightly
amount, $900 total, balcony, 1 p.m. late checkout, quiet/walkable location, and
adult occupancy. It did not ask about breakfast again; review showed Breakfast
as `No Preference` with source “breakfast optional.” No hotel approval or
purchase occurred because unsupported conditions remained held. The report is
`artifacts/messy-hidden-v15-20261014/`.

A v15 flight run completed one live send. The UI matched all seven source
fields in nine of nine checks: the `$295` matching offer passed, while the
`$280` three-connection offer was held with no purchase control. The tester
completed the `$295` simulated purchase, downloaded and reloaded the receipt,
and observed zero exceptions. The first AI answer correctly said the nonstop
offer met the budget and the cheaper connecting offer did not meet the nonstop
requirement; the flow reached review without re-asking for airports. Its
evidence is `artifacts/v15-flight-uat-20261014/final-verification.json`.
Root signature verification reports 14/14 checks passed, including the
canonical digest, configured issuer and merchant signatures, VI chain, native
constraints, exact checkout and approved hash. Verified metadata preserved
`nonstop=true`, economy, one-way, simulated checkout, and the analyst boundary;
the signed evidence is 55,951 bytes in
`artifacts/v15-flight-uat-20261014/signed-evidence.json`.

A separate root headless v15 money run used one DOM send and reached a terminal
state after 15,053 ms. It produced zero typed
fields, assumed neither a flight nor a `$300` budget, and held the unsupported
goal. The assistant said it could only help with flight booking and could not
help obtain money in Florida, rather than asking a clarifying question. This
was a negative hold without an error or fallback, but it was not a helpful
clarification pass and shows usability variability against the v14 money run.
The report is `artifacts/root-v15-ambiguous-ui/report.json`.

The readback after four live v15 cases (two hotel, one flight, one money) shows
452 total stages and a 2,392-US-cent ($23.92) application reservation; that
reservation is not an Azure bill. The $30 reservation cap and separate 500-stage ceiling remain unchanged,
with 48 lifetime stages left: 24 full two-stage interpretations. At UTC 2026-10-15 the
daily counter was 4/200 and a fresh session allowed 24 stages. No manual
reset was performed.
The local time was still the evening of October 14. No additional AI calls
were expected from that readback. These limits and the negative money
usability result prevent a claim of complete cross-domain coverage or
production readiness.

## Persistent London acceptance

The final persistent headless London context completed exactly four live
sends. The full v10 run therefore consumed eight sends and sixteen model
stages: hotel initial plus clarification, two earlier harness-limited London
contexts, and this final four-send London run. The final report is
`artifacts/messy-hidden-v10-final-20261014/REPORT.md`, with structured evidence
in `london-final.json`.

The model asked for departure airports first and arrival airports second. The
tester selected `LHR`, `LGW`, and `LCY`, then `YTZ` and `YYZ`, using the actual
`Use 3 airports` and `Use 2 airports` controls. After the exact correction
“Actually, limit the departure airports to London Heathrow and London Gatwick
only,” both the live summary and first review showed `LHR`/`LGW` with no `LCY`.
The `YTZ`/`YYZ` set, November 12, 2026, nonstop, and `$299.99` remained
present. London was not asked again. No purchase was attempted.

This is a successful persistent UI correction path. The hotel clarification
retention issue remains under diagnosis, and these eight v10 sends do not
establish arbitrary-request accuracy, production readiness, or fewer disputes.

