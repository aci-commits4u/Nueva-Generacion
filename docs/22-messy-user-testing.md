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

## Repair direction and limits

The planned repair adds general planner rejection feedback to the second
Foundry role and emits sanitized diagnostic codes. It keeps the fail-closed
behavior: no static fallback question or alias guess will be used. Frontend
guidance is being revised to use dollar examples without inventing dates, and
the adaptive prompt version is `v10-planner-repair-feedback`.

Tests, deployment, and a fresh native retest of these messy cases are pending.
The flight recovery is evidence that the UI can preserve messy constraints
after a delayed response; the hotel result shows that the shared planner can
still stop without asking the most useful question. These five sends do not
establish arbitrary-request accuracy, production readiness, or fewer disputes.

