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
budget; they are not evidence of actual Azure credit balance. The v9 deployment
recorded below is READY, so its public environment is the first current
deployment after these upserts.

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
of the original route is recorded below; its new receipt readback remains
pending.

## Blind native retest on v8

Source `cab3888dd3e919eebee1500c42b282efc88212f9` deployed READY as
`dpl_8jgXnKtet1MvvRrcUvyHBNr6eQrmCI` after CI run `38586292355` reported 478
pytest tests and ten browser flows. The independent blind native retest still
failed after four live turns. It used no retry, fallback, or Explain action.

The tester entered the exact London-to-Toronto request. The model asked,
“Which airport would you like to depart from in London?” The tester selected
the genuine UK options `LHR`, `LGW`, and `LCY`. The next question correctly
asked, “Which airport would you like to arrive at in Toronto?” and the tester
selected both `YTZ` and `YYZ`. The complete route then held November 12,
nonstop, and `29999` cents with no airport loop.

The tester next entered: “Actually, limit the departure airports to London
Heathrow and London Gatwick only.” The natural-language correction updated the
generic live criteria to `LHR`/`LGW`, but the unapproved typed summary and
review origin still contained `LHR`, `LGW`, and `LCY`. The tester stopped before
approval and before the second test case.

The failed native session is preserved at
`https://intent-judge-perfected.vercel.app/?intent=qgaDKDrg2tz0rghU4AEABQ`.
The tester opened Review only after entering the correction, so this was
backend typed-state propagation, not a cached sidebar edit.

The two primary causes were fixed in the working tree: the old widget set was
reapplied after a later customer correction, and named departure airports
containing “to” were misread as a destination. Additional review found paired
named assignments mixing endpoint roles and a wrong-field clarification
reopening the opposite endpoint. Scoped operators, endpoint bounds, and a
target-role guard now address those paths. The deployed v8 release is still
not accepted; native UAT will be retaken only after the hotfix is READY.

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
binding a reply to a stale planner question. The version guard marks known
older live trace prompt versions stale for explicit refresh, with
`v9-customer-corrections` preventing persisted v8 state from appearing current.

The final offline pytest count moved from 473 to 488 passing tests. JavaScript
syntax, the clean-diff check, and the 90-second API deadline check pass without
automatic retry. All ten browser flows pass in 20,478 ms against a local
offline server, including fixture coverage for correction and sidebar/review
consistency. This remains regression evidence, not ten live-AI journeys.

The v8 checkpoint ended with the merge-precedence hotfix deployment pending;
the v9 deployment and native observation are recorded below. Existing tests,
local integration, the initial v8 no-loop path, and the earlier EWR→LIS
walkthrough remain separate evidence from the native result.

## Observed native hotfix acceptance on v9

The hotfix source `483cec80b3fcb3d7e42a1c2d674a8fed80f52e81` is READY as
`dpl_MbrTKqjci751XHEJR1tZBXeBfAGj`, with CI run `38589183389` passing 490
pytest tests and ten browser flows. A fresh blind native session completed
five live sends across two independent paths, with no retry, offline fallback,
or Explain action.

For the exact London→Toronto request, the model asked “Which London airport
would you like to depart from?” and then “Which Toronto airport would you like
to arrive at?” The tester selected `LHR`, `LGW`, and `LCY`, then `YTZ` and
`YYZ`. After the same natural-language correction limiting departure to
Heathrow and Gatwick, both the live summary and first review showed only
`LHR`/`LGW`; London was not asked again and the other captured conditions were
retained.

The independent request was:

> Book me a nonstop one-way economy flight from Singapore Changi Airport (SIN) to Tokyo Haneda Airport (HND) on 2026-12-05 under $300.

One live send captured the correct fields. The `$295` matching offer passed to
a simulated purchase, while the `$280` offer with three connections held.
There were zero accepted differences, and a native receipt reload restored the
receipt. The final intent URL was
`https://intent-judge-perfected.vercel.app/?intent=k_or8c60l3WlT8Un8Fc8UA`.

Chrome's native Save to Downloads completed with generated filename
`intent-judge-evidence-mAzdjRLm1ssaJrZO4oHjeg.json`; Recent Download History
reported 51.2 KB. Root verified the 52,417-byte file and recorded the result
in `artifacts/route-native-evidence-verification.json`: canonical digest,
configured trusted issuer and merchant signatures, exact offer hash and
approval digest, `native_vi_passed: true`, nine passing checks, zero
exceptions, and `final_decision: "dispute analyst"`. The approved fields were
SIN→HND, December 5, 2026, maximum `29999` cents, nonstop, economy, and
one-way; the simulated purchase amount was `29500` cents and metadata reports
v9.

An earlier manually named evidence-file save failed with an insufficient
permissions error at the native save destination. The generated Downloads
filename above succeeded and is the verified artifact. A ScreenCaptureKit
observation tool returned an error while the receipt was being inspected;
accessibility state still verified the receipt, and the tool error was not an
application failure.

This verifies the synthetic v9 one-way purchase path. The v8 failure, local
integration artifact, intercepted browser flows, and v9 native route correction
remain separate evidence classes; this receipt does not establish complete
accuracy or production payment readiness.

A separate blind agent is now running two self-chosen flight and hotel
requests through the actual UI in headless mode, with at most six new live
sends and no source access, API calls, mocks, or fallback. Those results are
pending and are not counted as passed cases here.

