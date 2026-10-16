# Independent architecture review — Intent Judge

2026-10-16 · fresh verifier context · source commit `ef4fc34484cf5432153a9ad423165625202a2bc8`

## What is unowned

The evaluation plane is not yet owned by an executable adapter or a semantic judge. The proposed `06-evals/cases.jsonl` is designed but unexecuted, and `evals/scoring.py:L318-L319` defines a generic question as a question with no typed field and a novel key. That proxy cannot establish that a question is relevant, decision-changing, or non-redundant. The 616 passing tests are offline deterministic regression evidence; they do not measure live trajectory quality, model variance, or question utility.

Economics and operations are also open. `prices.json` deliberately has null Azure token rates, the real remaining allowance was not read, and no production on-call, recovery, or durable runner has been exercised. Component roles in `architecture.json` are proposed design owners, not assigned production ownership. These are unresolved lifecycle gates, not reasons to invent a winner.

## The four decisions

1. **Model call seam — DEFERRED.** The incumbent has multiple SDK call sites: `app/ai_pipeline.py:L845` constructs an `OpenAI` client; `app/foundry_client.py:L75` constructs `AzureOpenAI`; and `app/foundry_client.py:L143` constructs another `OpenAI` client for explanations. The two architecture pointers prove two seams, but they do not prove a single provider boundary. This leaves routing, fallback, caching, and spend attribution unowned. Keep the incumbent model fixed for A/B/C comparisons until a controlled adapter change is approved.

2. **Orchestration shape — incumbent bounded path, replacement OPEN.** `app/ai_pipeline.py:L1102` enters `_run_adaptive_pipeline`; the current fast path is sequential and can add a review call when a read-only observation or diagnostic requires it (`L1250-L1310`). `app/main.py:L526` is only the unsupported-list merge; the actual revision merge and compare-and-swap check are at `L523-L547`. A is therefore a bounded incumbent with known snapshot-reconciliation risk. B and C are designs only. A typed ledger may improve correction retention, but it does not make model edits semantically true; C adds information acquisition and a second failure surface. Do not mark the replacement loop decided before paired trajectories.

3. **Trust boundary — MADE for the current synthetic incumbent, unverified for production.** Customer evidence is placed in source fields at `app/ai_pipeline.py:L749` and the exact source catalogue at `L763`; tool observations and merchant metadata are separate payload fields at `L814` and `L822`. Approval requires exact revision/digest at `app/main.py:L609-L610`, and purchase rechecks the offer, exceptions, and block status at `L741-L751`. This satisfies the designed boundary for the current read-only tool surface. It does not prove semantic entailment, commercial issuer trust, real customer identity, or prompt-injection resistance under live tools. External flight discovery is explicitly unsigned and synthetic VI identities remain a demo boundary.

4. **Long-run home — UNMADE.** `vercel.json:L5` sets a 90-second function ceiling; the incumbent also has provider/tool timeouts and a bounded reservation ledger beginning at `app/store.py:L319`. No measured longest live run, deployed ceiling confirmation, timeout recovery, or C durable runner exists. Ordinary A turns may fit the current function, but that is an assumption until measured. Keep C's durable-runner choice conditional on measured deadline/recovery needs.

## Unowned planes

- **Evaluation:** no live adapter for the new trajectory JSONL; no blinded semantic question adjudication; no sealed final holdout.
- **Economics:** applicable Azure rates, current balance, and cost per successful conversation are unknown. B's lower-cost direction is a hypothesis; B can require a second model call where A normally uses one.
- **Operations:** proposed roles exist, but no named on-call backup, recovery SLO, rollback rehearsal, state migration plan, or C runner is exercised.
- **Observability:** traces are proposed, but retention, redaction, sampling, and a production owner are unresolved.
- **Tools/context:** C's discovery path would add remote tool and policy inputs; merchant identity, provenance freshness, egress scope, and failure recovery require implementation and adversarial trials.

## Evidence pointer audit

Several documentation pointers resolve to a nearby symbol rather than the claimed operation. They must remain recorded as failed evidence until corrected by the artifact owner:

| Pointer | Re-derived line | Result |
|---|---|---|
| `app/ai_pipeline.py:L732` | Function signature for `call_json`; payload assembly starts at L740 | FAIL for the claim that this line proves all context reaches the model |
| `app/ai_pipeline.py:L1102` | Function entry/docstring, no exit condition on the line | FAIL as proof of bounded orchestration |
| `app/main.py:L526` | `merge_unsupported(...)` only; revision merge is L531-L547 | FAIL as proof of snapshot reconciliation |
| `app/vi_adapter.py:L114` | `verify` function entry; chain verification call is L117 | FAIL as proof that the line verifies the chain |
| `tests/test_adaptive_quality.py:L52` | Test name; the eight-case assertion is L54 | FAIL as proof of the count on the cited line |
| `app/ai_pipeline.py:L771` in `05-trust-boundary.md` | Candidate adaptive-plan field, not source catalogue | FAIL; actual catalogue assignment is L763 |
| `app/ai_pipeline.py:L817` in `05-trust-boundary.md` | Closing parenthesis of tool payload assignment | FAIL; assignment begins at L814 |
| `app/ai_pipeline.py:L826` in `05-trust-boundary.md` | `elif merchant_context is not None` branch | FAIL for the adaptive merchant field; assignment begins at L822 |
| `app/ai_pipeline.py:L846` in `05-trust-boundary.md` | Client timeout continuation | FAIL for the system prompt; the call uses `system_prompt` at L850 |
| `vercel.json:L6` in `SYSTEM.md` | `includeFiles`, while `maxDuration` is L5 | FAIL for the 90-second ceiling claim |

The remaining endpoint/configuration pointers resolve to the named route or setting, but route decorators alone do not prove their downstream authority checks. Those checks are at `app/main.py:L609-L610` and `L741-L751`, not at the decorator lines.

## Candidate challenge: A versus B versus C

A is a credible control and is stronger than the recommendation implies on operational maturity: it already has a bounded adaptive path, source-separated inputs, read-only tools, revision checks, exact approval, signed synthetic facts, and deterministic purchase checks. It also has 616 offline tests. Its central weakness is the reconstructed snapshot and semantic repair seam, which is a real reason to test B, but a ledger cannot repair a model that misreads a customer clause. A should remain a fully instrumented arm, not merely a migration baseline.

B has a concrete production-shaped hypothesis: typed add/replace/retract operations can reduce unrelated field loss and make stale revisions explicit. The added reducer and ledger also introduce schema/version/provenance complexity, and the model still decides the semantic edit. B therefore earns a dev-only experiment, not a production recommendation. Its max-two-call cap is not evidence of lower cost than A's usual one-call fast path. Require a matched-information A/B comparison and an ablation that replaces typed edits with a full snapshot under the same prompt and model.

C has the highest possible upside only for tasks where policy or offer facts genuinely change the next question. MCP and Microsoft Agent Framework documentation establish transport/workflow capabilities; they do not establish better intent accuracy. LangGraph-style persistence can provide checkpoints, but it adds operational state and replay obligations. C should be a narrow challenger on decision-sensitive discovery cases, with a no-discovery and matched-information control. A general C rollout is defeated if added observations only increase calls, latency, injection exposure, or tool failures without improving useful questions or complete trajectories.

The cited primary sources support these boundaries: [Azure structured outputs](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs?view=foundry-classic) describe schema-constrained responses, not semantic entailment; [MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) describe discovery and schemas while treating annotations as untrusted unless the server is trusted; [Microsoft Agent Framework](https://learn.microsoft.com/en-us/agent-framework/overview/) and [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence) describe workflow/session/checkpoint primitives, not product quality; and the pinned [VI constraints](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/spec/constraints.md) leave unknown open-mandate constraints rejected until an evaluator exists. No source supports B's superiority claim.

## Threshold and experiment corrections

The proposed **95% exact required-constraint preservation** boundary is underpowered as a release floor for mandatory purchasing meaning. A 5% miss allowance can include a silent loss of a high-impact condition. Keep 95% as an exploratory aggregate target if desired, but require all of the following before any release decision: zero silent loss or unauthorized action on critical mandatory cases; 100% preservation on the predefined critical subset in the tested sample; non-inferiority to A within a predeclared 1 percentage-point margin on all required predicates; and a confidence analysis that treats each scenario family, not repeated model samples, as the unit. Any unsupported mandatory condition must remain HOLD even when a human later repairs it.

The screening design of 12 families × 3 arms × 2 repeats (72 conversations) is useful for instrumentation and failure discovery, but it has only 12 independent family units. Two repeats do not provide 24 independent families. It cannot by itself establish a 5-point gain or a 95% interval excluding zero. The confirmatory plan should be sized from paired family-level discordance and cluster variance before collection, with a fixed endpoint and no peeking. The exposed JSONL must not be treated as a final holdout; generate genuinely new hidden families and keep old eight cases as regression tests.

Question utility requires semantic adjudication. The current scorer's `generic_question` test at `evals/scoring.py:L318-L319` checks novelty and absence of a typed field, so it can accept a novel but useless question. Use blinded raters plus state-aware deterministic checks; report repeated-question rate, decision-changing utility, and rater disagreement. Do not let a generic-question proxy or a human repair count as an AI success.

## Fix first

Keep the recommendation conditional: instrument A, then run a metered, dev-only A/B ledger experiment with the corrected critical-safety threshold and an independently powered family-level design. Only test C on scenarios where additional capability/policy/offer information can affect the decision, and retain the matched-information C control. Do not implement or promote either challenger before the user approval requested in `architecture.json`; economics, live evals, operate, and verify remain unresolved.

## Verification verdict

**gate.verify: FAIL.** The architecture tree was inspected in a fresh context. Several evidence pointers are imprecise, the trajectory adapter has not been implemented, and live quality, economics, and operation remain unmeasured. The existing offline test result is reproducible as 616 passing tests, but its wall time differed from the recorded 7.34 seconds (fresh run: 6.84 seconds) and it does not certify live accuracy.

Generated by AI Architect · https://www.frankx.ai/ai-architect
