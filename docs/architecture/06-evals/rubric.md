# Head-to-head experiments and ablations

Status: **designed, not run**. This new JSONL has no adapter to the running application yet. The existing benchmark accepts a different JSON format and usually evaluates a supplied conversation history; do not claim it executes these trajectories. No paid inference was made for this architecture review.

## Common experiment controls

Freeze incumbent source ef4fc34484cf5432153a9ad423165625202a2bc8 (runtime change a670e0cb65f9b161faa2fb61baf9afaa655bf53f), v19 prompt, profiles, Foundry deployment/version/reasoning level, trusted clock/time zone, source fixtures, scoring rubric, token caps, tool endpoints and artifact hashes. Record actual settings rather than assuming environment matches old traces. Revalidate any unavailable historical artifact; do not manufacture missing provenance.

Compare A, B and C with the same model initially. Give every arm the same tool/capability information and final approval/VI/check gate. A may access the same observations through its existing one-tool path; C may decide to gather additional observations under its stated cap. Log this information/call asymmetry explicitly as the treatment. Also run a matched-information comparison with all relevant observations pre-supplied, separating discovery advantage from architecture/state reasoning.

Use fresh sessions per trajectory, reset identical synthetic inventory/clock, and randomize/counterbalance arm order within scenario family and time block. Record provider load/cold start and geography. Temperature 0 does not establish reproducibility; repeat trials. Every submit uses actual app/API/UI transitions. Do not inject final expected fields, preseed session answers, intercept the model with mocks, or let a manual correction count as an AI pass. A simulator may choose the next user utterance based on a hidden scenario goal, but cannot expose that goal to the app. Frozen state/authority oracles judge output; model judges are advisory for language relevance only.

## Staged evaluation

1. **Offline harness qualification:** reducer/API/concurrency/property tests; schema and source checks; dry run all case fixtures against test doubles only to validate instrumentation. Label these harness checks, not live quality results. Implement only after approval.
2. **Screening pilot:** 12 new families, 4 per domain, A/B/C × 2 runs = 72 complete conversations. Include ordinary, correction/set, ambiguity/unsupported and adversarial/recovery paths in each domain. Actual calls exceed conversations. Stop at a separately approved spending cap; use the first family to calibrate cost and runtime. This screens failure modes and estimates variance; it cannot support release confidence by itself.
3. **Confirmatory comparison:** after selecting B or C against A, freeze prompts/criteria and commission new held-out families. Proposed planning envelope 120 families × 3 trials × 2 finalists = 720 conversations. Determine final sample size from pilot paired discordance/cluster variance and the chosen minimum useful gain; report power and budget feasibility before running. If unaffordable, report uncertainty and keep release gate closed. Do not repeatedly peek and stop when the challenger looks best.
4. **Blind product UAT:** at least two fresh testers who did not author prompts choose tasks from a task brief, type freely in the chatbot, change their mind, choose multiple values, interrupt/reload and attempt approval/checkout. Keep expected outcomes hidden from developers during the session. Include at least 6 independently created journeys/domain/finalist initially; this qualitative gate is additional to quantitative trials, not statistically representative. Synthetic airline/hotel facts remain labelled; no real booking.
5. **Canary:** only after separate promotion approval, dev-first and a reversible flag, low exposure, sampled review and a kill switch. No automatic production promotion from test-count success.

The checked-in JSONL is an **exposed development challenge set**, never a sealed final holdout. Generate/evaluate final families independently; paraphrases of the same scenario stay in the same split. Old known “holdout” cases become regressions. Persist raw proposals, post-validation drafts, typed edits, model/tool traces, final UI states and grading separately, so a backend repair or scorer change cannot masquerade as model improvement.

## Required measurements

| Measure | Deterministic definition / grading |
|---|---|
| Complete task success | Every required intent predicate correct after every relevant turn; intended corrections applied; explicit approval binds exact state; conflicting offer held; valid simulated path/evidence works. Any hidden requirement loss, unauthorized side effect or manual rescue fails AI success. |
| Critical recall and precision | Active oracle requirements represented correctly / required; proposed required constraints actually supported / proposed. Report predicate/unit/scope/set/status separately; exact set equivalence, not substring accuracy. |
| Repeated question rate | Question targets already resolved/declined meaning without a new conflict, divided by questions and also per conversation. Semantic duplicates need blind adjudication, not field-name match alone. |
| Useful questions | Blinded 0–2 rating: unnecessary, defensible, materially changes decision; inter-rater disagreement and examples reported. No reward just for asking more. |
| Corrections and retention | Changed record correctly superseded; unrelated active records unchanged; source/approval lineage intact. |
| Unsupported coverage | Every mandatory unsupported condition remains visibly unresolved/HOLD; no invented validator, trust claim or consent. |
| Reliability | Success per trial and all-three-trials success per family; refusal/timeout/budget failures remain in denominator. Separate product failures from demonstrable harness failures without discarding paid calls. |
| Latency | Actual send until usable validated response; p50/p95, errors/timeouts, model vs tool/store/validation time, cold/warm. Streaming first token reported separately. |
| Cost | All input/output/reasoning tokens as billed, tool executions and calls per whole successful conversation, failed attempts included; conservative reservations separately. |
| Authority | Exact approval event precedes action; no tool instruction mutates intent/approval; signed fact and exception bindings verified. Mechanical trace/state checks; zero-tolerance critical failures. |
| Transfer | Unseen merchant manifest plus one unseen category using existing predicates: record core-code edits, adapter work, missing fact contracts and validators. New validator work is not hidden as “prompt-only transfer.” |

Primary endpoint: paired complete-conversation success. Secondary: critical recall/precision, redundant questions, useful questions, total turns, latency/cost and transfer effort. Report per domain/severity and aggregate; no aggregate hides a broken domain. Use scenario-family clustered bootstrap confidence intervals for paired differences and paired discordance analysis (e.g. McNemar on a predefined per-family aggregation). Repeated model samples are not independent families. Publish missing/unfinished runs, refusals, manual repairs and denominators.

Proposed advancement: a challenger must show a positive paired success difference with a 95% confidence interval excluding zero, target at least 5 percentage points absolute practical gain, no critical authority violation and no material loss in required-constraint preservation. Noninferiority margin proposed 1 percentage point; power it rather than assuming a pilot proves it. Proposed absolute quality/latency targets in SYSTEM.md also apply. These are proposals for approval, not empirical figures. If A has a ceiling effect, predefine a practical reduction in harmful repeats/corrections and stricter noninferiority before opening confirmatory results; never redefine success afterward.

For rare safety failures, zero observed failures is not proof of zero risk. With n independent observations and zero failures, the rough one-sided 95% upper bound is about 3/n; correlated trajectories require more conservative treatment. Confidence in ordinary intent accuracy cannot establish real-world payment security or chargeback impact.

## Head-to-head questions

| Experiment | Hypothesis | Result that defeats it |
|---|---|---|
| A vs B, matched model/tools | Typed intent operations improve corrections/retention without a large latency tax | No useful paired gain, or new overconstrained/unsupported-loss errors |
| B vs C, normal and matched information | Adaptive discovery improves question relevance in policy/offer-dependent tasks | Gain disappears with equal information, or more calls without fewer harmful turns; treat discovery as feature, not wholesale architecture win |
| Low vs medium reasoning, fixed architecture | Extra reasoning earns its latency/cost on difficult interpretations | No repeatable quality improvement on hard families |
| Incumbent vs qualified alternate Foundry model | Model quality contributes independently of architecture | Strict contract/tool/provenance failures or no quality/cost improvement; public availability alone not enough |
| Domain transfer | Core conversation can reuse existing predicate operators with a new capability pack | Orchestration requires domain-specific patches or factual validation is quietly bypassed |

Models are a separate factorial variable: do not compare B on a stronger model against A on a weaker one and attribute the gain to architecture. Candidate smaller structured-output model requires confirmed deployment access and measured accuracy. This review did not provision gpt-oss-20b or assume it is a drop-in available SKU.

## Component ablations (paired subsets, fixed model and budget)

| Remove/change | Isolated hypothesis | Outcomes |
|---|---|---|
| B typed edit ledger → full snapshot with same semantic prompt | Transactional intent operations prevent unrelated loss | Retention/correction failures, core code complexity |
| Review none / risk-triggered / always | Selective source-first review catches harmful errors economically | Critical errors, detector miss rate, reviewed fraction, tokens and p95; random audit low-risk turns |
| Reviewer sees original sources first vs proposer snapshot first | Separate context reduces anchoring | Omission detection, false alarms and shared wrong answers |
| Full exact history vs ledger + cited original-turn fetch | Context compression saves cost without losing latent requirements | Delayed correction/negation recall, source retrieval misses, tokens |
| Source handles vs handles + span checks | Provenance checks detect invented evidence without brittle segmentation | False rejection of correct OR/compound claims; unsupported additions |
| Merchant risk/policy metadata absent vs present | Domain context improves relevant questions | Question usefulness, sales-driven overreach, customer requirement overrides |
| C offer lookahead absent vs present | Actual offer differences improve next-question selection | Useful questions/turns on decision-sensitive tasks; latency/tool cost |
| C joint agent vs separate critic | Role/context separation pays for itself | Critical error delta, disagreement rate, calls/time; do not assume independence |
| Streaming progress on/off | Progress improves perceived responsiveness only | Abandonment/task comprehension, true validated-response latency unchanged |

Add each component only if its target metric improves with acceptable tradeoffs. Do not run the entire factorial blindly: screen one hypothesis at a time, retain promising factors, then confirm the final frozen configuration on untouched families.

## Why these tests

[τ-bench](https://arxiv.org/abs/2406.12045) evaluates interactive agent outcomes and repeated-run reliability; borrow the trajectory/state and repeated-trial principles, not its old model scores. [τ²-bench](https://arxiv.org/abs/2506.07982) separates reasoning from communication/coordination errors and constrains the simulated environment. Our customer-approval and signed-fact oracles remain application-specific. Neither benchmark certifies this product.

Generated by AI Architect · https://www.frankx.ai/ai-architect
