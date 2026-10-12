# AI / conversation delivery

Freshly reverified October 12, 2026 at 13:37 EDT, ahead of the 13:41 offline feature target and 14:00 feature freeze.

- Worktree: `/Users/victor/Nueva-Generacion/.worktrees/devin-ai-conversation`
- Branch: `devin/ai-conversation`; base: `f9848f13a369d5ac4210a4e6fa3f5e45b9fc8063`.
- Implementation commit: **`6d97a3ffd3a6cec8a8dea211f92f20b9a2f06582`**.
- This report is a separate documentation commit after that implementation commit. Integrate the implementation commit; optionally bring its subsequent report commit too. Neither was merged or pushed.
- Preserved and completed the interrupted worker's saved edits rather than restarting or discarding them.

## Status and scope

**Usable offline AI/conversation feature, verified locally. Live Foundry is NOT proven.** No cloud authentication, configuration, inference, billable call, SDK install, or prototype-environment change was performed. No shared models, VI adapter, rules, evidence builder, API, store, frontend, or other worker files were edited. Existing code comments were preserved.

**Delivery status: DONE_WITH_CONCERNS. Live flag: NOT_TESTED / BLOCKED; no live attempt. Offline observed `llm_fallback=True`; live fallback flag and latency remain unobserved.**

Implementation commit `6d97a3ffd3a6cec8a8dea211f92f20b9a2f06582` changed only `app/foundry_client.py`, `app/conversation.py`, `tests/test_foundry_client.py`, `tests/test_conversation.py`, `tests/test_ai_boundaries.py`, and `requirements-victor.txt`. This continuation changes and commits **only this report**, preserving the existing implementation commit without amendment.

Ownership was freshly verified against `docs/handoff/sessions/01-ai-conversation.md:3-7`. Initial `git status --short` showed only `?? docs/handoff/results/ai.md`; branch was `devin/ai-conversation`, HEAD was the exact implementation SHA above, and both tracked and staged diffs were empty. No peer implementation was inspected or edited in this continuation; no other worktree was written.

## Stable integration contracts

```python
from app.foundry_client import extract_requirements, explain, evidence_narrative
from app.conversation import conversation_turn, record_approval, trace_for_requirements

extract_requirements(text: str, today: date | str | None = None) -> ExtractResult
explain(decision: Decision, req: ApprovedRequirements) -> ExplainResult
evidence_narrative(packet: EvidencePacket) -> str | None
conversation_turn(conversation_id: str | None, text: str, today=None) -> dict
record_approval(conversation_id: str, req: ApprovedRequirements) -> dict
trace_for_requirements(requirement_set_id: str) -> dict
```

- `ExtractResult` stays `draft_requirements`, `questions` (at most two), `notes`, `llm_fallback` (`app/foundry_client.py:262,502`). Drafts have no approval, decision, purchase, exception, or category fields.
- Conversation returns `conversation_id`, timestamped `turns`, `draft_requirements`, `field_sources`, `questions`, `notes`, `llm_fallback`, `approved=False` (`app/conversation.py:24,95`). Field sources contain `turn_id`, literal `quote`, and separate `interpretation`, including explicit clearing to null.
- Call `record_approval` only from the backend's explicit traveler-confirmation action. It requires `approved_by_traveler=True`, a complete resolved draft, and exact equality with the displayed draft; requirement ids cannot be reused (`app/conversation.py:63`). Returned/exported traces are deep copies. Later draft changes cannot rewrite earlier approval snapshots.
- The trace contains `trace_status=application_record_not_user_signed_transcript` and an `approval` object with requirement id, approved_at and the complete approved requirements. Attach this beside/additively to the existing flat EvidencePacket API; do not replace Josue's flat receipt response with an incompatible wrapper.
- An eventual shared `category='flight'` remains in the approved snapshot but is deliberately excluded from private draft validation and comparison. Compatibility is tested with an ApprovedRequirements subclass (`tests/test_ai_boundaries.py:264`). The new primary `urn:intent-judge:requirements` belongs to integration/adapter; this feature changes no VI namespace.
- Manual UI edits must be reconciled into the displayed conversation draft before linking a matching approval trace. Do not silently attach a trace to different approved fields. Unknown conversations/requirement ids raise KeyError; invalid approval/message input raises ValueError for the API to translate.
- `explain` remains deterministic/display-only and always reports `llm_fallback=True`; it preserves backend facts and prevents accepting an exception for BLOCK or missing approval (`app/foundry_client.py:523`). It does not call the live model.
- `evidence_narrative` is deterministic/display-only, preserves code's responsibility and reason code, omits injected free text, and ends `Final decision: dispute analyst.` (`app/foundry_client.py:537`). The demonstrated narrative is 58 words; tests cover every responsibility enum and the <=120-word limit. It mutates no packet fields.

## Preserved fixes and added boundaries

- Context-sensitive bare origin (`JFK`) and terse budget replies; explicit route labels can reverse word order (`app/foundry_client.py:131`; `tests/test_conversation.py:69,96`; `tests/test_foundry_client.py:111`).
- Negated nonstop, refund/cabin negation, optional preference clearing, ambiguous/new corrections invalidating the old affected field without erasing unrelated fields (`tests/test_foundry_client.py:88,101`; `tests/test_conversation.py:85,109`).
- Invalid/excessive counts remain reviewable; unresolved passenger counts continue to block approval after unrelated chat until corrected (`tests/test_conversation.py:140`). Very long numeric input cannot crash integer conversion (`tests/test_foundry_client.py:118`).
- Approval compares normalized zero-second clocks correctly, including arrival deadlines, but never truncates unreviewed nonzero seconds into equality (`tests/test_conversation.py:158,166`).
- Private Pydantic schemas forbid extra fields, string/bool integer coercion, invalid dates/counts, numeric window timestamps, invented sources, assistant sources, and missing provenance for changed fields (`app/foundry_client.py:38,275,479`; `tests/test_ai_boundaries.py:34-149`). A literal quote still does not prove semantic interpretation; traveler review remains mandatory.

## Lazy Foundry transport: code wired, live untested

`app/foundry_client.py:371-521` lazily imports the official `azure-ai-projects`/identity SDKs only for an explicitly enabled live attempt. It uses AIProjectClient, PromptAgentDefinition, FunctionTool, and the project's OpenAI Responses client; no client/network initialization occurs on module import.

- Defaults to offline when MOCK_LLM is absent; `MOCK_LLM=1` bypasses transport completely.
- Existing-version live mode requires `MOCK_LLM=0`, `FOUNDRY_LIVE_ENABLED=1`, an HTTPS `FOUNDRY_PROJECT_ENDPOINT` on `*.services.ai.azure.com` with `/api/projects/` in its path, and a configured `FOUNDRY_AGENT_VERSION`. Leave `FOUNDRY_CONFIGURE_AGENT` unset for read-only reuse. Historical `AZURE_OPENAI_*` variables do not enable this project-agent transport; it uses Azure CLI credentials rather than an API key.
- `FOUNDRY_AGENT_NAME` defaults to `intent-judge-assistant`. Existing versions are fetched and rejected unless their instructions, one read-only function schema, and absence of skills match the application's definition. The known blank version 1 is not silently treated as working.
- Only after separate authorization for remote configuration, the optional `FOUNDRY_CONFIGURE_AGENT=1` plus `FOUNDRY_MODEL_DEPLOYMENT` permits creating a new immutable version under that same agent name. Its version is cached per process/configuration. This configuration path was exercised only with external SDK doubles, never against Azure.
- Only local `search_demo_offers` is allowlisted. It validates query arguments, requires explicit supported route/date context, reads existing synthetic fixtures, retains offer_ids, and returns bounded summaries with `synthetic=True`, `trusted_for_purchase=False` (`app/foundry_client.py:283,315,438`). It never supplies verified checkout data or approves anything.
- Maximum one catalog invocation and two model responses per turn; second response disables tools. SDK retries are disabled, response calls use <=4-second request timeouts, Azure CLI subprocess authentication uses <=3 seconds, and a 12-second checked budget applies across steps. Hard wall-clock cancellation behavior across SDK authentication/HTTP phases is not live-verified and must not be advertised as a measured SLA.
- Invalid shape/quotes, unknown/repeated tools, refusal, incomplete output, overlong context/output, configuration/auth failure and timeouts visibly fall back with `llm_fallback=True` and an offline note. Exception details/secrets are not returned.
- No temperature setting or assumed strict server JSON support is imposed. All output is validated locally. Requirements now specify `azure-ai-projects>=2.8,<3` to match the inspected SDK API.

### Exact pending dependencies — do not claim installed SDK equals live success

The existing runtime has azure-ai-projects **2.8.0**, azure-identity **1.26.0**, openai **3.29.0**, Pydantic **2.14.1**. Local SDK signatures/models were inspected and constructed without network.

**No `az` executable is available on the current PATH.** This transport deliberately uses bounded AzureCliCredential, so a user-approved Azure CLI installation/availability and authenticated tenant/project login are needed before live access. Browser login is not an SDK credential. None of FOUNDRY_LIVE_ENABLED, FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_AGENT_VERSION, FOUNDRY_MODEL_DEPLOYMENT, FOUNDRY_CONFIGURE_AGENT was set when checked (only presence booleans were printed, never values/secrets).

The project endpoint from the handoff is `https://victor-lead-foundry-20261012.services.ai.azure.com/api/projects/lead-team`; this is not the resource's Azure OpenAI endpoint. Project permission, actual deployment name/quota, gpt-oss-120b Responses/JSON/tool capabilities and API compatibility remain unverified. The persisted blank agent needs an authorized configured version. Configuration and any synthetic live inference/latency test require Victor's further consent. **Live latency: not measured; live fallback flag: not observed.**

## Actual proof and commands

All commands ran from this feature worktree using the pre-existing prototype Python, without changing that environment:

```sh
MOCK_LLM=1 PYTHONDONTWRITEBYTECODE=1 ../victor-rules/.venv/bin/python -m pytest -q -p no:cacheprovider
# Fresh full rerun on implementation HEAD 6d97a3ffd3a6cec8a8dea211f92f20b9a2f06582:
# 123 passed in 0.54s; started 2026-10-12 13:37:29 EDT; exit 0.
# Bytecode and pytest cache writes disabled; no live Azure calls.

# Earlier worker proof retained, not represented as fresh reruns:
MOCK_LLM=1 PYTHONDONTWRITEBYTECODE=1 /Users/victor/Nueva-Generacion/.worktrees/victor-rules/.venv/bin/python -m pytest -q
# 123 passed in 0.64s at 13:33:34 EDT

MOCK_LLM=1 PYTHONDONTWRITEBYTECODE=1 /Users/victor/Nueva-Generacion/.worktrees/victor-rules/.venv/bin/python -m pytest -q tests/test_foundry_client.py tests/test_conversation.py tests/test_ai_boundaries.py
# 107 passed in 0.59s after implementation commit

git diff --check
# earlier worker check passed

git diff --cached --check
# fresh staged report check passed; staged path is only docs/handoff/results/ai.md
```

Initial preserved baseline was 56 passed. Final full suite is 107 AI/conversation/boundary cases plus 16 unchanged VI adapter cases. Tests replace only external model transport/SDK responses and exercise real extraction, provenance, catalog, approval and narrative code. Simulated model success is NOT live success.

A fresh-process offline probe in this continuation reverified SDK versions above, `az available: False`, and presence=False for all five Foundry opt-in/configuration variables listed above, without printing their values. It reported `SDK imported at module load: False`, `Offline usable: True`, `llm_fallback: True`, and `Live attempted: False`. The previously recorded local demo harness produced:

1. `Get me NYC to Florida cheap next week.` -> destination and exact-date follow-ups.
2. `Orlando on October 20, nonstop, morning, under $300.` -> NYC airports, MCO, 2026-10-20, 06:00-12:00, max_stops=0, max_total_cents=30000, USD, passengers=1, unstated cabin/refundability null; approved=False, llm_fallback=True.
3. Explicit record_approval with the matching fixture -> immutable copied application trace and exact original quotes.
4. A **provided synthetic HOLD**, not rules execution, was explained as `You requested nonstop; this offer has 3 connections.`; a supplied synthetic evidence packet yielded the 58-word offline narrative.

Other commands: git status/branch/base/diff inspection, clock checks, SDK signature/model introspection, SDK version and configuration-presence checks, safe local CLI-availability check, and scoped git add/commit. No fetch, merge, push, destructive operation, server, real payment, cloud smoke test, or cloud configuration.

## Integration owner must still verify

This worktree does not contain the other workers' real rules/evidence/routes, so its suite is **not** proof of the assembled app's 12 scenarios or purchase enforcement. Assemble Josue's current code with the real workers, preserve the flat check/receipt contracts, and verify B -> HOLD -> purchase 409 -> exact offer-specific acceptance -> purchase 201 -> receipt, plus tamper -> BLOCK. A bare OK must never be sufficient exception consent.

In-memory conversation traces are neither durable audit logs nor user-signed transcripts; exceptions are not new signed VI credentials. The parser is conservative demo vocabulary, not general NLP. One traveler, USD for dollar amounts, and the morning interval are visible review defaults/interpretations, not evidence of unstated preferences. Keep the offline badge visible. No live Foundry, production service, certification, liability protection, or universal-category claim is justified by these results.
