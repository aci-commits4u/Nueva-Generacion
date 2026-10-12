# Intent Judge — coordination and conflict-avoidance handoff

Final offline MVP delivery: October 12, 2026. Feature work is frozen; only demo-blocking fixes should be considered. Coordinator-owned file; implementation owners update their own result files, not this file. This is an incremental delivery record, not permission to overwrite another owner's work.

## Read first

Read `AGENTS.md`, `DEVIN-HANDOFF.md`, the latest `JOSSUE-UPDATES.md` supplied by Victor, this file, and your feature brief/result before making changes. The latest Josue update supersedes old namespace/scaffold claims: the primary VI extension is `urn:intent-judge:requirements`; existing models retain flight fields plus `category='flight'`. Flights are the only implemented category.

Victor requests small, understandable commits plus Markdown contracts. Commit one coherent implementation/fix/test milestone at a time. Commit updated result proof separately where recording a previous SHA. Do not squash, amend, reset, revert others, or force-push. Victor explicitly authorized publication to the NEW `victor/build` branch at 13:41 EDT. Push reviewed incremental checkpoints there using normal fast-forward updates only. Do not push or merge shared `main`, force-push, or overwrite an existing unrelated remote branch. Earlier checkpoint notes describe their historical local-only state; later publication records supersede that state.

## Workspace and exclusive ownership

Base prototype: `f9848f13a369d5ac4210a4e6fa3f5e45b9fc8063` on `victor/rules`; retain it unchanged. Integration lives on `devin/api-integration`, not local `main`. Each feature has a separate worktree under `.worktrees/`.

| Owner/session | Branch / worktree suffix | Exclusive implementation and test files | Result handoff |
| --- | --- | --- | --- |
| AI Conversation | `devin/ai-conversation` / `devin-ai-conversation` | `app/foundry_client.py`, `app/conversation.py`, `tests/test_foundry_client.py`, `tests/test_conversation.py`, `tests/test_ai_boundaries.py`, `requirements-victor.txt` | `docs/handoff/results/ai.md` |
| Rules & Consent | `devin/rules-consent` / `devin-rules-consent` | `app/rules_engine.py`, `tests/test_rules_engine.py`, `tests/test_purchase_eligibility.py` | `docs/handoff/results/rules.md` |
| Vendor Evidence | `devin/vendor-evidence` / `devin-vendor-evidence` | `app/evidence.py`, `tests/test_evidence.py` | `docs/handoff/results/evidence.md` |
| API Integration | `devin/api-integration` / `devin-api-integration` | `app/main.py`, `app/store.py`, `tests/test_enforcement.py`, `tests/test_scenarios.py`, `tests/test_injection.py`; sole designated editor for bounded shared-model/VI-adapter integration fixes | `docs/handoff/results/integration.md` |
| Josue | Latest fetched `origin/jossue/build` snapshot `67c0037`; `4a9a4f0` was the initial integration checkpoint | ALL `web/` files and frontend/user flow | Latest team update |
| Coordinator | Integration worktree, serialized documentation commits | This `docs/handoff/TEAM-STATUS.md` only | This file |

Shared models, fixtures and adapter are contracts, not freely editable. Request bounded changes through the integration owner. Never edit a peer module to make integration tests pass. Read Josue's newest branch/current work before any shared API changes. Do not send teammates messages without Victor's instruction.

## Incremental commits already available

- `b5701ad`: integrated Josue's current branch `4a9a4f0` into the isolated integration branch, preserving the Victor prototype.
- `ffc441e`: deterministic rules and exact consent implementation/tests.
- `c802ab2`: rules proof and three-value purchase contract.
- `3ad5861`: evidence assembly and tests.
- `9745f79`: evidence result/contract. DO NOT integrate this old evidence tip: independent review found consent/timestamp defects, being corrected by its owner.
- `4f80aa9`: signed API enforcement, conversation approval and compatibility preparation.
- `df1d886`: merged reviewed rules `c802ab2` into the integration branch.
- `c003f4c`: proved real signed API core flow; receipt remains a missing dependency at this checkpoint.
- `6d97a3f`: AI/conversation parser, provenance and bounded Foundry transport initial implementation.
- `8aebb1d` / `3863ee1`: independently reviewed evidence consent, chronology and tamper-diagnostic fixes plus handoff.
- `dfa2f9c`: merged reviewed evidence; `606d513`: merged latest Josue snapshot `67c0037` unchanged.
- `82d7a1b`: published green 407-test receipt integration checkpoint.
- `089484c`, `c7b80c8`, `a3881c3`: incremental reviewed AI count/budget and route-correction fixes; final feature handoff `b7e89e0`.
- `2955efd`: merged exact reviewed AI tip, assembling all four features.
- `42cae24`: bounded API whitespace rejection with preserved literal evidence words.
- **`68e52e3`**: final four-feature code/test/proof checkpoint, published to `origin/victor/build`; all 515 tests pass. Subsequent coordinator documentation commits do not change the tested product code.

Use exact reviewed SHAs, not a moving branch name. Only integration merges peer features into its branch. Review the resulting tree and rerun tests after each merge. Feature worktrees retain their own history; do not delete them during the demo window.

## Fixed cross-feature contracts

```python
extract_requirements(text, today=None) -> ExtractResult
explain(decision, req) -> ExplainResult
conversation_turn(conversation_id, text, today=None) -> dict
record_approval(conversation_id, req) -> dict
trace_for_requirements(requirement_set_id) -> dict
evaluate(req, offer_or_none, vi_chain_valid, merchant_signature_valid) -> Decision
can_purchase(decision, exceptions) -> tuple[bool, str, list[str]]
build_packet(purchase, dispute_claim, decision, req, offer, exceptions, narrative=None) -> EvidencePacket
evidence_narrative(packet) -> str | None
```

- `/api/check` stays `{decision, offer, explanation, vi_errors}`.
- `/api/disputes` stays FLAT EvidencePacket JSON. `conversation_trace` is an additive root attachment, never an incompatible wrapper.
- Conversation endpoint: `POST /api/conversation/turn` with `{text, conversation_id?}`. Explicit approval is a separate `POST /api/intent/approve` with `{conversation_id?, draft_requirements, source_text?}`. A conversation-backed approval must equal the displayed reviewed draft.
- The existing UI remains stateless-compatible. It does not yet call the new conversation route or display the trace. Josue owns that frontend follow-up; backend/API tests can exercise the richer conversation path independently.
- Josue's exact exception wording is `I accept 3 connections (STOPS) on offer OFFER-B-3STOP`; multiple specific clauses are joined with `; `. Only server-derived exact decision/hash/check/value/timestamp records count. Bare OK, denials, AI quotations and partial coverage cannot authorize purchase or be portrayed as informed consent.
- BLOCK occurs before reading untrusted offer data and may carry an empty decision hash. Never patch a hash onto BLOCK to bypass enforcement. A blocked attempted purchase has no purchase id; `/api/disputes` is for existing simulated purchases. Integrity-diagnostic packet tests are not actual purchases.

## Verification status at this checkpoint

Original prototype freshly verified: 33 passed. Rules feature freshly verified: 208 passed. Original evidence feature: 124 passed, but independent review found important defects; a passing unit count is not approval to merge it.

Integration at `c003f4c`: all 12 real signed HTTP scenarios pass; A PASS; B HOLD with THREE connections; purchase409; exact existing UI acceptance; simulated purchase201; tampered L2/forged merchant BLOCK and purchase409. Full suite is NOT green yet: receipt-dependent tests fail because reviewed evidence is not merged. See integration result for exact commands/counts and distinctions from the 13 preserved fake wiring tests.

**All four features are assembled and published to `origin/victor/build` at code checkpoint `68e52e37cfb407c1b32b2a73a31339a1b8fb5387`.** Fresh coordinator verification: **515 passed, zero failures/skips/deselections**. The integration owner separately verified 502 tests excluding the 13 explicitly isolated fake wiring cases, plus 62 real enforcement/scenario/injection cases and all 12 signed HTTP scenarios. Every feature has its own committed result Markdown and separate worktree history. Do not use `scripts/dev_server.py` (fake engine) as the real demo.

Final coordinator browser smoke after the AI merge passed via real HTTP: extraction200 with offline flag -> explicit approval200 -> B HOLD -> purchase409 -> initially unchecked exact STOPS consent200 -> purchase201 -> flat receipt200. Cardholder/Merchant/Issuer seats render, the new display-only offline narrative is populated, and final authority remains `dispute analyst`. Earlier browser proof also confirmed A PASS and both tamper BLOCK/purchase409 paths.

This is a tested OFFLINE demo, not live Foundry proof or a production audit. Victor's final instruction is to stop additional engineering and deliver: no further parser expansion, design changes, cloud setup, or new agent waves are part of this frozen MVP.

Fresh remote inspection at 13:41 found no existing `victor/build`; `origin/jossue/build` is now `67c0037` and `origin/main` is `7fe07bd`. The newer Josue delta changes frontend/docs/dev tooling only, not shared API/models/adapter contracts. It adds per-check unchecked consent, held-offer re-shopping, and a three-seat flat receipt. Its exception requests retain the same exact check-specific wording, one selected check per request. Only integration may merge that snapshot; nobody else should modify `web/`.

The live Uvicorn server uses the REAL `app.main:app`, `MOCK_LLM=1`, and `FOUNDRY_LIVE_ENABLED=0` at `http://127.0.0.1:8010`; it is not the development fake server. Coordinator rendered desktop verification at 1440x900 passed: request -> explicit approval -> B HOLD with four segments/three connections -> purchase409 -> exception modal initially unchecked/submit disabled -> exact checkbox consent200 -> simulated purchase201 -> flat receipt200 with Cardholder/Merchant/Issuer seats and `final_decision=dispute analyst`. Real browser tampered L2 and forged merchant each produced BLOCK/purchase409, with no segments trusted for forged merchant; A then produced PASS. Browser calls were real HTTP, not mocked.

### Josue-owned UI follow-ups (do not edit his files here)

- Mobile initial layout at 390x844 fits the viewport. The receipt dialog itself fits (358px content width), but the populated background checks table makes the document 428px wide on a 390px viewport. This is a 38px horizontal-overflow follow-up for Josue; desktop demo is verified. No web file was changed to hide it.
- The existing UI does not yet call `/api/conversation/turn` or render `conversation_trace`; full multi-turn original-quote evidence is supported/tested at the backend/API level, while the current UI uses editable stateless requirements.
- Inherited receipt copy such as 'The merchant delivered what it signed' should be read as demo framing, not authenticated delivery proof. The backend has no delivery-evidence contract and deliberately returns `unclear` for unsupported delivery allegations. Josue owns any copy correction; do not claim guaranteed delivery, no production integration burden, liability protection, or a dispute win.
- Favicon404 and expected purchase409 network entries appear in the browser console. No JavaScript exception was observed during the demonstrated flows. Keep expected refusal errors distinct from application failures.

Screenshots are local verification artifacts under ignored `.worktrees/.playwright-cli/`; not repo changes. Refresh/reset the demo after a development-server reload to avoid stale in-memory ids. The final browser verification used the frozen four-feature build after reload.

## Run and rehearse now

The working app is in `/Users/victor/Nueva-Generacion/.worktrees/devin-api-integration`, not the preserved root main checkout. The real server is already running at `http://127.0.0.1:8010`. For a restart, stop only that server first, then run from the integration directory:

```sh
MOCK_LLM=1 FOUNDRY_LIVE_ENABLED=0 ../victor-rules/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

A teammate should use the published `victor/build` branch, install `requirements-victor.txt` in their own Python 3.12 virtualenv, and keep `MOCK_LLM=1`. No credentials are needed for the offline demo. Do not run or merge over anyone's dirty main checkout.

Two-minute rehearsal: enter `NYC to Orlando Oct 20 nonstop morning under $300`; Clarify; Approve and sign; select B ($280, THREE connections); Buy is refused409; accept only the explicit Connections checkbox; Buy succeeds as a simulation; Dispute -> Intent Receipt. A ($260 nonstop) is the passing alternative. Optional `?dev` exposes actual tamper BLOCK toggles. Neither offer supports a fabricated savings story, and no real money moves.

## Runtime and honest limits

Existing usable Python: `/Users/victor/Nueva-Generacion/.worktrees/victor-rules/.venv/bin/python` (3.12). Run it with the intended FEATURE/INTEGRATION workdir; do not install into or change the saved prototype environment.

```sh
MOCK_LLM=1 PYTHONDONTWRITEBYTECODE=1 /Users/victor/Nueva-Generacion/.worktrees/victor-rules/.venv/bin/python -m pytest -q -p no:cacheprovider
```

## Authorized live follow-up — supersedes historical offline-only status

Victor subsequently authorized bounded live setup while leaving frontend ownership with Josue. Azure CLI 2.90.0 was installed in its separate uv tool environment and Azure login succeeded. The original `intent-judge-assistant` version1 was confirmed blank with zero tools. Version2 was created with the application's exact instructions and one read-only catalog tool; its definition validated successfully. No credentials were committed.

Actual agent-Responses attempts exposed two issues: obsolete `agent`/separate `instructions` request fields (HTTP400), then HTTP404 `DeploymentNotFound` despite the project listing `gpt-oss-120b`. The transport now uses `agent_reference` and does not override persisted instructions. Native agent-Responses compatibility remains unresolved for this deployment.

The bounded direct Chat Completions mode WORKS with real `gpt-oss-120b` inference. First response id: `19bfe6b870fe4a0a90007fdeeb9d59a7`, measured 1.715 seconds, asking Florida city and travel dates. Actual application extraction then returned validated `llm_fallback=false` in 4.289 seconds. Real HTTP extraction on port8011 also returned `llm_fallback=false`. This mode does not execute catalog tools; it uses the configured deployment directly, with application instructions and private JSON/provenance validation. Explanation and receipt narrative remain deterministic/display-only.

Real HTTP two-turn proof on8011: both turns reported live (no fallback), the completed draft had no unanswered questions, explicit approval200, real signed offer A PASS, simulated purchase201, receipt200 with BOTH original user messages and `final_decision=dispute analyst`. Prompt1: `Get me NYC to Florida cheap next week.` Prompt2: `JFK to MCO on 2026-10-20, nonstop, morning, under $300 USD, 1 passenger. No cabin or refundability preference.` The existing website reaches live inference through Clarify, but still uses stateless form approval; it does not yet provide a multi-turn chat or render the conversation attachment. Josue retains those UI tasks.

Live server is already running on `http://127.0.0.1:8011`; offline backup remains on8010. A teammate needs their OWN Azure CLI login; credentials do not transfer through Git. From the integration directory, the live startup is:

```sh
MOCK_LLM=0 FOUNDRY_LIVE_ENABLED=1 FOUNDRY_PROJECT_ENDPOINT=https://victor-lead-foundry-20261012.services.ai.azure.com/api/projects/lead-team FOUNDRY_AGENT_VERSION=2 FOUNDRY_MODEL_DEPLOYMENT=gpt-oss-120b FOUNDRY_API_MODE=chat FOUNDRY_CONFIGURE_AGENT=0 ../victor-rules/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8011
```

Fresh offline regression suite after the transport fix/direct-chat guards: **520 passed**. Guard tests reject incomplete, empty, refused and tool-calling chat responses; clients close and fallback remains visibly flagged. Every PASS/HOLD/BLOCK, approval, exception and responsibility rule is unchanged. Web files remain untouched.

Synthetic keys/offers only; purchases simulated; storage in-memory. Conversation traces and exceptions are unsigned application records, not new VI authorizations. Only deterministic rules decide. Evidence recommendations are advisory; final authority is the dispute analyst. No certification, liability guarantee, delivered-flight proof, or universal-category support is claimed.
