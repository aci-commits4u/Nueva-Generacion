# Devin handoff — verified state and shared contracts

Prepared October 12, 2026, around 1:05 PM ET. This document is a snapshot, not proof of future remote/team state. Codex is stopping after saving the prototype and the handoff. Do not rely on the prior chat being available.

## Product and purpose

**Intent Judge is a confirmation and evidence layer for agent-driven commerce.** Help merchants avoid misunderstood AI purchases before checkout, and trace a transaction back to what the customer said and explicitly authorized if a dispute occurs. Flight booking is the concrete demo, not the market boundary. Other transaction types would add category schemas and rules (size/returns, delivery, subscription terms). Those checks are not implemented today; do not market universal transaction support as a tested feature.

The key workflow:

1. Customer states a request in natural language.
2. A Microsoft Foundry assistant asks short, targeted follow-ups and can search a synthetic flight catalog through a read-only tool.
3. Show an editable structured draft with the original words/follow-up answers. AI interpretation stays separate from user words.
4. Customer explicitly confirms the snapshot. The Mastercard SDK signs these approved requirements into a VI user mandate.
5. Verify the merchant-signed offer and VI chain; deterministic rules compare it with approved fields.
6. Missing/deviating requirements pause checkout. Invalid signatures block it. The backend refuses purchase until the result is PASS or every eligible mismatch has specific, recorded acceptance for that exact offer hash.
7. Merchant/analyst evidence links original conversation, approved snapshot, signed offer, check results, and recorded exceptions.

Chat alone is not authorization. An AI summary cannot prove consent. A valid signature proves integrity/authenticity under the demo's keys, not that a flight was delivered or that a merchant will win a dispute. No Mastercard certification, legal-liability, or chargeback-reduction guarantee.

## People and collaboration

- Victor: research, AI/Foundry, backend/domain work, product/pitch direction.
- Josue (also spelled Jossue in conversation): frontend and user flow; he previously built shared models, fixtures, SDK adapter, and FastAPI scaffold. His published/unpublished work must be respected.
- Separate Devin sessions own AI/conversation, rules/consent, evidence, and API integration. The last is the integration owner. Workers are not alone in the codebase: never revert someone else's edits.
- Public models/fixtures/VI adapter are shared contracts. Request a bounded change through the integration owner before changing them. Do not send messages to Josue or others without Victor's explicit instruction.

## Git and runtime

Repository: `https://github.com/aci-commits4u/Nueva-Generacion`.
Main checkout: `/Users/victor/Nueva-Generacion`, local main at `76333ba` (ahead of origin/main by two commits at the snapshot).
Prototype checkout: `/Users/victor/Nueva-Generacion/.worktrees/victor-rules`, branch `victor/rules`.
Josue's published branch was fast-forwarded locally with:

```sh
git fetch origin
git merge --ff-only origin/jossue/build
```

The new Victor code is only on `victor/rules`; it has not been merged into main or pushed. See `SNAPSHOT.txt` in the export folder for the exact saved commit. Copies of the handoff at the main root are for easy discovery, not another code version. `.worktrees/` is ignored via local `.git/info/exclude`. Scratch task ledger is under the worktree's `.superpowers/sdd/04-victor-implementation-plan/`; it is not needed to run the source.

Local Python is 3.12.13 in the prototype `.venv`; system Python 3.9 is unsuitable. Packages installed: azure-ai-projects 2.8.0, azure-identity 1.26.0, openai 3.29.0, Pydantic 2.14.1, VI 0.1.0 from upstream commit `356c29635f1c44df7de02edb58699ca9f29bece6`. No `az` executable was available when checked. A browser login does not prove SDK authentication.

For a fresh checkout:

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements-victor.txt
MOCK_LLM=1 .venv/bin/python -m pytest -q
```

Fresh safe-stop suite: **33 passed** (16 SDK adapter + 11 AI + 6 conversation). This proves those tests, not whole-app enforcement, all twelve scenarios, model accuracy, or live inference.

## Implemented code

Existing Josue code: `app/models.py`, `app/fixtures_loader.py`, `app/fixtures/offers.json`, `app/vi_adapter.py`, `app/main.py` health route/static hosting, `tests/test_vi_adapter.py`, placeholder `web/index.html`.

New partial AI prototype:

- `app/foundry_client.py`: private `DraftRequirements` validation, conservative demo-vocabulary parser, `questions_for`, `extract_requirements`, and deterministic `explain`.
- `app/conversation.py`: `ConversationStore`, timestamped user/assistant turns, field sources pointing to literal user quotes, merged drafts, immutable copied approval trace keyed by requirement id.
- `tests/test_foundry_client.py`, `tests/test_conversation.py`.
- `requirements-victor.txt`: includes base requirements plus official Foundry and identity SDKs.

**Not implemented:** live Microsoft SDK transport, agent tool configuration/handler, evidence_narrative, rules engine, can_purchase, evidence packet builder, store/product API endpoints, full UI, scenario/enforcement/injection integration coverage. Existing extract/explain currently always run offline and return `llm_fallback=True`, regardless of MOCK_LLM. Installed Microsoft libraries alone are not a Foundry integration.

## Existing and planned interfaces

Keep the shared models in `app/models.py`. Implement these functions without changing callers casually:

```python
# Existing partial code
extract_requirements(text: str, today: date | str | None = None) -> ExtractResult
explain(decision: Decision, req: ApprovedRequirements) -> ExplainResult
conversation_turn(conversation_id: str | None, text: str, today=None) -> dict
record_approval(conversation_id: str, req: ApprovedRequirements) -> dict
trace_for_requirements(requirement_set_id: str) -> dict

# Required next modules
evaluate(req: ApprovedRequirements, offer: FlightOffer | None,
         vi_chain_valid: bool, merchant_signature_valid: bool) -> Decision
can_purchase(decision: Decision, exceptions: list[ExceptionAcceptance]) -> tuple[bool, str, list[str]]
build_packet(purchase, dispute_claim, decision, req, offer, exceptions,
             narrative=None) -> EvidencePacket
evidence_narrative(packet: EvidencePacket) -> str | None
```

`can_purchase` uses `(allowed, reason, uncovered_check_ids)`; older docs/07 shows two values, so use the three-value contract consistently across the new sessions. The server stores decisions; never trust client-supplied PASS objects. `purchase` provides purchase_id by mapping or attribute; no new Purchase model is needed.

`conversation_turn` returns conversation_id, turns, draft_requirements, field_sources, questions, notes, llm_fallback, approved=False. Each field source has turn_id, quote, interpretation. `record_approval` is for the server's explicit approval action only, not an agent tool. It requires an approved requirements object equal to the current draft and rejects reuse of the requirement id. A trace is an application record and includes `trace_status=application_record_not_user_signed_transcript`. Export it as a separate attachment beside EvidencePacket to avoid silently breaking that model.

## Verified cloud state

Resource `victor-lead-foundry-20261012`; project `lead-team`; resource region West US 2; Azure for Students.

- Victor explicitly approved the Foundry User self-assignment; it succeeded.
- Foundry created `intent-judge-assistant`, version 1, at about 1:01 PM ET.
- Playground visibly selects **gpt-oss-120b**, **Global Standard deployment**.
- Agent instructions are blank; no tools are configured; no test message was sent.
- No live model or tool invocation succeeded in this session. Deployment quota/details, model JSON capabilities, SDK authentication, and end-to-end latency remain unverified.
- Earlier gpt-5-mini Global Standard/Data Zone Standard forms said unsupported West US 2; that does NOT mean all models are unavailable. The later agent wizard selected gpt-oss-120b automatically. Recheck current state instead of recreating resources.
- No key was revealed/copied; no .env was created; no paid reserved-throughput commitment was made intentionally. The default model's billing/quota details were not inspected.

Project endpoint: `https://victor-lead-foundry-20261012.services.ai.azure.com/api/projects/lead-team`
Resource Azure OpenAI v1 endpoint: `https://victor-lead-foundry-20261012.openai.azure.com/openai/v1/`
These are different API surfaces. For agents use the project SDK/endpoint, not the resource endpoint blindly.

[Existing assistant](https://ai.azure.com/nextgen/r/xagNntfoRYS1VFrLbdrcsg,lead-team-rg,,victor-lead-foundry-20261012,lead-team/build/agents/intent-judge-assistant/build?tid=17dcb00c-6941-4050-b69e-bd7eb8951712).

## Research findings and technical choice

1. [Mastercard's article](https://www.mastercard.com/us/en/news-and-trends/stories/2026/verifiable-intent.html) already describes human-in-the-loop confirmation and additional confirmation for autonomous commerce. Do not pitch human confirmation itself as something VI lacks.
2. [VI SDK README](https://github.com/agent-intent/verifiable-intent/) supports Immediate (L1/L2, human confirms final cart/payment) and Autonomous (L1/L2/L3, delegated constraints) modes. Existing adapter uses Autonomous. Preserve it for the demo unless the integration owner deliberately chooses another mode.
3. VI has built-in machine-enforceable constraints and signed checkout/payment binding. [Custom constraint spec](https://github.com/agent-intent/verifiable-intent/blob/main/spec/constraints.md) permits namespaced extension data; our flight extension's semantic comparisons are our responsibility. A valid chain is not a passing flight rules result. Unknown constraints in open mandates have compatibility rules—review before claiming generic validator interoperability.
4. The original L2 cannot honestly be claimed to authorize a later deviation automatically. The prototype records offer-specific traveler exceptions at the application level; they are not new signed VI credentials. A future strengthened implementation can issue a newly confirmed mandate or Immediate final-cart authorization. Do not claim that is already implemented.
5. [Microsoft SDK overview](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/sdk-overview) and [function-tool guide](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/function-calling) support `azure-ai-projects`, `AIProjectClient`, `PromptAgentDefinition`, conversations, and function tools. The SDK obtains an OpenAI-compatible client via `get_openai_client()`. Locally installed SDK signatures were inspected; no live call was made.
6. Use ONE prompt agent + ONE read-only `search_demo_offers` tool. Microsoft Agent Framework is compatible but unnecessary for this prototype. No hosted containers, vector database, generic multi-agent runtime, or live airline integrations.
7. [Structured output guidance](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs) requires model/API-specific support; do not assume agent JSON is schema-guaranteed. Always validate with Pydantic. Don't force temperature=0 on unsupported models. Invalid/refused/incomplete/timeouts must visibly fall back.
8. Evidence can support merchants/analysts, but [VI's security model](https://github.com/agent-intent/verifiable-intent/blob/main/spec/security-model.md) does not settle disputes or assign liability. Final decision remains dispute analyst.

## Known gaps to address before broad demo use

Verified parser limitations: a bare `JFK` reply is currently interpreted as destination, not a context-sensitive origin answer; `I do not want nonstop` currently becomes max_stops=0. Fix with failing regression tests. The parser is not general language understanding.

Other unverified boundaries needing focused tests: conflicting/new answers that should clear old values, unsupported airports/relative dates, invalid or excessive passenger counts, negated preferences, and preserving explicit optional "no preference" answers. The current parser assumes one traveler and interprets morning as 06:00–12:00; these are visible review defaults, not independently proven user preferences. A field's quoted source is the full supporting user turn; semantic correctness still needs traveler review. Conversation state is in-memory, not durable/audited production storage.

`app/vi_adapter.py` currently defaults absent currency to USD. Missing merchant currency must not pass as known USD. The integration owner should make the minimal adapter/model-compatible fix after checking Josue's current work. `signed_requirements` reads an object marked evidence-only: source approved requirements from the successfully verified L2 or compare the stored snapshot to it after serialized verification. Never decide from prompt_summary.

## Demo and time discipline

Target a two-minute sequence: vague request -> two follow-ups -> concrete draft -> explicit approval -> merchant offers nonstop A vs three-connection B -> B HOLD -> purchase 409 -> specific acceptance (or choose A) -> simulated purchase -> vendor evidence showing original words and exact approved/accepted facts. Tamper -> BLOCK is the optional short contrast.

Synthetic A is $260 nonstop; B is $280 with THREE connections (four segments), not a bargain that is cheaper than A. Don't invent a savings story from these fixtures. The budget is $300 inclusive; H at $300.01 must HOLD. Twelve scenario expectations are in the shared fixtures/docs10.

Start sessions 1–3 in parallel. Session 4 owns integration and can prepare routes against fixed signatures while those modules are finished. Integrate/test at 2:00 PM; reserve the last 30 minutes for fixes, rehearsal and offline backup. Cloud troubleshooting gets at most ten minutes before escalating the exact blocker to a Microsoft volunteer/user and preserving the offline path. Never claim event compliance merely because a blank agent exists.
