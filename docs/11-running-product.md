# Running product and operations

Production: **https://intent-judge-perfected.vercel.app**. Branch: `victor/perfected`. Python 3.12 FastAPI and static vanilla web files; Vercel framework `fastapi` discovers `app/main.py`. No frontend build step. The separate Vercel project is `intent-judge-perfected` in `vmj-8946s-projects`.

## What runs where

The browser renders profile questions and reviewed fields. It cannot choose PASS or bypass checkout. FastAPI holds the authoritative session state and deterministic purchase gate. Azure Table stores complete sessions and the global AI reservation ledger with conditional ETag writes. Complete sessions are compressed into bounded binary properties to retain atomic receipts and idempotency within Azure limits. Existing string records migrate on mutation.

The Foundry model is the existing `gpt-oss-120b` deployment. It extracts typed proposals with exact source quotations and optionally explains completed checks. Both calls are real inference; JSON is strictly validated before a draft is accepted. Provider errors are visible and never silently invoke offline mode. The separate emergency parser supports limited phrases and holds unrecognized substantive text. Unit tests do not spend model credits.

The same pure engine loads versioned flight, hotel and general profiles. It understands reviewed operators (`eq`, `in`, `lte`, local time `window`), not arbitrary prompts. Adding a domain means defining typed fields, source fact mappings, questions, and operators; new computations need reviewed code. Customer/merchant text cannot install a profile. General intake preserves unsupported conditions and holds checkout.

Demo discovery is isolated in `demo/fixtures.py`. Signed offers are synthetic; prices are fixed and route/city facts adapt to the reviewed request. There is no live inventory, payment, wallet authentication or booking provider.

## Actual API flow

| Request | Server behavior |
|---|---|
| `GET /api/session` | Start/resume an HTTP-only anonymous synthetic session |
| `POST /api/intents` | Extract a live or explicitly offline draft |
| `POST /api/intents/{id}/answers` | Validate every field, explicit optional no preferences and retained unsupported conditions; advance revision |
| `POST /api/intents/{id}/approve` | Require reviewed revision and digest; issue VI credentials with the exact approved object |
| `POST /api/check` | Verify issuer/agent chain, merchant signature, native constraints and deterministic domain rules |
| `POST /api/decisions/{id}/explain` | Explain current checks; narrative has no authorization authority |
| `POST /api/decisions/{id}/exceptions` | Record specific signed acceptance of exact eligible values and offer hash |
| `POST /api/purchase` | Reverify current approval, signatures, expiry, native constraints and every required acceptance; otherwise HTTP 409 |
| `GET /api/purchases/{id}/evidence` | Return the signed evidence packet for this session |
| `POST /api/disputes` | Prepare advisory analyst context; no actual chargeback |
| `POST /api/session/reset` | Open a fresh workspace without deleting old evidence |

The review screen permits editing supported fields and adding missed conditions. Extra conditions become unimplemented requirements and hold checkout; they do not disappear merely because the customer approved the draft.

## Signing and enforcement

The pinned real Verifiable Intent SDK creates L1, autonomous L2 with the custom domain constraint, and split checkout/payment L3 presentations. The application independently verifies an ES256 merchant checkout JWT against its pinned synthetic merchant key. Agent descriptions never supply authoritative itinerary facts.

Every constraint instance receives explicit dispatch. Product/quantity and amount rules use strict SDK checks. Payment reference placement, uniqueness and exact checkout-disclosure binding are checked. The known custom constraint routes to the profile engine. Unsupported constraint types hold execution. Native over-price acceptance creates a revised signed amount authorization while retaining the original bundle and exact consent.

Missing required facts hold checkout. Broken signatures, expiry, changed approval and unknown constraints cannot be waived. Duration rounds up so fractional minutes never pass a shorter maximum. Offer-specific business differences may be accepted with check ID, accepted value/status, offer hash, approval/profile digest and timestamp. Evidence includes original request, approval, findings, signatures, exceptions, receipt and public keys, ending with `"final_decision": "dispute analyst"`.

Keys demonstrate synthetic trust roles, not Mastercard certification or real consumer hardware signatures. Public keys in a packet still require an independently trusted identity source.

## Budget and maintenance

Configured live limits are 64 model stages per session, 80 interactive stages/day, 100 evaluation stages/day, and an operational ceiling of up to 1,500 stages when the explicitly enabled $30 reservation envelope is configured at the $0.02 minimum rate. The default ordinary reservation allowance remains hard-capped at $20; the additional $10 is opt-in and bounded by the same application maximum. The adaptive_fast path normally reserves one stage per turn; a read-only tool review may reserve one additional bounded stage. Existing historical reservations are retained, and future calls reserve $0.02 additively without repricing or resetting them. Monitoring is limited to two stages/day and 40 lifetime, sharing the same money ledger. SDK automatic retries are disabled and token/time bounds apply. Failed requests keep their reservation. These are application controls; actual Azure credit, unrelated activity, storage and native evaluation compute require separate billing inspection. See [the final reliability record](17-live-reliability-and-uat.md).

Do not clear the global ledger to “fix” an exhausted allowance. Choose emergency mode explicitly for offline presentations, or deliberately review the remaining Azure credit before changing limits. Provider secrets and signing keys stay in ignored `.env` locally and Vercel environment variables in hosting. No secret values belong in Git, browser state or evidence.

Sessions last eight hours; offers/VI credentials last one hour. If a presentation resumes with expired offers, use **New request** to generate fresh reviewed credentials. Each session permits three scenarios and 25 checks. A new session does not reset global spending limits.

Deployment from this branch:

```sh
.venv/bin/pytest -q
node --check web/app.js
npx --yes vercel@63.1.2 deploy --prod --yes --scope vmj-8946s-projects
.venv/bin/python scripts/hosted_capacity.py https://intent-judge-perfected.vercel.app
```

`scripts/browser_flow.js` verifies live intake, approval, explanation, held checkout, exact consent, receipt, evidence and analyst context with Playwright CLI. `scripts/browser_explanation.js` is the independent offline POST regression. Neither exports browser credentials. The hosted capacity script exercises all 25 checks and durable receipt recovery without AI calls.


## Conversational revision

`POST /api/intents/{id}/clarify` accepts the current revision and a customer message. It binds the response to the displayed profile question, performs the selected extraction/audit pipeline, stores immutable source mappings and invalidates prior approval. There are 31 follow-up turns in the standard one-stage adaptive_fast path; every field remains editable in final review. Specific removal of a flagged condition is a recorded traveler action, not model authority. Overflow beyond 20 flags or 6,000 UTF-8 bytes is rejected before saving an unreviewable draft.

`GET /api/quality` serves synthetic aggregate benchmarks and current live-canary status. `GET /api/internal/quality-check` requires the private scheduler bearer secret and is idempotent for its UTC date. `vercel.json` schedules it daily at 07:00 UTC. Stale interrupted runs become unavailable without another paid call. See [the measured evaluation record](15-ai-evaluation-and-conversation.md) for limits and results.
