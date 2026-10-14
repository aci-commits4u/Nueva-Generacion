# Route-choice reliability

This record captures a real native UI failure reported on October 14, 2026.
It is separate from the earlier successful EWR→LIS walkthrough because that
walkthrough did not exercise ambiguous global city routing.

## Reproduction

The customer entered:

> Book me a nonstop flight from london to toronto on 2026-11-12 under $300.

The route chooser then mixed role selections. The origin side contained
London, GB alongside Toronto-area airport codes `YYZ` and `YTZ`; the arrival
side contained London, GB alongside Toronto selections. The system retained
both sets, but the model asked for London again three times and incorrectly
described the requirement as “single airport required.”

The report is backed by the user screenshot at
`artifacts/route-loop-user-reported.png`. The shared interactive quota then
reached its 80-stage limit, so no additional paid model run was available to
continue the native investigation. This was a product failure, and the prior
“finished” assessment was premature.

## Why the earlier pass did not cover this

The prior native EWR→LIS result proved one supported route through review,
merchant checks, simulated purchase, and receipt reload. It did not prove
that a global ambiguous city can be resolved without cross-wiring origin and
destination candidates. Backend tests and the earlier route use are therefore
separate evidence from this user-driven failure.

## Scoped implementation response

The route-choice changes now in the working tree include:

- the pinned global `airportsdata` catalogue with role-scoped origin and
  destination candidates;
- country and region qualifiers from `pycountry==26.2.16`, so phrases such as
  London, Ontario and Paris, France → Rome, Italy are resolved using their
  qualifiers instead of a dominant-US count;
- the Maine pronoun “me” injection fix;
- Toronto metro expansion to Pearson (`YYZ`) and `YTZ`;
- a structured choice contract with `question_id`, `field`, and canonical
  `values`, validated before reserving a model stage;
- preservation of every selected airport set before and after review, with no
  forced single-airport reduction; and
- one useful model question per turn, with role feedback supplied when a
  mixed origin/arrival question is rejected on the next pass.

The UI removes static EWR/MCO defaults, displays the active question once, and
labels later updates against the correct origin or destination role. These
changes address the observed loop; they do not yet prove arbitrary global
route interpretation.

## Budget and verification boundary

The shared ledger history was not reset. Production environment upserts and
the local environment now configure a 200-stage daily quota, 24 stages per
session, and a 1,000-cent ($10) emergency allowance inside the combined $30
authorization representing the original $20 ordinary plus $10 emergency
allowance. The unchanged lifetime ceiling is 500 stages. These settings are
not active on the public URL until a new deployment reports READY. The staged
follow-up cap is 11, allowing one initial request plus eleven staged requests
within the 24-stage session limit. These settings protect the remaining
budget; they are not evidence of actual Azure credit balance.

## Local live integration evidence

Root's local live Foundry integration artifact
`artifacts/route-choice-live-integration.json` exercised the exact original
London-to-Toronto request and two staged structured choices: `LCY`/`LHR` for
origin and `YYZ`/`YTZ` for destination. Across three paid turns and six model
stages it passed with the complete airport sets, maximum price `29999` cents,
November 12, 2026, and `nonstop: true`; London was not asked again.

This is local provider integration evidence, not an independent native
production UAT. The new route browser suite uses intercepted UI responses and
therefore is not live-AI evidence. The independent native production retest
of the original route remains pending.

## Follow-up fixes and guards

Independent review found and fixed two more geographic failure classes:

- a city-only model output could select `LHR`/`YYZ`, or all airport codes for
  a city, without a customer choice; it now remains ambiguous until the
  customer selects the airport set; and
- reversed “to Toronto from London,” bare depart/arrive wording, and
  leaving/arriving arrow order could cross-wire route roles; role scoping now
  preserves the direction expressed by the customer.

State guards now mark a legacy question/plan mismatch as
`clarification_current: false` through a read-only GET. An explicit refresh
reinterprets the full saved history and revokes prior approval. A completed
receipt remains immutable. New tests also protect an empty question list from
binding a reply to a stale planner question.

The final offline pytest count moved from 473 to 478 passing tests. JavaScript
syntax, the clean-diff check, and the 90-second API deadline check pass without
automatic retry. All ten browser flows pass in 18,767 ms against a local
offline server: the first six use explicit offline mode, and the final four
use intercepted fixtures. This is regression evidence, not ten live-AI
journeys.

The source commit and deployment of these fixes are next; blind native
production UAT remains pending. Existing tests, local integration, and the
earlier EWR→LIS walkthrough must not be reported as proof that the public
native route is fixed. No release or complete-accuracy claim is made until a
fresh native retest covers the exact route, preserves both airport sets, and
demonstrates that London is not asked repeatedly.

