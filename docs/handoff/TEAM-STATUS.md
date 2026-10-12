# Intent Judge — coordination and conflict-avoidance handoff

Updated October 12, 2026, 13:36 America/New_York. Coordinator-owned file; implementation owners update their own result files, not this file. This is an incremental delivery record, not permission to overwrite another owner's work.

## Read first

Read `AGENTS.md`, `DEVIN-HANDOFF.md`, the latest `JOSSUE-UPDATES.md` supplied by Victor, this file, and your feature brief/result before making changes. The latest Josue update supersedes old namespace/scaffold claims: the primary VI extension is `urn:intent-judge:requirements`; existing models retain flight fields plus `category='flight'`. Flights are the only implemented category.

Victor requests small, understandable commits plus Markdown contracts. Commit one coherent implementation/fix/test milestone at a time. Commit updated result proof separately where recording a previous SHA. Do not squash, amend, reset, revert others, or force-push. No push or shared-main merge is currently authorized. All commits are local until Victor explicitly requests sharing them remotely.

## Workspace and exclusive ownership

Base prototype: `f9848f13a369d5ac4210a4e6fa3f5e45b9fc8063` on `victor/rules`; retain it unchanged. Integration lives on `devin/api-integration`, not local `main`. Each feature has a separate worktree under `.worktrees/`.

| Owner/session | Branch / worktree suffix | Exclusive implementation and test files | Result handoff |
| --- | --- | --- | --- |
| AI Conversation | `devin/ai-conversation` / `devin-ai-conversation` | `app/foundry_client.py`, `app/conversation.py`, `tests/test_foundry_client.py`, `tests/test_conversation.py`, `tests/test_ai_boundaries.py`, `requirements-victor.txt` | `docs/handoff/results/ai.md` |
| Rules & Consent | `devin/rules-consent` / `devin-rules-consent` | `app/rules_engine.py`, `tests/test_rules_engine.py`, `tests/test_purchase_eligibility.py` | `docs/handoff/results/rules.md` |
| Vendor Evidence | `devin/vendor-evidence` / `devin-vendor-evidence` | `app/evidence.py`, `tests/test_evidence.py` | `docs/handoff/results/evidence.md` |
| API Integration | `devin/api-integration` / `devin-api-integration` | `app/main.py`, `app/store.py`, `tests/test_enforcement.py`, `tests/test_scenarios.py`, `tests/test_injection.py`; sole designated editor for bounded shared-model/VI-adapter integration fixes | `docs/handoff/results/integration.md` |
| Josue | `origin/jossue/build` snapshot `4a9a4f0` | ALL `web/` files and frontend/user flow | Latest team update |
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
- `6d97a3f`: AI/conversation parser, provenance and bounded Foundry transport implementation; review/result finalization pending at this checkpoint.

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

Current next steps: finish/review evidence fixes; finish/review AI; merge exact approved tips into integration; run full suite without acceptance skips; verify the real UI in a browser; record final proof here and in owner results. Do not use `scripts/dev_server.py` (fake engine) as the real demo.

## Runtime and honest limits

Existing usable Python: `/Users/victor/Nueva-Generacion/.worktrees/victor-rules/.venv/bin/python` (3.12). Run it with the intended FEATURE/INTEGRATION workdir; do not install into or change the saved prototype environment.

```sh
MOCK_LLM=1 PYTHONDONTWRITEBYTECODE=1 /Users/victor/Nueva-Generacion/.worktrees/victor-rules/.venv/bin/python -m pytest -q -p no:cacheprovider
```

Live Foundry authentication, actual inference/tool execution and latency remain unproven. No authorized live cloud write or model smoke has occurred in this coordination session. Do not claim SDK installation or the existing blank agent proves live integration. Keep offline mode reliable.

Synthetic keys/offers only; purchases simulated; storage in-memory. Conversation traces and exceptions are unsigned application records, not new VI authorizations. Only deterministic rules decide. Evidence recommendations are advisory; final authority is the dispute analyst. No certification, liability guarantee, delivered-flight proof, or universal-category support is claimed.
