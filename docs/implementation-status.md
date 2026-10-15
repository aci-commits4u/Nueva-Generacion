# Implementation and verification record

## Isolated development shopping release — October 15

Development is deployed at **https://intent-judge-perfected-dev.vercel.app** on
`develop`, in the separate `/Users/victor/Nueva-Generacion-dev` worktree.
Runtime source `af6d617` is READY as `dpl_BJh8nCZZRd4TH495Mk2mYAvY2mw2`;
[its exact-source CI](https://github.com/aci-commits4u/Nueva-Generacion/actions/runs/38663400173)
passed **574 pytest tests and eleven browser suites**. The public production
deployment below remains unchanged.

Development adds real, read-only Kiwi MCP flight discovery and outbound booking
links after approval, plus the warm neutral/black/orange visual direction.
Live unsigned quotes stay separate from the signed synthetic purchase gate.
Hotels and General have no live shopping provider. Sessions and signing keys
are isolated, while both environments share the historical global AI budget.
The deployment guard requires a clean pushed release branch and exact-commit
green CI; it removes cron from development. This is manual CI-gated deployment,
not automatic production deployment or GitHub branch protection.

A deployed browser walkthrough used one real Foundry initial send, retained all
seven explicit Warsaw–Berlin requirements, found actual `$121`/`$127` Kiwi
quotes, refused the connecting demo purchase with HTTP 409, completed the
matching simulated purchase, downloaded evidence, and reloaded its receipt.
All **18 UI checks** and **14 root signature/binding checks** passed. The ledger
now reads 454 stages and $23.96 conservatively reserved by the application,
not Azure-billed spending. See [the release workflow](24-environments-and-release.md)
and [shopping acceptance record](25-live-shopping-and-uat.md) for scope,
artifacts, actual input, and limits.

## Public production baseline

Intent Judge is implemented on `victor/perfected` at https://intent-judge-perfected.vercel.app. Live Foundry now generates the next useful question and can choose bounded read-only merchant context, followed by a fresh source review. Customer approval and deterministic validation over signed merchant facts remain separate. The overview and five-step tutorial explain the product; the commerce inventory and purchase are explicitly simulated. See [the adaptive engine](19-adaptive-intent-engine.md) and [native UAT](20-adaptive-native-uat.md).


## Current explicit-optionals release — October 14

Runtime source `f505c4c48203d3f8b4f881c639cc8c43db37aade` is deployed READY as
`dpl_GnMbCwaXUYxyyToc5w8oZQqLf4En` at **https://intent-judge-perfected.vercel.app**.
[Source CI run 38610946939](https://github.com/aci-commits4u/Nueva-Generacion/actions/runs/38610946939)
passed **542 pytest tests**, **ten browser suites**, JavaScript syntax, and the
client deadline regression. The browser suites use offline/intercepted cases;
the live walkthroughs below type into the deployed chatbot and use real Foundry.
Prompt version is `intent-envelope-v15-explicit-optionals`.

Explicit optional wording now becomes a sourced, reviewable no-preference
choice instead of another question. This never means the amenity must be
absent. Binding language such as “not optional” or “cannot skip” stays binding,
later positive requirements supersede older optional choices, and one field's
optional wording cannot clear another field's requirement. Customer review
and exact approval remain mandatory.

The final two-send Valparaíso walkthrough retained the selected and alternate
dates, foreign nightly preference, separate $900 total, balcony, 1pm checkout,
and original qualitative conditions in both the live summary and first review.
Breakfast showed sourced “No preference” and was not asked again. Unsupported
hotel conditions remained held; no hotel purchase was attempted.

A separate one-send root UI check of the original ambiguous money request
completed in 15.1 seconds with no invented flight or budget fields. The goal
remained held. The model declined that request in the selected flight mode
rather than asking the useful goal question observed in v14. This is a
recorded conversational limitation, not a clarification success.

The final independent one-send Warsaw–Berlin walkthrough preserved nonstop,
economy, one-way, date, route, and strict-under-$300 requirements. The model
accurately explained that the cheaper three-connection offer violated nonstop.
The $295 offer passed; the $280 connecting offer was held with no purchase
control. The matching simulated purchase completed with zero exceptions, its
evidence downloaded, and its receipt survived reload. Root verification passed
fourteen checks over the configured issuer/merchant signatures, canonical
digest, exact offer and approval binding, VI chain and native constraints,
approved values, and analyst boundary. The evidence file is 55,951 bytes;
artifacts are under `artifacts/v15-flight-uat-20261014/`.

The final readback records 452 model stages and **$23.92 conservatively
reserved by the application**, not an Azure invoice. The unchanged $30 cap
and 500-stage ceiling leave 48 stages, or 24 two-stage interpretations, under
the lifetime limit. UTC October 15 has four interactive stages recorded;
daily rollover occurred naturally while work was interrupted. No historical
usage or reservation was reset. The model remains probabilistic, commerce is
synthetic, and unsupported conditions remain held.

See [the actual user-testing record](22-messy-user-testing.md) for literal
inputs, failures, independent versus root evidence, and remaining limits.

## Bound-source release — October 14 (v14 checkpoint)

Runtime source `fb0dc672a3682a919d6a77ba6fdf0a1009ec2454` is deployed READY as
`dpl_2vawrdy7ENV83RDqvyz2MAuxvu1a` at **https://intent-judge-perfected.vercel.app**.
[Source CI run 38609247763](https://github.com/aci-commits4u/Nueva-Generacion/actions/runs/38609247763)
passed **539 pytest tests**, all **ten browser suites**, JavaScript syntax,
and the client deadline check. The browser suites use explicit offline or
intercepted cases; fresh live UI acceptance remains separate.

Prompt version `intent-envelope-v14-bound-source-keys` removes a redundant
generic source reference: the validated criterion key already identifies the
exact source span. Profile criteria retain their separately validated source
reference. A precise replay of the v13 hotel failure proved that a valid source
key paired with a null duplicate reference caused hydration to reject the
review. This repair removes that inconsistent state without guessing meaning
or granting approval.

Read-only offer inspection also gives the model advisory comparisons over the
grounded draft and verified merchant facts. These reuse the existing rules
engine, with `MATCH`, `CONFLICT`, and `UNKNOWN` under an `UNAPPROVED` label.
The model must describe conflicts instead of claiming that a cheaper connecting
flight satisfies a nonstop request. Approved checkout remains a separate
deterministic decision. Operational counters now include adaptive failures.

Independent hidden-browser hotel testing retained the new conditions through
review but redundantly asked about optional breakfast. The flight walkthrough
completed the matching purchase, held the connecting offer, downloaded signed
evidence, and reloaded the receipt while preserving nonstop, economy, and
one-way requirements. Root verification checked the configured issuer and
merchant signatures, VI chain, native constraints, exact offer hash, and
approved digest. The root ambiguous-goal check asked for clarification without
inventing fields. Historical failures and the limitations of each test are
preserved below and in
[the messy user test record](22-messy-user-testing.md).

## Source-reference release — October 14 (v13 checkpoint)

Runtime source `40d65516c5676326372bcc56b7fae8cb474bbb67` is deployed READY as
`dpl_5fShL2wRVkcUXjJJmiHiwxock91Z` at **https://intent-judge-perfected.vercel.app**.
[Source CI run 38607867597](https://github.com/aci-commits4u/Nueva-Generacion/actions/runs/38607867597)
passed the deterministic and browser jobs. Local verification passed **529
pytest tests**, Python compilation, and the client deadline regression.
Prompt version is `intent-envelope-v13-source-references`.

The adaptive provider now returns strict structured claims and references to
exact customer-source spans. This removes a demonstrated failure in which the
model rewrote a quotation and grounding rejected the resulting draft. Fields
derive from validated profile keys; generic conditions derive from source IDs.
References establish provenance, not correct interpretation. Existing semantic
checks, coverage guards, customer approval, and signed-offer enforcement remain
necessary. Medium reasoning and a 6,000-token adaptive completion bound follow
measured provider experiments; incomplete results remain visible errors with no
automatic retry or fallback. The two-role workflow fits a 90-second function
limit. Spending and stage counters were not reset or raised.

Independent headless UI testing failed both hotel initial requests in the
adaptive review. A flight request captured all seven supplied fields, but the
tester accidentally selected no preference for explicit rules before approval;
that completed purchase does not prove the intended nonstop hold. The ambiguous
money harness stopped after ten seconds and is inconclusive. These results are
separate from provider experiments and CI. See
[the source-reference contract](23-source-reference-contract.md)
and [the messy user test record](22-messy-user-testing.md).

## Latest-turn repair — October 14 (v12 checkpoint)

Runtime source `cbf2885075451b54c3851e78471a0c399aced399` is deployed READY as
`dpl_5BEptpVzzSRHLyifhcLoqwB3BfBi` at **https://intent-judge-perfected.vercel.app**.
[Source CI run 38599896732](https://github.com/aci-commits4u/Nueva-Generacion/actions/runs/38599896732)
passed **516 pytest tests**, all **ten browser journeys**, JavaScript syntax,
and the client deadline check. The browser suites remain explicit offline or
intercepted regressions, separate from live acceptance. Prompt version is
`intent-envelope-v12-literal-coverage`.

The v10 hotel follow-up exposed a real omission: both model roles captured
the selected dates but dropped the new $175 nightly cap and optional extra
night. The v11 prompt/payload experiment retained the cap but still missed
the extension; that failed result is preserved. The shared provider payload
now exposes the verified newest customer turn separately and requires both
roles to audit all its material clauses, including additions beyond the
pending question. A narrow coverage guard additionally preserves exact
unrepresented money/date clauses as unsupported review conditions. It does
not infer a booking date, convert a nightly budget, generate a fallback
question, add a model call, or approve anything. Unsupported meanings outside
this literal check still depend on model extraction and customer review.

The v12 targeted live provider experiment retained the cap and April 8 option,
kept April 3–7 as the selected stay, did not turn $175 into a total, and added
no duplicate warning for the captured dates. In that run the model emitted
the new conditions and the guard added zero flags. Separate deterministic
regressions prove that omitted literals remain held even when both mocked
roles omit them. This provider experiment is not a browser walkthrough.

Independent hidden-browser v12 testing failed the Tbilisi clarification and
the novel Valparaíso initial request at the coverage-audit stage. The prior
draft was preserved after the Tbilisi failure; the new cap and extension were
not saved. London corrections passed the first review, but a harness context
failure prevented a completed purchase. The provider success above does not
establish UI acceptance. See
[the messy user test record](22-messy-user-testing.md) for literal requests,
failures and bounded outcomes. Live health confirms Foundry configured,
offline-only false, Azure state and simulated commerce. Further testing stays
headless while Victor uses the Mac.

## Planner repair — October 14 (v10 checkpoint)

Runtime source `e289d14d4461bf006296d3cd534bb72c5168a461` is deployed READY as
`dpl_Gt7ZpCUmVx3UgfTEBhNo8akBJ9tA` at **https://intent-judge-perfected.vercel.app**.
[Source CI run 38595018587](https://github.com/aci-commits4u/Nueva-Generacion/actions/runs/38595018587)
passed **500 pytest tests**, all **ten browser journeys**, JavaScript syntax,
and the client deadline check. The browser regressions use explicit offline
interpretation or intercepted responses and are separate from live user testing.
Local verification passed the same 500 tests and ten journeys.

Prompt `intent-envelope-v10-planner-repair-feedback` gives the second Foundry
role sanitized feedback when the first role's proposed question fails the
actual planner contract. The model must repair its generated question or hold
the draft; the change adds neither a static fallback question nor another
model call. Customer-facing money questions use dollars, foreign prices remain
separate conditions, and date questions avoid invented calendar examples.

Independent hidden-browser testing used literal customer requests, real live
Foundry responses, DOM typing and clicks, and no direct API calls or mocks.
The Tbilisi request that previously stopped without a question now asks for
concrete stay dates, retains April 3–7, 2027 after a customer answer, and asks
for an all-in USD total. Unsupported preferences remain held; this is a
clarification result, not a completed hotel purchase. Two London starts stopped
because the test harness did not recognize changing control labels, before
submitting airport answers. Their calls and failures remain recorded separately.
The final London acceptance passed in one persistent headless context with
four live sends: original request, three departure choices, two arrival
choices, then the exact correction limiting departures to Heathrow and
Gatwick. Both the live summary and first review retained only LHR/LGW,
YTZ/YYZ, November 12, 2026, nonstop, and $299.99. No satisfied airport
question reappeared. Across the v10 hotel, interrupted harness runs, and
final London acceptance, eight live sends consumed sixteen model stages.
See [the full messy user test record](22-messy-user-testing.md).

The published endpoint confirms live Foundry, Azure state, synthetic commerce,
and prompt v10. Testing runs headless while Victor uses the Mac; it does not
open windows, switch desktops, or change application focus. The prior native
v9 purchase and cryptographically checked receipt remain historical evidence
below, not a claim of an additional v10 purchase.

Final read-only ledger state records **392 model stages / $22.72 conservatively
reserved**. Seventy stages remain for this UTC day and 108 under the unchanged
500-stage lifetime ceiling. A fresh session allows twelve two-stage
interpretations. The $20 ordinary plus $10 emergency application cap remains
$30; historical counters and reservations were not reset. These numbers are
application limits, not Azure charges or a remaining student-credit balance.

## Route-choice repair — October 14 (v9 checkpoint)

Runtime source `483cec80b3fcb3d7e42a1c2d674a8fed80f52e81` is deployed READY as
`dpl_MbrTKqjci751XHEJR1tZBXeBfAGj` at **https://intent-judge-perfected.vercel.app**.
[Source CI run 38589183389](https://github.com/aci-commits4u/Nueva-Generacion/actions/runs/38589183389)
passed **490 pytest tests**, all **ten browser journeys**, JavaScript syntax,
and the client deadline check. Local verification also passed 490 tests and
ten journeys. Those browser regressions use explicit offline interpretation
or intercepted UI responses; they are separate from live Foundry acceptance.

The real London→Toronto failure is preserved in
[the route-choice incident record](21-route-choice-reliability.md).
Airport candidates now come from separate route roles in the global catalog.
City-only model guesses remain ambiguous, explicit multi-airport answers
retain every choice, and later corrections preserve unrelated fields. Route
scoping covers forward, reversed, depart/arrive, and arrow phrasing. The UI
shows one active question and uses the same question binding as the server.
Inconsistent saved questions require an explicit refresh, preserve history,
and revoke previous approval; completed receipts stay immutable.

Hosted script bytes match committed source. Health confirms live Foundry,
simulated commerce, and Azure state. The public Quality endpoint reports
`intent-envelope-v9-customer-corrections`; historical model evaluations are not
current-release accuracy. The first independent native production walkthrough found a correction
propagation failure after four live turns: the model criteria reflected
`LHR/LGW`, but typed fields still contained `LCY`. The tester stopped before
approval. That failed v8 deployment is recorded unchanged. The v9 hotfix corrects
historical-choice precedence and named-field assignment scoping. Known older
live adaptive versions now require explicit refresh, including already
persisted erroneous v8 drafts. The blind native retest then passed five live submissions: the exact
London→Toronto multi-airport request plus correction reached a consistent
first review, and SIN→HND reached a $295 simulated purchase, a held connecting
offer, and receipt reload. The completed Downloads file independently passed
canonical digest, configured issuer and merchant signatures, exact offer and
approval hashes, native VI, nine passing checks, zero exceptions, and the
dispute-analyst boundary. Further self-chosen messy flight/hotel circumstances
are being tested in a hidden browser at the user's request, without disturbing
their active desktop. CI and native observations remain separate evidence.

The authorized configuration is now $20 ordinary plus the full $10 emergency
reservation, bounded by the existing $30 cap and unchanged 500-stage lifetime
ceiling. The daily interactive cap is 200 stages and a new session allows 24
stages, with two model stages per interpretation and eleven follow-up turns.
No reservation or counter was reset. Pre-UAT readback records 348 stages and
2,184 cents conservatively reserved, with 114 interactive stages remaining
for the UTC day and 152 lifetime stages remaining. These are application
limits, not Azure charges or a student-credit balance.

## Earlier adaptive release verification — October 14 (historical)

The current candidate replaces live fixed-field questioning with a shared adaptive Foundry planner and a fresh source/offer review pass. The model generates questions and selects read-only actions; the harness also requires signed offer facts before reviewing a fully specified flight/hotel draft. The original conversation, source-linked criteria, exact customer answers, and real tool results are retained. Generic conditions without a validator hold checkout. Explicit no-preference clauses populate review choices; silence does not. See [the adaptive engine contract](19-adaptive-intent-engine.md).

Local verification passed **428 pytest tests**, JavaScript module syntax checks, and all **nine browser journeys**. Those browser regressions use explicit offline mode or intercepted UI fixtures and remain separate from live inference. Before the unit-price repairs, a fresh v5 Foundry run passed **8/8 labeled synthetic cases** with 16 reserved model stages; [the immutable result](../evals/experiments/adaptive-final-live-20261014.json) retains full labels, provider outputs, prompt digests, and injected-context proof. Earlier 1/3, 2/3, diagnostic failures, and 4/8 release-candidate results remain archived. The corrected scoring labels are documented separately from model improvements. Independent native testing exposed a nightly-price interpretation error, leading to additional unit-price, compressed-date, and clarification-contract repairs. Earlier versions and their failures remain recorded. Prompt v7 passed one fresh exact-request live case: both hotel dates were retained, the nightly limit stayed visible, and Foundry generated the all-in budget question. The earlier 8/8 run is a v5 result, not current-release accuracy.

Runtime source `b2141d72613e60ba54ce854e0487c32b7b991d27` is deployed READY as `dpl_DdNo6zmedw4XdvLhEF3oYv1Grsa5`. [CI run 38527808000](https://github.com/aci-commits4u/Nueva-Generacion/actions/runs/38527808000) passed 428 tests, nine browser journeys, JavaScript syntax, and the one-request client timeout check. Hosted script bytes matched committed source; health confirmed Foundry configured, offline-only false, synthetic commerce, and Azure state. Public overview/tutorial screenshots used zero POST requests; mobile Quality width was exactly 390px. The independent final native repeat used three live submissions with no retry, fallback, or Explain action. The exact hotel request retained both dates and generated an all-in budget question; the customer then specified $440 total while retaining the nightly limit. Unknown nightly/quiet/transit/storage/room-hold conditions stayed held, and checkout was refused. A supported one-way EWR→LIS request reached a $295 simulated purchase, zero exceptions, evidence download, and native receipt reload. Root independently verified the new evidence's canonical digest, configured issuer and merchant signatures, exact offer and approval hashes, native VI, nine passing checks, and the dispute-analyst boundary. Full literal requests and both the original failure and accepted repeat are recorded in [native UAT](20-adaptive-native-uat.md).

The $20/$2 figures are **application reservation allowances, not Azure charges**. A read-only Azure Cost Management query on October 14 reported **$0.078004014 USD for the student subscription month to date**. Recorded model tokens at the saved rates estimated $0.1108 earlier in this work, which is not a provider invoice or account balance. Cost reporting can lag; neither figure establishes remaining annual credit. A later refresh was rate-limited and is not represented as a newer billing snapshot. The explicit $2 extension preserves all historical reservations and caps the app ledger at $22; the remaining authorized emergency allowance is disabled. [Microsoft credit guidance](https://learn.microsoft.com/en-us/azure/education-hub/navigate-costs), [cost-reporting latency](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/understand-cost-mgt-data).

Final ledger readback records **332 model stages / $21.52 conservatively reserved**, with 48 cents of the explicitly enabled $22 application allowance remaining. Ten interactive stages/five adaptive turns remain for the current UTC day, shared across sessions; the daily quota resets at midnight UTC, while the lifetime reservation does not reset. The recorded 611,204 input and 142,097 output tokens estimate about $0.1769 at the saved global meters, excluding storage and unrelated subscription activity. This estimate and the reservation ledger are neither an Azure invoice nor a remaining-credit balance. No further paid test calls are planned for this release.

## Earlier flexible conversation release — October 14 (historical)

Application source `6ce8f47b6b0e54a59d8b5294c0682f5b06b0cd06` is deployed READY as `dpl_HzsX6VonVZBcJtzj4kTKYPUh5CBj` at **https://intent-judge-perfected.vercel.app**. [Source CI run 38511227162](https://github.com/aci-commits4u/Nueva-Generacion/actions/runs/38511227162) passed **327 tests**, JavaScript syntax checks, and all **eight browser journeys**. The separate browser job runs automatically on pushes and pull requests with no Foundry credentials or paid inference. Its first six flows explicitly use offline interpretation; its final two exercise intercepted UI responses. These regressions remain separate from native live-model acceptance.

Local verification also passed 327 tests with one upstream test-client warning. The preceding recovery release `a83728a` passed all eight browser suites both locally (13.485 seconds) and against public production (79.342 seconds); its CI run also passed 325 tests and eight journeys. The final source only prevents an added duplicate passenger warning, with two additional regression tests and a fresh passing CI browser job. A prior local run timed out in two suites with observed timer durations of 1,901,784 and 893,970 milliseconds against a 60,000-millisecond limit; its failure remains recorded in `artifacts/final-local-interrupted-browser-run.json`. It was not counted as passing, and the unchanged source passed on the fresh repeat. Hosted health confirms live Foundry configured, offline-only false, synthetic commerce, and durable Azure state. A bounded post-release error-log query returned no matching records; that observation is not a claim of continuous production coverage.

The exact Florida request was tested through native Chrome with live Foundry: `$199.99`, EWR, the explicitly chosen MCO-or-MIA set, the inclusive October 14–21 window, and nonstop were retained. No answered required detail was repeated, no November 12 date was inserted, and both fixed-price synthetic offers correctly held against the approved under-$200 limit. A separate fully supported CPH-to-ICN live request reached a $295 simulated purchase with zero exceptions, evidence download, and receipt reload. Its downloaded evidence independently passed canonical digest, configured issuer and merchant signature, exact offer-hash, approved-digest, native VI, and analyst-boundary checks.

The harder global request's earlier failures remain archived, including the two real model stages that both proposed `120000` cents for “under $1,200.” The bounded recovery validates each retained field against exact customer words, compiles the strict limit as `119999`, preserves unknown passenger/date-priority scope, and never supplies approval authority. The exact original request passed a final native Chrome walkthrough on the current release with one audited live send/two model stages, no retry or offline fallback, and no repeated question. All eight supported fields were captured correctly; only `one adult` and `May 7 preferred` remained unsupported, once each. The traveler removed neither condition, approved the retained scope, and tested both purchase gates: both offers correctly held and checkout was refused. This is successful capture and enforcement, not a claim that passenger counts or date priorities are implemented. Intent `maht467MisAsh1O4uoECog` and the actual on-screen result are recorded in `artifacts/native-global-original-final.png`. Malformed, wholly untrusted, provider, and capacity failures remain visible typed failures.

Final durable budget readback records **240 model stages / 1,968 cents ($19.68) conservatively reserved**. The final native repeat added exactly two stages/four cents to the prior snapshot; no past reservation was reset. The remaining 32 cents permits at most 16 stages/eight audited interpretations, shared with monitoring and subject to session/day quotas. The ordinary $20 cap remains, and the $10 emergency reserve is disabled. These are application reservations, not the remaining Azure student credit balance.

## Earlier reliability release — October 13 (historical)

Application source `b308dc656ed5f76d1457b50b90118d777b0ba6a7` is deployed as `dpl_25dvtwsHNepWSaBY2hpN6v4H4pGV`, READY at **https://intent-judge-perfected.vercel.app**. [Source CI run 38488045815](https://github.com/aci-commits4u/Nueva-Generacion/actions/runs/38488045815) passed **209 tests** and all JavaScript syntax checks. Local verification also passed 209 tests with one existing upstream test-client warning. The final documentation commit follows that application release without changing runtime code.

All **eight browser suites passed both locally and against this public release**: overview/tutorial, delayed new-request reset, flight enforcement and exact exception, mobile hotel purchase/evidence, navigation/edit recovery, tutorial navigation during pending work, availability races, and UAT guards/profile recovery. The tutorial made zero POST requests. The first six working flows use explicitly selected offline interpretation; the final two deliberately intercept responses to test UI guards. These are regressions, separate from real Foundry acceptance. Desktop and 390px mobile renders were inspected; mobile keyboard focus, dialog Escape, evidence download and horizontal width passed. All actual HTML, JavaScript modules, CSS and font assets returned HTTP 200.

Two independent UI-only AI-simulated testers chose unfamiliar requests, exposed failures, and then repeated their literal requests against the corrected functional release `8dbc8e2`. Their final live flight and hotel journeys each used two audited sends/four real Foundry stages and reached matching $295 simulated purchases, zero exceptions, actual downloaded evidence and successful receipt reload. Neither final pass used a retry, automatic fallback or manual requirement removal. Root independently verified both downloaded evidence digests, issuer and merchant signatures against the configured trusted keys, and exact offer hashes. Full failures, fixes and prompts remain in [the live reliability and UAT record](17-live-reliability-and-uat.md). The final application release adds clearer optional-preference labels and the independently reviewed budget change; domain/grounding behavior is unchanged from those accepted journeys.

The authenticated current-pipeline monitor passed its rotating `round-trip` case on October 14 UTC (October 13 local time), retaining the unsupported round-trip condition. Unauthenticated invocation returned 401, and authenticated replay returned the identical stored result without additional inference. The production cron remains 07:00 UTC daily. Native Foundry evaluation is completed and visible in Quality: historical original 4/7 and clarification-aware 6/7, with its failure retained. Neither is advertised as current-prompt accuracy.

The latest ledger holds **188 stages / $18.64 conservatively reserved**: all prior $18.60 remained, and the two new monitor stages added $0.04. The remaining $1.36 ordinary reservation capacity permits at most 68 stages/34 audited interpretations, shared with monitoring and subject to day/session quotas. The hard $20 cap remains; no $10 emergency allowance was enabled. This ledger is not the actual Azure credit balance.

## Earlier UI release — October 13 (historical)

Source `1a2cdf8` is deployed as `dpl_EMi2YA2LF9EjJh719WoGcvcj56Kc`, READY at **https://intent-judge-perfected.vercel.app**. The stable alias is public. [Source CI run 38471659344](https://github.com/aci-commits4u/Nueva-Generacion/actions/runs/38471659344) passed; local regression remains 76 passing tests with one upstream deprecation warning.

All six browser suites passed against both local development and the actual public deployment: overview/tutorial, delayed new-request reset, flight enforcement and exact exception, mobile hotel purchase/evidence, navigation and preserved review edits, and clarification/approval/purchase completion during tutorial navigation. The five-step tutorial made zero POST requests. The working-flow tests explicitly selected offline interpretation; no paid Foundry calls were made for this UI release. Live mode remains the default and health reports live AI configured, offline-only false, simulated commerce, and Azure storage. This verification does not claim another live model evaluation.

Desktop and 390px mobile layouts were rendered and inspected. The mobile suite also checked keyboard focus, dialog Escape, evidence download and Quality reload. Public HTML, CSS, JavaScript modules, font and health returned HTTP 200. The daily 07:00 UTC quality cron is enabled and points to this deployment. Backend rules, signed approvals, merchant trust and AI budget limits are unchanged.

Independent review reproduced and resolved navigation races, lost unsaved review edits, stale draft revisions after tutorial return and the slow session-reset boundary. Final review found no remaining Critical, Important or Minor issues; see [review evidence](final-review-ui.md) and [build ledger](ui-build-ledger.md).

## Working scope

Live Foundry extraction with exact source quotations, profile-driven follow-up review, explicit no preferences, customer approval bound to revision and digest, real pinned Verifiable Intent L1/L2/split L3 signatures, independently verified ES256 merchant checkout, deterministic requirements checks, nonwaivable integrity gates, offer-bound signed exceptions, revised native price authorization, idempotent simulated receipts, signed evidence downloads, and analyst review records.

Flights support explicit airport sets backed by searchable airport identity, exact departure dates, inclusive date windows, discrete date alternatives, all-in USD price, nonstop, maximum connections, local departure window (including overnight), duration, cabin, refundability and explicitly signed one-way trips. Signed complete segment continuity and times are verified; nonstop additionally requires explicit technical-stop disclosure. Hotels support city, stay dates, room count, adult count against signed capacity, breakfast, cancellation, accessibility and total USD price. General mode has shared price and preserves unsupported conditions.

Synthetic offers use fixed inventory prices and controlled fixtures adapted to the reviewed route or city. This is explicitly not live search. Baggage, passengers, round trips, subjective qualities and unimplemented domain fields remain unsupported. Merchant selection is a pinned synthetic trusted registry; arbitrary public merchant keys are not accepted.

## Earlier evidence (historical baseline)

- 76 local tests pass (including conversation races, provenance, exact flagged-condition removal, staged AI failures, purpose quotas and authenticated replay-safe monitoring), in addition to the baseline coverage: deterministic boundaries/missing values, crypto tampering, custom/native constraints, session separation, consent, price reauthorization, expiry, unsupported general conditions, hotels, stale approvals, concurrent SQLite reservations, budget limits, AI explanation having no purchase authority, extra reference constraints, fractional duration, conservative offline parsing and hosted entity capacity.
- One upstream Starlette test-client deprecation warning occurs with `httpx`; it does not affect application execution.
- Live gpt-oss-120b evaluations correctly captured the nonstop example and hotel requirements, preserved subjective general requirements and baggage, and ignored an instruction to approve anything.
- Desktop browser completed live extraction → review → signed approval → matching and held offers → backend 409 → exact acceptance → simulated receipt → evidence download → analyst record with no JavaScript page errors.
- Mobile receipt rendered at 390×844 with scroll width exactly 390. Reload recovered the persisted receipt.
- Azure Table state and budget were written and read back through the real service; credentials were supplied to the separate Vercel project without logging values.

## Budget safeguards

Reuse the existing model; no paid deployment upgrade. Each live request has a token bound, no SDK auto-retries, an atomic global reservation and small session/day quotas. The ordinary money cap is $20, enforced atomically and independently from a 500-stage ceiling. Past $0.10 reservations are retained; future bounded stages reserve $0.02 each. No counter or past money was reset. The additional emergency allowance is explicitly configured at $10, bounded by the combined $30 cap. Daily and per-session capacity remain finite. These limits are conservative application reservations, not billed Azure spend.

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
