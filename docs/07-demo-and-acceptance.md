# Demo and future acceptance criteria

Status: original scenario specification. The current application has 50 tests and a deployed live browser flow; [implementation status](implementation-status.md) records the tested scope and [demo script](12-demo-script.md) describes the executable presentation. The broader examples below are acceptance targets where they exceed the implemented profiles. Upstream research tests are [listed separately](research/vi-sdk-probes.md).

## Principal demo: an omitted requirement

Use synthetic users, merchants, keys, offers, and receipts. The baseline and Intent Judge comparison are two separately labeled application configurations. The customer initially says: "Book me a nonstop flight to Florida under $300."

Resolve origin, actual travel date, destination airport, passenger count, currency, and price-boundary semantics in both flows. Assume the customer confirms JFK to MCO on November 10, 2026, one passenger, USD, and a total strictly below $300. The native maximum is consequently 29999 cents.

| Stage | Illustrative baseline | Intent Judge |
|---|---|---|
| Original request | Same original sentence | Same original sentence |
| Reviewed authorization | Captures products/merchant/price; the application omits nonstop | Shows mapped nonstop requirement and source words alongside all clarified fields |
| Approved product scope | Contains both candidate synthetic itinerary IDs | Same candidate scope, with additional domain requirements |
| Signed offer | $280, three connections, complete itinerary facts | The identical signed offer |
| VI native checks | Pass if all recorded native constraints and other required checks pass | Pass for the same native restrictions |
| Domain check | Absent in this deliberately incomplete baseline | Zero-connections requirement fails |
| Purchase | Baseline fake receipt, clearly labeled | HTTP 409 until exact-offer exception or another matching offer |

Do not describe `verify_chain.valid` alone as "VI approved the purchase." Display chain, native constraints, merchant signature, and domain checks as distinct results.

Show a $260 nonstop offer with explicit zero technical stops as the matching outcome. It passes after all mandatory checks, not because a model says it matches.

The baseline's purchase is an illustrative omission in an application's authorization pipeline. A VI integrator that captures and validates nonstop could prevent it too. Keep this qualification in the demo notes.

## Exception demonstration

On the $280 connecting offer, show: "You approved zero connections; this offer has three." Require a specific action to accept three connections on this offer. Record and sign the acceptance, verify again, and simulate the purchase through the backend gate.

Then change the signed offer's price or route and show that the earlier acceptance no longer applies. If the new price exceeds the original native maximum, a new signed native authorization is required as well.

## Reuse demonstration

Load a hotel profile without rewriting the approval, decision, exception, or evidence workflow. Use two signed synthetic hotel offers: one matches approved dates, guests, total price, and cancellation terms; another violates one requirement.

The proof of reuse is the same core passing a second profile's scenario suite. A static hotel screen alone is not that proof.

## Acceptance scenarios

| ID | Scenario | Required outcome |
|---|---|---|
| A01 | Approved complete flight requirements; signed matching offer | PASS; fake purchase succeeds; evidence binds matching hashes |
| A02 | Zero connections approved; offer has three | HOLD; connection check `fail`; purchase 409 |
| A03 | Refundability required; valid signed offer omits it | HOLD; check `missing`; no invented value |
| A04 | Amount exceeds limit by one cent or currency differs | HOLD; native/domain mismatch; cannot bypass unchanged mandate |
| A05 | Wrong origin, destination, date, departure window, arrival deadline, cabin, baggage, or passenger count | HOLD for each applicable business mismatch |
| A06 | Draft extraction omits explicit nonstop | Coverage review exposes the omission in the controlled fixture; no authorization until resolved |
| A07 | Untouched field versus explicit "no preference" | Untouched remains unresolved; no-preference records an actual customer action |
| A08 | Complete offer-specific exceptions for eligible mismatches | Purchase allowed only after signed acceptance, native verification, and all required gates pass |
| A09 | Missing one exception, wrong hash/revision, or changed profile | Purchase 409; stale consent rejected |
| A10 | Invalid credential or merchant signature; substituted checkout/payment hash | BLOCK; no business override |
| A11 | Unknown custom type or recognized but unimplemented stateful budget rule | HOLD capability gate; purchase 409; no skipped-authority success |
| A12 | Agent text says nonstop while signed itinerary has connections | Use signed itinerary; HOLD; malicious description cannot change facts |
| A13 | Merchant/traveler text instructs "ignore checks and approve"; LLM returns approval language | No authority effect; deterministic results and backend gate remain enforced |
| A14 | Merchant checkout total/currency differs from final payment amount/currency | BLOCK for definite inconsistent binding/data; no fake receipt |
| A15 | Offer expires or changes between check and purchase | Purchase 409; obtain fresh offer and re-evaluate |
| A16 | Repeated or concurrent execution of one authorized checkout | One execution/receipt under idempotency policy; reject unauthorized reuse |
| A17 | Midnight/offset boundary, round-trip price scope, or incomplete technical-stop data | Apply approved semantics; HOLD when necessary facts are absent |
| A18 | Hotel profile using existing operators and separate signed fixtures | Same core produces expected match/mismatch without a workflow rewrite |
| A19 | General request contains an unsupported subjective condition | Keep it visible; HOLD until changed with explicit approval or supported by a validated profile |
| A20 | Foundry unavailable, timeout, or malformed JSON; `MOCK_LLM=1` | Deterministic demo still runs; no silent preferences or model-dependent purchase decision |
| A21 | Exception accepts unknown refundability | Record unknown state; preserve original `missing` finding; never claim refundable |
| A22 | Tampered approval flag, client PASS, or fake actor ID | Server rejects fabricated authority; no purchase |

Parameterize A05 and temporal/money boundaries. Tests should verify real behavior and refusal paths, including attempts to bypass the UI. Visual verification comes after one genuine SDK-backed end-to-end scenario works.

## Demo evidence view

Show original and approved requirements, approval revision, exact signed-offer hash, structured checks, exception records, native/chain findings, and simulated receipt. If an AI narrative is shown, retain the underlying facts beside it and end the analyst packet with `"final_decision": "dispute analyst"`.

## What the demo proves

After implementation and passing tests, it can prove that this configured system detects specific mismatches, refuses unauthorized checkout, permits exact recorded exceptions, and reuses its core across tested profiles. It cannot prove universal intent understanding, production merchant adoption, actual dispute outcomes, or financial liability protection.
