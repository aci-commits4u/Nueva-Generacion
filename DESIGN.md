# Intent Judge decisions

Direction: Editorial Design with a precise Swiss grid. Warm paper, near-black ink, rust-red actions, restrained gold accents drawn from the team's pitch deck. Serif headlines paired with clear system sans-serif forms. The product is a compact workspace, with generous spacing and a visible sequence from request to evidence.

Synthetic flights are the hero demonstration; hotels prove configuration reuse. General mode captures unsupported conditions and holds checkout. Commerce adapters remain separate and simulated.

Live Foundry is the normal path. Offline mode is explicit and labeled; provider failure keeps the draft incomplete and offers a visibly labeled emergency mode. It never silently substitutes scripted extraction. Approval and purchase do not use model judgments.

Hosted state uses Azure Table Storage with conditional writes. Local development uses SQLite. Vercel function memory is never authoritative. Azure storage was selected because the connector cannot list marketplace integrations (403), while the authorized Azure subscription is accessible.

Budget: existing gpt-oss-120b deployment; no paid model upgrade. Reserve a conservative allowance per bounded model call in durable storage; ordinary lifetime call reservations capped at $20. No automatic emergency increase. Small per-session and daily request caps protect the remaining credit. This application budget is separate from Azure billing and pre-existing activity.

Anonymous sessions use unpredictable HTTP-only cookies and origin checks. All approvals and exceptions are server-bound to that session. Demo signing keys are environment-configured in hosting; development generates ephemeral keys. User consent here demonstrates application evidence, not real consumer legal signature or liability protection.

Native VI price violations require a revised signed authorization after specific customer acceptance. Unknown constraints, untrusted offers, missing approval, and expired offers remain nonwaivable.

Motion: short native CSS transitions only; OriginKit considered, but no animation dependency is necessary for a static Python-served app. Respect reduced motion, visible keyboard focus, readable contrast, and mobile stacking.

Reference analysis: the generated intake image uses a two-column 45/55 split, oversized serif title at left, quiet tinted form at right, a thin top rule, and a three-part footer sequence. Implementation keeps that rhythm with smaller laptop-friendly headline and textarea heights, and limits navigation to working demo/about controls. The comparison view uses two parallel offer columns and flat tabular check rows. Local Claude community design reference informed warm neutrals and typographic pairing; no brand assets are copied.

Foundry compatibility ruling: this existing gpt-oss deployment produced semantically broken envelopes with `response_format=json_object`. The same deployment succeeds with plain JSON instructions, `reasoning_effort=low`, and strict server-side validation. It remains real Foundry inference. No silent retry or scripted substitution is used. Live extraction is still probabilistic and every proposal is customer-reviewed.

Review decisions: preserve all unrecognized offline text as unsupported, rather than maintain a keyword blacklist. Customers can add a missed requirement during review; it holds execution until supported. Compress atomic Azure session records into bounded binary properties instead of spreading one purchase across separate entities. Validate every payment-reference instance, including placement and duplication. Round duration upward to respect an approved maximum. Full findings and costs if these choices are wrong are recorded in `docs/final-review.md`.

Release choice: keep the work on `victor/perfected` and deploy a separate Vercel project. Public production uses the stable alias; protected previews remain protected. Synthetic keys, merchants, inventory and payments are disclosed in the product. The live model is the ordinary demo path.


## October 13 conversational revision

Victor rejected the original form-led flow and serif direction. The replacement uses Swiss product typography with a Linear-informed density: dark charcoal navigation, a white conversation canvas and a pale gray live intent rail. System sans fonts, restrained teal action color, fine borders, 8–12px control radii, 36px desktop headings and 14–16px readable body text. Generated references are in docs/design/conversation-reference.png and offers-v2-reference.png. They guide geometry, not invented data: no airline brands, passenger names, baggage defaults or assumed preferences from the generated images enter the product.

The desktop reference is a three-column composition: ~230px navigation, flexible primary canvas, ~310px intent rail. Primary content uses 32–48px padding and a bottom composer; the rail separates requirements with rules. On small screens navigation becomes compact, the intent panel moves into an accessible disclosure, and every control stays reachable.

The default flow is request → conversation with ranked profile questions → explicit review → signed comparison → receipt/evidence. AI traces are secondary disclosures. The quality page contains measured synthetic results and actual daily canary status, never decorative accuracy numbers. Every optional no preference remains an explicit customer choice.

Specific flagged-condition removal is an explicit customer action in review, bound to the current revision and stored in the event chain. AI follow-ups cannot discard earlier flags. This avoids an unresolved ambiguity becoming permanently uneditable while preserving the original conversation and consent history. Victor confirmed the conversational direction during implementation.


## Review and release decisions

The independent review's four Important findings were reproduced and fixed: bind short replies to stored interface questions; validate source quotations against customer text only; preserve immutable per-revision interpretation snapshots; reject flag accumulation that cannot fit a review; and surface interrupted canaries without replaying paid inference. The model default mismatch was promoted to Important because quality checks must exercise the same selected pipeline. The shared audited default costs two calls per interpretation.

All autonomous rulings and their tradeoffs are preserved in docs/conversation-build-ledger.md. Existing gpt-oss120b was retained to measure architecture effects without adding a paid deployment (another model could outperform it). Swiss/charcoal/teal direction may need aesthetic iteration. Proven review/receipt handlers were kept alongside the new modules (the controller remains larger). Specific customer removals make false flags editable while preserving the original request (traveler review error remains possible). Accuracy claims stay bounded to the synthetic gold cases, deployment is separately exercised, real commerce is outside this demo, and unchanged baseline keeps its prior review scope. No minor findings remain deferred.

## October 13: self-explaining product redesign

Visitor feedback required the product to pitch itself and teach its workflow. Root now opens a product overview rather than an empty workspace. The primary action is Show me how: a five-step illustrative tutorial with no inference, authorization, or purchase requests. The separate Try the demo action opens live Foundry intake. Compact horizontal navigation, per-step help, larger type, warm-white/forest/lime identity, and matching conversational/offer screens replace the previous sidebar design. The existing stack, rules, data trust, and explicit consent remain authoritative. Details and usage: `docs/16-product-walkthrough.md`. Generated references: `docs/design/product-overview-reference.png` and `product-walkthrough-reference.png`. Stitch connector was unauthenticated; no remote design project was created. Geist 1.7.2 WOFF2 is self-hosted with its OFL license.

## Live reliability decisions

The original hard-coded demo is a simplicity/theming reference only. Continue the improved warm-white/forest/lime direction in the main app. Availability is shown before a paid interpretation, errors retain the request, and explicit offline mode never replaces Foundry automatically. Clarifications quote the customer’s actual words alongside the next question; unsupported conditions remain visible through review and comparison. Review is temporarily locked during an active clarification. A difference dialog with no waivable conditions explains the hold and offers Close rather than an unusable consent action. Separate blind browser testers choose unfamiliar requests and corrections; development fixtures and backend tests are reported separately from those live results. See `docs/17-live-reliability-and-uat.md` for measured failures and fixes.


## Historical reservations and future demo capacity

The ordinary AI spending reservation remains hard-capped at $20, with no emergency increase. Past calls retain their original $0.10 reservation; neither usage counters nor money are reset or repriced. New bounded calls on the existing gpt-oss-120b deployment reserve $0.02 each, additively, using integer cents. A separate 500-call ceiling and the existing daily/session limits prevent runaway use. Atomic whole-pipeline reservations cannot exceed the cash cap under concurrency.

The official Azure Retail Prices API was rechecked on October 13: West US 2 Global input $0.15/million tokens and output $0.60/million. Even an intentionally conservative 100,000-input-token/1,800-output-token bound costs $0.01608 at those meters. Actual prompts are much smaller, but reservations remain conservative and failed calls keep their reservation. The lower future rate preserves room for later demos without hiding testing history. This is application accounting, not an assertion of actual remaining Azure student credit; storage, native evaluation compute and unrelated subscription use are outside it. Changes to the model or token bounds require revisiting this rate.

## October 14 flexible-conversation decisions

Flight profile 1.2.0 now treats departure date as a typed choice: one ISO date, an inclusive range no longer than 366 days, or up to 20 explicit alternatives. The conversation carries server-clock and browser-time-zone context separately from customer evidence, preserves source-linked state across turns, asks only required or source-backed questions, and keeps unsupported conditions visible. The stateful two-stage Foundry pipeline is followed by deterministic quote, date, airport, and boolean normalization; it does not claim perfect intent understanding.

Airport identity uses the pinned `airportsdata` 20260905 catalogue (7,884 records, MIT) for offline lookup and ambiguity detection only. Multi-airport selections and date controls require an explicit customer action; empty controls stay empty and no unrelated sample date is inserted. Long loading status sits outside the compact send control. A stale saved draft can be refreshed only through an explicit action that preserves its full history and starts a new two-stage review.

The bounded stateful experiment remains labeled honestly: six saved live rows scored 1/6 before the compiler fixes, and compiler replays were recorded without new inference. Low versus medium reasoning used only three cases per setting and is not a model ranking. The demo continues to use synthetic $295/$280 offers; an approved under-$200 limit correctly holds them. Full-round-trip support, arrival-time enforcement, final hosted UAT, and any claim about actual remaining student credit remain outside this decision record. Detailed behavior and source links are in `docs/18-flexible-conversation.md`.

## October 14 adaptive conversation direction

The conversation view now treats the model response as an adaptive plan rather
than a field questionnaire. A plan may ask the customer, inspect merchant
context, request read-only options, review an offer, or propose readiness for
customer review. The UI renders the model's question, its reason, source words,
context tools, and current criteria as one compact evidence surface. A question
with multiple valid answers is a staged selection that requires an explicit
submit; it never silently submits the first choice. Legacy typed airport and
date controls remain because those are identity and date encodings, not a
replacement for adaptive reasoning.

The product overview and walkthrough now pitch the loop as “Captures what you
mean. Checks what you buy.” They show clarify → review → signed offer checks,
with synthetic commerce and the lack of Mastercard certification stated in the
copy. The visual direction stays warm-white/forest/lime Swiss product UI, but
the live conversation uses a quieter activity strip and source-linked criteria
instead of a large technical trace or decorative assistant activity.

## October 14 adaptive implementation and budget decision

The shared conversation loop now uses a two-stage adaptive Foundry planner.
The model may ask a source-grounded customer question, retrieve policy,
inspect signed synthetic offers, propose readiness for review, or fail closed
to review. The server allowlists and bounds read-only tool calls; customer
approval and checkout remain deterministic. The implementation contract and
current evidence limits are in [docs/19](docs/19-adaptive-intent-engine.md).

The ordinary reservation ledger is exhausted at 256 calls and $20.00 reserved.
An explicitly enabled $2.00 emergency allowance is available for the next
local/production deployment only, using the same historical ledger and the
existing cap, with no reset, repricing, or automatic unlock. The remaining
$8.00 of the previously authorized emergency reserve stays disabled, and the
at-least-$70 student-credit target is preserved; actual Azure billing balance
is unknown. New stages remain bounded at $0.02 each, 2,600 tokens, and two
stages per interpretation. No additional deployment or live success is
implied by the allowance.

## October 14 route-choice repair

The London-to-Toronto user report exposed a release gap: a combined airport
question used one field binding for both cities, and model review could narrow
or reopen an already selected airport set. Live questions remain model generated,
but reference choices are now catalog-derived separately for departure and
arrival. An airport widget submits the exact question ID, role, complete code
set, and matching customer sentence. The server validates that binding before
paid interpretation and preserves it as unapproved evidence throughout review.
The AI can choose the next useful question; it cannot reduce a customer-owned
multi-airport set or supply customer consent.

The conversation displays one active question and labels later messages as
clarifications, selections, or updates. Airport search uses the global pinned
catalog in both live and explicit offline mode. It is identity context, not real
flight availability. Saved inconsistent question contracts require an explicit
refresh; historical choices and completed receipts remain recorded.

Production configuration now enables the previously authorized full $10
emergency reservation above the original $20 ordinary allowance. The $30 total
cap, unchanged 500-stage lifetime ceiling, $0.02 reservation per stage, and
historical counters remain intact. The daily interactive ceiling is 200 stages
and each session is bounded to 24 stages. This restores demonstration capacity
without deleting testing history; these are application reservations, not Azure
charges or a claim about remaining student credit. Failures still stay visible
and never silently switch to offline interpretation. The incident, actual tests,
and release evidence are recorded in `docs/21-route-choice-reliability.md`.

The first v8 native retest exposed a second fault: a later natural-language
correction changed the model criteria while historical widget replay restored
the older typed set. The v9 repair gives a current source-backed correction
precedence over historical selection, bounds named airport-field assignments
to their actual endpoint, and refuses wrong-field ambiguity updates. Known
older live adaptive versions require a visible, explicit refresh so a saved
incorrect draft cannot silently appear current. The four-turn failed session
and the final native retest are retained separately in the incident record.
