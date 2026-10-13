# Implementation and verification record

The product is implemented on `victor/perfected`. The earlier research documents describe a broader target; this file states what runs today.

## Working scope

Live Foundry extraction with exact source quotations, profile-driven follow-up review, explicit no preferences, customer approval bound to revision and digest, real pinned Verifiable Intent L1/L2/split L3 signatures, independently verified ES256 merchant checkout, deterministic requirements checks, nonwaivable integrity gates, offer-bound signed exceptions, revised native price authorization, idempotent simulated receipts, signed evidence downloads, and analyst review records.

Flights support airport sets, departure date, all-in USD price, nonstop, maximum connections, local departure window (including overnight), duration, cabin, and refundability. Signed complete segment continuity and times are verified; nonstop additionally requires explicit technical-stop disclosure. Hotels support city, stay dates, room count, breakfast, cancellation, accessibility and total USD price. General mode has shared price and preserves unsupported conditions.

Synthetic offers use fixed inventory prices and controlled fixtures adapted to the reviewed route or city. This is explicitly not live search. Baggage, passengers, round trips, subjective qualities and unimplemented domain fields remain unsupported. Merchant selection is a pinned synthetic trusted registry; arbitrary public merchant keys are not accepted.

## Evidence recorded so far

- 42 local tests pass: deterministic boundaries/missing values, crypto tampering, custom/native constraints, session separation, consent, price reauthorization, expiry, unsupported general conditions, hotels, stale approvals, concurrent SQLite reservations, budget limits, and AI explanation having no purchase authority.
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

## Pending final verification

Deployment build, public production routing, hosted live browser flow, and fresh-context whole-branch review are recorded below when actually completed.
