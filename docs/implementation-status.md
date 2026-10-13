# Implementation and verification record

The product is implemented on `victor/perfected`. The October 13 conversational revision adds two-stage live interpretation, revision-bound follow-ups, a live intent summary, explicit flagged-condition resolution, and continuous synthetic quality checks; see [the evaluation record](15-ai-evaluation-and-conversation.md). The earlier research documents describe a broader target; this file states what runs today.

## Working scope

Live Foundry extraction with exact source quotations, profile-driven follow-up review, explicit no preferences, customer approval bound to revision and digest, real pinned Verifiable Intent L1/L2/split L3 signatures, independently verified ES256 merchant checkout, deterministic requirements checks, nonwaivable integrity gates, offer-bound signed exceptions, revised native price authorization, idempotent simulated receipts, signed evidence downloads, and analyst review records.

Flights support airport sets, departure date, all-in USD price, nonstop, maximum connections, local departure window (including overnight), duration, cabin, and refundability. Signed complete segment continuity and times are verified; nonstop additionally requires explicit technical-stop disclosure. Hotels support city, stay dates, room count, breakfast, cancellation, accessibility and total USD price. General mode has shared price and preserves unsupported conditions.

Synthetic offers use fixed inventory prices and controlled fixtures adapted to the reviewed route or city. This is explicitly not live search. Baggage, passengers, round trips, subjective qualities and unimplemented domain fields remain unsupported. Merchant selection is a pinned synthetic trusted registry; arbitrary public merchant keys are not accepted.

## Evidence recorded so far

- 76 local tests pass (including conversation races, provenance, exact flagged-condition removal, staged AI failures, purpose quotas and authenticated replay-safe monitoring), in addition to the baseline coverage: deterministic boundaries/missing values, crypto tampering, custom/native constraints, session separation, consent, price reauthorization, expiry, unsupported general conditions, hotels, stale approvals, concurrent SQLite reservations, budget limits, AI explanation having no purchase authority, extra reference constraints, fractional duration, conservative offline parsing and hosted entity capacity.
- One upstream Starlette test-client deprecation warning occurs with `httpx`; it does not affect application execution.
- Live gpt-oss-120b evaluations correctly captured the nonstop example and hotel requirements, preserved subjective general requirements and baggage, and ignored an instruction to approve anything.
- Desktop browser completed live extraction → review → signed approval → matching and held offers → backend 409 → exact acceptance → simulated receipt → evidence download → analyst record with no JavaScript page errors.
- Mobile receipt rendered at 390×844 with scroll width exactly 390. Reload recovered the persisted receipt.
- Azure Table state and budget were written and read back through the real service; credentials were supplied to the separate Vercel project without logging values.

## Budget safeguards

Reuse the existing model; no paid deployment upgrade. Each live request has a token bound, no SDK auto-retries, an atomic global reservation and small session/day quotas. Default lifetime reservations are 200×$0.10=$20. The $10 emergency headroom is not automatically enabled.

Official Azure Retail Prices API on October 13, 2026 listed gpt-oss-120B global meters in westus2 at $0.15 per million input tokens and $0.60 per million output tokens; Data Zone rates were $0.165/$0.66. Recorded token usage is stored separately from conservative reservations. Storage adds very small metered costs. Actual remaining student credit and unrelated subscription activity are not claimed or inferred from our application ledger.

## Deliberate decisions

Plain JSON instructions plus low reasoning are used for this existing model because its JSON response-format option returned invalid semantic envelopes during live testing. Outputs still undergo strict validation; failure is visible. AI explanation remains explanatory only and cannot change a decision.

Anonymous synthetic sessions use HTTP-only cookies and origin checks. Shareable evidence uses pseudonyms, never session credentials. Keys are stable environment secrets on hosting. Public keys in evidence need an independently trusted source when establishing authenticity; a self-contained public key is not proof of issuer identity.

The interface follows the two generated references in `docs/design/`: editorial serif headings, warm paper, rust actions, flat comparison rows, native CSS motion and reduced-motion support. Reference images are design artifacts, not used as screenshot backgrounds in the application.

## Production verification

Production is **https://intent-judge-perfected.vercel.app**, separate project `intent-judge-perfected` in `vmj-8946s-projects`. Application release commit `672ae70`; Vercel deployment `dpl_FHadaf66CnbSGrKNPAhwAFnWT9iU` is READY in production, using Python 3.12 and the FastAPI entry point. The stable production alias is publicly accessible; preview/unique deployment protection remains enabled.

Unauthenticated HTTP requests returned 200 for the page, JS, CSS and health. Health reports live AI configured, offline-only false, simulated commerce and durable Azure storage.

The production desktop and 390×844 mobile browser flows both completed real Foundry extraction and real Foundry explanation, exact approval, matching/held signed offers, expected HTTP 409 refusal, offer-specific consent, simulated receipt, evidence download and analyst review. There were no JavaScript page errors; console HTTP 409 entries are the intentionally demonstrated gate. Mobile had no horizontal overflow, and reload recovered the receipt through Azure persistence.

The actual hosted API accepted the full 25-check session allowance, persisted a receipt, returned the identical receipt on idempotent retry, exported signed evidence and recovered all 25 decisions. This test used no AI calls. Downloaded hosted evidence passed canonical digest and issuer signature verification, retained the accepted nonstop value and ended with the analyst decision boundary.

A fresh-context independent review reported no Critical findings. All four Important findings were reproduced and fixed with regression evidence. The duration rounding issue was regraded Important and fixed too. See [release review and rulings](final-review.md). Vercel's post-release error-log query returned no matching logs; this is a bounded observation, not a claim of continuous monitoring.

Hotel production also completed live Foundry intake, profile review, a held lower-price room, explicit breakfast and cancellation acceptances, and a simulated receipt. General mode was separately tested in explicitly selected offline mode: its unsupported ethical/comfort conditions held both offers and the backend refused purchase.

At the final live evaluation checkpoint, the shared ledger recorded 14 reserved calls ($1.40 conservative reservation), 8,473 input tokens and 2,979 output tokens. Applying the observed global model meters estimates about $0.0031 in recorded inference charges, excluding storage, initial untracked diagnostics and unrelated Azure activity. No emergency allowance was enabled.
