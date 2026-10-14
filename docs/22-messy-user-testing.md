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
third model call or automatic retry. The v12 deployment and UAT are pending.

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

