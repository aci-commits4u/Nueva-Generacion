# Adaptive native UAT

This record covers a native, UI-only walkthrough of the deployed adaptive
conversation on build `019814b`. The tester used an isolated Chrome Incognito
session and chose the requests and follow-ups through the visible interface.
No API calls, browser fixtures, retries, offline fallback, or Explain action
were used during the five live submissions. All commerce data was synthetic.

## What was exercised

The walkthrough covered flight, hotel, and general requests. It included an
exact-date flight clarification, a supported one-way flight path, and requests
containing conditions outside the current deterministic validators.

The flight path reached the simulated purchase for receipt
`HPFXb2aHI9zhzFcJA3PqsA`. The matching offer was accepted with zero customer
exceptions. Hotel and general requests with unsupported conditions remained
held for review, as required by the trust boundary; they did not create
receipts.

The tester's interaction-level result was that the adaptive flow could carry
the request through clarification, review, signed offer comparison, and a
simulated purchase when the approved requirements were supported. The same
walkthrough also made the current limitation visible: a broad conversation
can preserve a condition that the current domain validator cannot enforce, but
it cannot turn that condition into a checkout rule without a reviewed profile
field, semantics, and trusted merchant fact.

The first run also found a material interpretation bug: a request using the
literal phrase “per night” was treated as a total budget. That is a real
failure in the adaptive path, even though the resulting signed evidence was
internally valid. The price-basis fix and a repeat native walkthrough are
required before this UAT can be called accepted.

The tester also reported confusion when unsupported round-trip and supported
one-way conditions appeared together in the preview, and a noticeable delay
while the next adaptive result was pending. These are usability and trust
issues to address in the repeat; they are not evidence that the model or
validator handled those conditions correctly.

## Earlier receipt verification

Root re-read the downloaded receipt/evidence rather than relying on the UI
label alone. The verified record had:

- the canonical evidence digest and configured issuer signature;
- the configured merchant signature and exact `offer_hash`;
- the exact `approved_digest` for the customer-approved revision;
- `native_vi_passed: true`;
- nine deterministic checks with status `PASS`;
- zero accepted exceptions; and
- `final_decision: "dispute analyst"`.

The actual downloaded file is preserved at
`/Users/victor/Downloads/intent-judge-evidence-HPFXb2aHI9zhzFcJA3PqsA.json`.
The receipt is evidence for this synthetic simulation, not proof of a real
payment, Mastercard certification, legal liability, or chargeback outcome.

## Evidence boundary and limitations

The tester inspected screenshots during the native session, but native CUA
screenshots were not successfully persisted as repository artifacts. A
separate public read-only CLI pass did persist three 390px screenshots without
POST requests: `artifacts/adaptive-production-overview.png`,
`artifacts/adaptive-production-tutorial.png`, and
`artifacts/adaptive-production-quality-mobile.png`. These are visual release
checks, not native-session screenshots.

## Literal native transcript

The tester's five-step transcript and exact clarification exchange were:

1. “I need a round-trip flight from Newark (EWR) to Lisbon (LIS) for a
   five-day conference trip in early November. I must arrive before 3 p.m.,
   prefer nonstop but accept one stop, keep the total under $900, and return
   after 6 p.m. If two options meet those rules, show me both.” The model then
   asked: “Could you tell me the exact departure and return dates for your
   five-day conference trip in early November?”
2. The tester selected the inclusive range November 2–8, 2026, recorded as
   “Travel between 2026-11-02 and 2026-11-08, inclusive.”
3. “Find me a one-way nonstop economy flight from EWR to LIS on November 2,
   2026, under $900.”
4. “I need a quiet hotel in Boston for November 2–4, 2026, under $220 per
   night, near public transit, and I need the front desk to hold a refrigerated
   medication pack. Please keep the room on hold while I confirm that storage.”
5. “I need a quiet portable field recorder for urban sound research under
   $300, with 24-bit recording, weather resistance, and USB-C so I can use it
   with an iPhone. Keep two options if both meet those requirements.”

The round-trip prompt and later one-way prompt intentionally expose the
preview distinction. The hotel prompt contains the per-night budget and
unsupported storage condition. The field-recorder prompt exercises general
criteria that the current checkout validator cannot fully enforce.

The **New request** control intentionally starts a new anonymous session. It
therefore makes the previous session URL inaccessible from that flow. The
tester did not reload the receipt before the session boundary, so receipt
continuity was verified from the downloaded signed JSON, not from a reload in
the same native walkthrough.

Five live submissions are a narrow UAT sample. They do not establish general
intent accuracy, reliable behavior for arbitrary domains, merchant adoption,
or production payment readiness. The hotel and general holds are expected
fail-closed behavior, but they also show that generic conversation support is
broader than the current validator coverage.

The raw adaptive experiment remains separate from this UAT. The first three
fresh live adaptive cases still score 1/3 in
`evals/experiments/adaptive-first-live-20261014.json`; this UAT does not rewrite
that artifact or convert the result into an accuracy claim.

## Native repeat on `b2141d7`

The native repeat completed three paid submissions with no automatic retry,
Explain call, or offline fallback. It used the exact original nightly hotel
request, the literal follow-up below, and the exact one-way flight request.

1. The nightly hotel request produced a useful all-in-stay budget question.
   Both November 2–4 dates remained present, and the draft did not invent a
   `$219.99 total` value.
2. The exact reply was: “For the two-night stay from November 2 through
   November 4, use a $440 all-in cap (44,000 cents) while preserving the
   original under-$220-per-night limit.” The draft captured Boston, November
   2–4, the `$440` total, and the original nightly, quiet, transit, storage,
   and room-hold conditions. The storage and hold conditions remained
   unsupported. The `$295` offer was held by the backend gate on integrity and
   unsupported non-waivable conditions.
3. “Find me a one-way nonstop economy flight from EWR to LIS on November 2,
   2026, under $900.” The adaptive plan reached `ready` directly. The `$295`
   offer passed with zero exceptions, a simulated receipt was created, and a
   native reload restored that receipt. Evidence was downloaded to
   `/Users/victor/Downloads/intent-judge-evidence-m7kkaBC8ndkTRWOGijCb6A.json`.

The public repeat URL was
`https://intent-judge-perfected.vercel.app/?intent=zxTQewt6Qq07JMY6v5Ds6g`.
Root subsequently completed the independent cryptographic readback of the new
receipt, as recorded below. The UI confirmation was not substituted for
signature verification.

## Verification status

Runtime source `b2141d7` was covered by green CI run `38527808000` with 428
pytest tests and nine browser checks. Fresh v7 adaptive evaluation
`evals/experiments/adaptive-nightly-final-live-20261014.json` passed its one
observed-case hotel regression with two Foundry stages and no retry. The
benchmark retains its legacy `holdout` split label, but this was a known UAT
counterexample; it is not an unseen accuracy evaluation. The preceding v6
diagnostic `evals/experiments/adaptive-nightly-diagnostic-live-20261014.json`
retains its 0/1 failure; the earlier 8/8 v5 result remains historical in
`evals/experiments/adaptive-final-live-20261014.json`.

The final native receipt passed the independent Root cryptographic
readback below. This document records a successful UI repeat, not complete accuracy,
production payment readiness, or a liability guarantee.


## Final independent evidence readback

Root re-read `intent-judge-evidence-m7kkaBC8ndkTRWOGijCb6A.json` after the
native repeat. The canonical digest, configured issuer signature, configured
merchant signature, exact offer hash, approved-requirements digest, and
`native_vi_passed` all passed. All nine checks were `pass`; there were zero
exceptions and `final_decision` remained `dispute analyst`. No additional
inference was used for these checks. The runtime is READY and its source CI
passed; the final native repeat is accepted within the documented synthetic
demo scope.
