# Implementation and verification record

The product is implemented on `victor/perfected`. The current public release adds an overview that explains the pitch, a five-step tutorial, and help throughout the working demo; see [the walkthrough guide](16-product-walkthrough.md). The underlying conversational revision adds two-stage live interpretation, revision-bound follow-ups, a live intent summary, explicit flagged-condition resolution, and continuous synthetic quality checks; see [the evaluation record](15-ai-evaluation-and-conversation.md). The earlier research documents describe a broader target; this file states what runs today.

## Earlier UI release — October 13 (historical)

Source `1a2cdf8` is deployed as `dpl_EMi2YA2LF9EjJh719WoGcvcj56Kc`, READY at **https://intent-judge-perfected.vercel.app**. The stable alias is public. [Source CI run 38471659344](https://github.com/aci-commits4u/Nueva-Generacion/actions/runs/38471659344) passed; local regression remains 76 passing tests with one upstream deprecation warning.

All six browser suites passed against both local development and the actual public deployment: overview/tutorial, delayed new-request reset, flight enforcement and exact exception, mobile hotel purchase/evidence, navigation and preserved review edits, and clarification/approval/purchase completion during tutorial navigation. The five-step tutorial made zero POST requests. The working-flow tests explicitly selected offline interpretation; no paid Foundry calls were made for this UI release. Live mode remains the default and health reports live AI configured, offline-only false, simulated commerce, and Azure storage. This verification does not claim another live model evaluation.

Desktop and 390px mobile layouts were rendered and inspected. The mobile suite also checked keyboard focus, dialog Escape, evidence download and Quality reload. Public HTML, CSS, JavaScript modules, font and health returned HTTP 200. The daily 07:00 UTC quality cron is enabled and points to this deployment. Backend rules, signed approvals, merchant trust and AI budget limits are unchanged.

Independent review reproduced and resolved navigation races, lost unsaved review edits, stale draft revisions after tutorial return and the slow session-reset boundary. Final review found no remaining Critical, Important or Minor issues; see [review evidence](final-review-ui.md) and [build ledger](ui-build-ledger.md).

## Working scope

Live Foundry extraction with exact source quotations, profile-driven follow-up review, explicit no preferences, customer approval bound to revision and digest, real pinned Verifiable Intent L1/L2/split L3 signatures, independently verified ES256 merchant checkout, deterministic requirements checks, nonwaivable integrity gates, offer-bound signed exceptions, revised native price authorization, idempotent simulated receipts, signed evidence downloads, and analyst review records.

Flights support airport sets, departure date, all-in USD price, nonstop, maximum connections, local departure window (including overnight), duration, cabin, refundability and explicitly signed one-way trips. Signed complete segment continuity and times are verified; nonstop additionally requires explicit technical-stop disclosure. Hotels support city, stay dates, room count, adult count against signed capacity, breakfast, cancellation, accessibility and total USD price. General mode has shared price and preserves unsupported conditions.

Synthetic offers use fixed inventory prices and controlled fixtures adapted to the reviewed route or city. This is explicitly not live search. Baggage, passengers, round trips, subjective qualities and unimplemented domain fields remain unsupported. Merchant selection is a pinned synthetic trusted registry; arbitrary public merchant keys are not accepted.

## Evidence recorded so far

- 76 local tests pass (including conversation races, provenance, exact flagged-condition removal, staged AI failures, purpose quotas and authenticated replay-safe monitoring), in addition to the baseline coverage: deterministic boundaries/missing values, crypto tampering, custom/native constraints, session separation, consent, price reauthorization, expiry, unsupported general conditions, hotels, stale approvals, concurrent SQLite reservations, budget limits, AI explanation having no purchase authority, extra reference constraints, fractional duration, conservative offline parsing and hosted entity capacity.
- One upstream Starlette test-client deprecation warning occurs with `httpx`; it does not affect application execution.
- Live gpt-oss-120b evaluations correctly captured the nonstop example and hotel requirements, preserved subjective general requirements and baggage, and ignored an instruction to approve anything.
- Desktop browser completed live extraction → review → signed approval → matching and held offers → backend 409 → exact acceptance → simulated receipt → evidence download → analyst record with no JavaScript page errors.
- Mobile receipt rendered at 390×844 with scroll width exactly 390. Reload recovered the persisted receipt.
- Azure Table state and budget were written and read back through the real service; credentials were supplied to the separate Vercel project without logging values.

## Budget safeguards

Reuse the existing model; no paid deployment upgrade. Each live request has a token bound, no SDK auto-retries, an atomic global reservation and small session/day quotas. The ordinary money cap is $20, enforced atomically and independently from a 500-stage ceiling. Past $0.10 reservations are retained; future bounded stages reserve $0.02 each. No counter or past money was reset. The $10 emergency reserve is disabled.

Official Azure Retail Prices API on October 13, 2026 listed gpt-oss-120B global meters in westus2 at $0.15 per million input tokens and $0.60 per million output tokens; Data Zone rates were $0.165/$0.66. Recorded token usage is stored separately from conservative reservations. Storage adds very small metered costs. Actual remaining student credit and unrelated subscription activity are not claimed or inferred from our application ledger.

## Deliberate decisions

Plain JSON instructions plus low reasoning are used for this existing model because its JSON response-format option returned invalid semantic envelopes during live testing. Outputs still undergo strict validation; failure is visible. AI explanation remains explanatory only and cannot change a decision.

Anonymous synthetic sessions use HTTP-only cookies and origin checks. Shareable evidence uses pseudonyms, never session credentials. Keys are stable environment secrets on hosting. Public keys in evidence need an independently trusted source when establishing authenticity; a self-contained public key is not proof of issuer identity.

The current interface follows the product overview and walkthrough references in `docs/design/`: large Geist Sans typography, warm white, forest ink, lime matches, amber holds, flat comparison rows, native CSS motion and reduced-motion support. Earlier serif/rust and sidebar references are historical. Reference images are design artifacts, not used as screenshot backgrounds in the application.

## Original production verification (historical)

Production is **https://intent-judge-perfected.vercel.app**, separate project `intent-judge-perfected` in `vmj-8946s-projects`. Application release commit `672ae70`; Vercel deployment `dpl_FHadaf66CnbSGrKNPAhwAFnWT9iU` is READY in production, using Python 3.12 and the FastAPI entry point. The stable production alias is publicly accessible; preview/unique deployment protection remains enabled.

Unauthenticated HTTP requests returned 200 for the page, JS, CSS and health. Health reports live AI configured, offline-only false, simulated commerce and durable Azure storage.

The production desktop and 390×844 mobile browser flows both completed real Foundry extraction and real Foundry explanation, exact approval, matching/held signed offers, expected HTTP 409 refusal, offer-specific consent, simulated receipt, evidence download and analyst review. There were no JavaScript page errors; console HTTP 409 entries are the intentionally demonstrated gate. Mobile had no horizontal overflow, and reload recovered the receipt through Azure persistence.

The actual hosted API accepted the full 25-check session allowance, persisted a receipt, returned the identical receipt on idempotent retry, exported signed evidence and recovered all 25 decisions. This test used no AI calls. Downloaded hosted evidence passed canonical digest and issuer signature verification, retained the accepted nonstop value and ended with the analyst decision boundary.

A fresh-context independent review reported no Critical findings. All four Important findings were reproduced and fixed with regression evidence. The duration rounding issue was regraded Important and fixed too. See [release review and rulings](final-review.md). Vercel's post-release error-log query returned no matching logs; this is a bounded observation, not a claim of continuous monitoring.

Hotel production also completed live Foundry intake, profile review, a held lower-price room, explicit breakfast and cancellation acceptances, and a simulated receipt. General mode was separately tested in explicitly selected offline mode: its unsupported ethical/comfort conditions held both offers and the backend refused purchase.

At the final live evaluation checkpoint, the shared ledger recorded 14 reserved calls ($1.40 conservative reservation), 8,473 input tokens and 2,979 output tokens. Applying the observed global model meters estimates about $0.0031 in recorded inference charges, excluding storage, initial untracked diagnostics and unrelated Azure activity. No emergency allowance was enabled.


## Conversational release verification

Source `50cce98` is deployed as `dpl_AanJqeeqf1ZXhFq6DbkSvN6wWyqe` at the same public URL. GitHub [run38463770631](https://github.com/aci-commits4u/Nueva-Generacion/actions/runs/38463770631) passed all regression and syntax steps. Hosted live multi-turn audited interpretation, approval, PASS/HOLD,409 refusal, exact exception, simulated receipt, evidence download and reload passed without JavaScript errors. Evidence digest and issuer signature were checked independently, including historical source mappings and question binding. Hosted mobile390px hotel flow in explicit offline mode, keyboard focus, dialog Escape and quality-page reload passed without overflow.

The first live quality canary passed; unauthenticated production scheduler calls returned401 and authenticated replay returned the stored result. Vercel registered the daily07:00UTC cron against this production deployment. Future scheduled executions have not yet occurred at release time.

At release the durable ledger had99 call reservations ($9.90 conservatively reserved), 60 experiment calls,2 monitoring calls and36 interactive calls for the UTC day. The lifetime200-call/$20 allowance was not reset or increased. [Revision ledger](conversation-build-ledger.md) records the complete decisions and verification.
