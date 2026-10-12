# Victor's domain and Foundry design — October 12, 2026

Status: historical design. Victor has requested a modular Devin handoff and a safe stop of Codex implementation. Read ../../DEVIN-HANDOFF.md and ../handoff/README.md for the verified current state; earlier cloud/implementation snapshots below are historical.
Deadline: 2:30 PM America/New_York today. Target feature freeze: 2:00 PM, leaving 30 minutes for integration fixes, rehearsal, and backup.

## Outcome

Deliver Victor's complete flight decision, consent eligibility, extraction/explanation, and evidence modules against the models already supplied by Josue. The core must work without Azure. Live Foundry adds language understanding and explanation; it never adds purchase authority. Preserve AGENTS.md and the established flight scope.

## Verified starting point

- Local main is at 76333ba after bringing in origin/jossue/build. Its working tree was clean at the start of this review. This does not establish the state of Josue's unpublished work.
- Existing code: app/models.py, app/fixtures_loader.py, app/fixtures/offers.json, app/vi_adapter.py, app/main.py health route/static hosting, placeholder web/index.html, and tests/test_vi_adapter.py.
- Missing: Victor's three modules, store.py, product API endpoints, full UI, domain/scenario/enforcement/injection tests.
- Shared models already include APPROVAL, ExtractResult, and ExplainResult. The adapter converts totals without confirmed taxes/fees to total_cents=None. No shared-model edit is needed for those cases.
- No project .venv was found; the default python3 lacks pytest, Pydantic, verifiable_intent, and openai. Existing adapter tests have not been run in this review.
- Browser inspection: resource victor-lead-foundry-20261012, project lead-team, region westus2, Azure for Students subscription. The serverless deployments view says "Deploy your first model".
- Azure OpenAI v1 endpoint shown in the portal: https://victor-lead-foundry-20261012.openai.azure.com/openai/v1/ . Project endpoint: https://victor-lead-foundry-20261012.services.ai.azure.com/api/projects/lead-team . These serve different APIs and must not be interchanged.
- For gpt-5-mini version 2025-08-07, both Global Standard and Data Zone Standard deployment forms explicitly report unsupported region for West US 2. No model deployment was submitted or key revealed. Other models/regions remain untested. The separately approved Foundry User role assignment subsequently succeeded.
- The originally denied Agents page now permits creation after Victor explicitly approved the Foundry User self-assignment. The current agent list is empty; the creation form can be opened. No agent or live model has been created. The Azure overview independently shows the underlying Foundry resource deployment succeeded.

## Chosen approach to review

Strengthen the existing modules and function contracts. Use private typed validation inside foundry_client.py while preserving public ExtractResult and ExplainResult. Use direct model inference for the application and separately configure the required Foundry portal agent when deployment is available.

Alternatives: mock-only is a useful backup but does not complete the event's Foundry requirement. Moving the application into a new hosted-agent orchestration stack adds infrastructure and interfaces that this demo does not require. Neither alternative replaces the deterministic engine.

## Ownership and interfaces

Victor edits app/rules_engine.py, app/foundry_client.py, app/evidence.py, their unit tests, tests/test_injection.py, a domain scenario report, and this new document. Avoid edits to Josue's app/main.py, app/vi_adapter.py, app/store.py, web/, fixtures, requirements, and shared models. Coordinate integration tests through a distinct file or one designated editor.

Execute implementation in an isolated victor/rules checkout/worktree after review. Preserve the user's current main checkout. Do not run git commands or tools that send messages on Josue's behalf.

Public contracts retained from the detailed build plan:

```python
evaluate(req, offer, vi_chain_valid, merchant_signature_valid) -> Decision
can_purchase(decision, exceptions) -> tuple[bool, str, list[str]]
extract_requirements(text, today) -> ExtractResult
explain(decision, req) -> ExplainResult
evidence_narrative(packet) -> str | None
build_packet(purchase, dispute_claim, decision, req, offer, exceptions, narrative=None) -> EvidencePacket
```

The three-value can_purchase return is the draft plan's proposed contract; clearly document it for Josue, since docs/07 still shows two values. For build_packet, accept an object or mapping with purchase_id; no new shared Purchase model is required. Do not require other purchase fields unless an integration need is demonstrated.

## Rules and consent

- Follow docs/07's ordering: invalid credentials/signature -> BLOCK before accessing offer fields; unapproved requirements -> HOLD with APPROVAL missing; then all eleven checks.
- The verifier can return offer=None on an invalid signature. The engine must still return BLOCK without crashing. A missing offer despite true verification flags yields missing checks/HOLD rather than inferred compliance.
- Money stays integer cents. Evaluate airport-local date/time, inclusive budget/window boundaries, next-day arrival failure, and no segments as missing itinerary data.
- Every applicable check returns pass/fail/missing; optional absent requirements return not_required. Produce exact values and plain English messages. Complete all checks rather than stopping at the first failure.
- HOLD can be purchased only when every failed/missing check has recorded acceptance for the same decision_id, offer_hash, check_id, and exact accepted offer_value. APPROVAL cannot be excepted; BLOCK cannot be excepted. A bare "OK" cannot establish consent.
- Exceptions carry timestamps and accepted values. Tests cover partial coverage, wrong decision, changed offer, wrong accepted value, duplicates, unapproved requirements, and explanation text claiming approval. Validate malformed consent conservatively.
- Tests may evaluate fixtures without a signed hash; the integrated purchase flow must use the adapter's exact nonempty signed checkout hash. No agent description or prompt_summary influences checks.

## Extraction, explanations, and resilience

- Keep draft requirements unapproved. A private typed draft model validates known fields, rejects unexpected approval/result fields and invalid values, and represents unknown required fields as null.
- Prompt only for preferences supported by traveler text; ask at most two questions at a time for missing required fields. Explicitly preserve unresolved gaps in the draft. Do not invent a destination, budget, cabin, refundability, or nonstop preference.
- Preserve the current public extract(text, today) contract. Josue's editable approval form collects answers; any later conversational refinement API is coordinated separately.
- Use notes for visible assumptions. Field-level provenance is a possible later improvement, but introducing new public fields is not required for the first working flow.
- Mock parsing covers the full documented demo and reasonable variations, including non-refundable vs refundable and conflicting/vague dates. Ambiguous inputs remain questions/nulls.
- Prefer JSON Schema structured output when the selected deployed model supports it; still validate in Python. Otherwise validate JSON-mode output. A schema-valid output can still misinterpret a preference; traveler review remains essential.
- v1 endpoints use OpenAI(base_url=...) rather than AzureOpenAI with a dated API version. Keep endpoint compatibility in one factory and retain the existing AZURE_OPENAI_* configuration names.
- Use only generation parameters supported by the deployed model. In particular, do not copy temperature=0 unconditionally into a reasoning-model call; inspect model support and use a supported low/minimal reasoning setting when latency matters. Cap output and handle incomplete/refused responses through the same fallback.
- Initialize the cloud client lazily so mock mode needs no credentials. Use a three-second request timeout and disable automatic retries for the demo so retries do not multiply the delay. Test the fallback path; do not claim a strict wall-clock guarantee without measuring it.
- Network errors, refusal, malformed/invalid output, missing cloud configuration, and timeouts yield a deterministic fallback with llm_fallback=True. Avoid logging credentials, raw headers, or response bodies.
- Explanation text preserves the code result and names every failed/missing check. For BLOCK, suggested_next_step cannot be accept_exception. Fall back to deterministic check messages if generated copy contradicts the structured result or omits required facts.
- Prompt injection defenses include treating text as data, schema restrictions, no purchase tools, and a code authority boundary. JSON encoding alone is not a guarantee against injection. Test invariance of the rules result independently of model wording.

## Evidence

Follow docs/07's recommendation table, always retaining final_decision="dispute analyst". Bind the packet to the decision/offer/approved requirement identifiers. Include only matching exceptions as consent evidence and preserve exact approved and offered values.

Use conservative recommendations when a claim cannot be mapped to the supplied evidence. A free-text allegation is not proof that the merchant delivered a different flight or that the platform bypassed enforcement. Without delivery evidence, do not manufacture a merchant finding. Model-written narrative cannot choose responsibility or reason code. The current reason-code mapping is the team's prototype mapping, not a legal determination.

## Research findings that affect implementation

1. The local research recommends precise approved delegation, retrievable consent, and pause/confirm checkpoints. Implement those as recorded structured fields, hash binding, and backend eligibility, rather than adding generic AI confidence scores.
2. The current VI specification supports namespaced custom constraints and states that unknown constraints are rejected in open mandates. The local prototype deliberately evaluates its custom flight constraint outside the SDK. Document that extension boundary; do not change AGENTS.md's SDK policy or claim universal compatibility without a team decision.
3. VI already supplies dispute evidence; the added value is flight-specific comparison and an assembled analyst packet. Avoid claiming that VI supplies no evidence or no intent controls.
4. Microsoft documents schema-constrained model output and the Azure OpenAI v1 endpoint. Use these within the private model client without changing Josue's HTTP response shapes.
5. Do not upload project research into runtime retrieval or add web-search tools for flight requirements. The engine's sources remain approved fields and signed offers. The research informs the design and presentation.

## Handoff Josue can apply without redesign

- /intent/extract calls extract_requirements and returns ExtractResult. Approval is always separate.
- /check obtains a verified offer, supplies verification flags, calls evaluate, and optionally attaches explain output without changing Decision.result.
- Supply requirements tied to the successfully verified L2 custom constraint. Resolve from that verified mandate or compare the stored approved snapshot to it; changing a stored requirement after signing must not change the decision source silently. Current signed_requirements is labeled evidence-only and reads bundle.l2, so verification of the serialized mandate must precede trusting that readback.
- /purchase calls can_purchase, returning 409 with reason/uncovered_checks or recording the simulated purchase only when allowed. The server owns decision records; it must not accept arbitrary client-supplied PASS objects.
- /exceptions records the exact decision, hash, check, offered value, traveler statement, and timestamp; avoid converting a bare acknowledgment into consent.
- /disputes calls build_packet and optionally evidence_narrative. Without purchase/delivery facts sufficient for a recommendation, return unclear.
- A missing currency must not become known USD. The current payload parser defaults missing currency to USD; this needs Josue's adapter-side adjustment or explicit validation before passing the offer to the engine.
- Freeze the public contracts, not all implementation choices. Additional evidence, returned metadata, or requirements fields that affect his code are written as requests before edits.

## Delivery order and checkpoints

Suggested targets from the 12:15 PM review; adjust based on actual execution start, preserving the 2:00 PM freeze:

| Target | Deliverable | Verification |
| --- | --- | --- |
| 12:50 PM | Pure rules + consent eligibility; baseline adapter tests run after local environment setup | Unit tests cover all rule fields and exception boundaries; A PASS, B HOLD, tamper BLOCK |
| 1:15 PM | Mock extract/explain + conservative evidence packet | Full domain flow works without Azure; evidence preserves consent and analyst authority |
| 1:40 PM | Live client + injection/fallback tests; model/portal-agent setup if available | Validated extraction and visible fallback; measured latency; no model approval path |
| 2:00 PM | All 12 scenarios, report, handoff and joint API flow | Distinguish pure-domain checks from credential/API/injection evidence; no "12/12" until actually run |
| 2:00–2:30 PM | Integration fixes, two rehearsals, backup and submission | Offer B -> HOLD -> 409 -> exception -> purchase -> dispute; live then offline run |

Cloud setup can proceed during read-only investigation. If the existing region cannot host the chosen model, inspect a supported model/region and quota before proposing a deployment. Do not make a paid or provisioned commitment without a concrete reviewed configuration. A cloud blocker does not delay the offline core, but the Foundry event requirement remains incomplete until an agent is actually created and tested.

## Acceptance

- A clean test run proves all eleven rule checks, invalid verification, approval requirement, and exact exception binding.
- Tests demonstrate that model prose cannot affect eligibility and that unknown fields/invalid extraction use the fallback.
- Offline demo works; live extraction/explanation is separately identified and tested when deployment exists.
- Evidence includes matched requirements, signed-offer hash, check results, specific exceptions, rationale, and human final authority.
- Existing adapter behavior is verified, not assumed from test files. Domain scenario coverage is not presented as complete API coverage.
- No edits to Josue's implementation files; shared changes are an explicit handoff. No secrets in the repo or report.

## Sources inspected

- Local docs/03, docs/04, docs/05, docs/07, docs/08, docs/10, docs/11, docs/plans/01-build-plan.md, and current source files.
- [Microsoft structured outputs](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs)
- [Microsoft Azure OpenAI v1 API](https://learn.microsoft.com/en-us/azure/foundry/openai/api-version-lifecycle)
- [Microsoft reasoning-model API differences](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/reasoning)
- [Foundry Agent Service regions and limits](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/limits-quotas-regions)
- [Mastercard's VI overview](https://www.mastercard.com/us/en/news-and-trends/stories/2026/verifiable-intent.html)
- [VI constraints specification](https://github.com/agent-intent/verifiable-intent/blob/main/spec/constraints.md)
- [VI security and dispute evidence](https://github.com/agent-intent/verifiable-intent/blob/main/spec/security-model.md)

External sources inform this proposed design; the team's research statistics and legal interpretations have not all been independently revalidated in this review.

## Latest agreed product intent and proposed technical revision

This section supersedes earlier flight-only product positioning and direct-inference-only preferences. Victor explicitly wants a confirmation and evidence layer for the future of agent-driven commerce. Flights are the fully implemented demo domain; support for other transaction categories is an extension direction, not a claim of implemented universal coverage. Existing flight models, constraints, and eleven checks remain in place. Do not rewrite the SDK adapter or build a universal rule language for this deadline.

**Outcome:** merchants can trace a transaction back to the traveler's words, targeted follow-up answers, approved requirements, signed merchant offer, rule results, and specific exceptions. The primary value is preventing misunderstood purchases before checkout; dispute evidence is a secondary value. Evidence supports review and does not guarantee liability protection or a successful dispute.

**Microsoft path:** use the official `azure-ai-projects` Python SDK with `azure-identity`, `AIProjectClient`, a persisted prompt agent, and a read-only `search_demo_offers` function tool. Retain the existing `openai` dependency for the project's OpenAI-compatible client. One agent handles clarification, extraction, and explanation; no multi-agent deployment or hosted container is required. Microsoft Agent Framework is compatible but not necessary for the first complete demo. Foundry requires a supported model deployment and usable authenticated project access; role assignment alone does not prove live inference.

**Conversation loop:** maintain an application conversation id, timestamped user/assistant turns, the current unapproved draft, and references from each extracted field to its source user turns. Ask at most two questions per turn, prioritizing unresolved destination, date, all-in budget, and preferences with meaningful offer differences. Do not require every optional preference or equate silence with approval. Search synthetic fixtures through the agent's read-only tool only when enough search context exists. Label catalog results as synthetic; no live fare or inventory claims.

**Confirmation:** show the complete structured draft and relevant source quotes. The traveler confirms the snapshot; the existing adapter signs approved requirements into L2. Any later change requires a new approved snapshot/mandate. Model output and raw chat are supporting evidence, never decision authority. The agent has no purchase, consent, or exception-recording tools. Backend checks and traveler actions retain authority.

**Trace:** create `app/conversation.py` with private sidecar models for turns, field references, and an approval snapshot associated with `requirement_set_id`. Preserve literal user text separately from AI interpretation. Copy approved snapshots and trace records when exporting evidence. Validate source references and ensure the quoted text exists in a user turn; a model-provided reference is not independent proof of semantic accuracy. Existing `source_text` is insufficient for a full multi-turn trace. Add a separate trace attachment to evidence rather than silently changing `EvidencePacket`. Do not call an application log or a standalone hash a user-signed transcript; binding a transcript digest into L2 requires an explicit adapter extension and is deferred unless integration time permits.

**Integration boundary:** preserve current `extract_requirements`, `explain`, `evaluate`, and `build_packet` functions. Add a documented optional `conversation_turn(conversation_id, text, today)` interface returning the existing extraction result plus conversation id and field references, and `trace_for_requirements(requirement_set_id)` for evidence attachment. Josue can wire these to a conversation endpoint and a vendor evidence view without a frontend redesign. In-memory synthetic conversation state is sufficient for this demo; no new database, retrieval index, or chat analytics stack.

**Fast execution:** rules and exact consent first; offline conversation/trace second; evidence third; one Foundry agent/tool connection last. Bound the agent to one catalog tool call per turn and a short model deadline; if additional reasoning is needed, return a follow-up rather than running an unbounded tool loop. On cloud failure, retain a visible deterministic offline mode using the same draft/trace interfaces. Time-box deployment troubleshooting to ten minutes. Do not claim live Microsoft inference unless a synthetic smoke test succeeds.

**Pitch:** “A confirmation and evidence layer for agent-driven commerce. We demonstrate it with flights: understand what the customer meant, confirm what they authorize, and give the merchant a traceable record before the agent buys.” Other domains require their own approved schemas and deterministic checks, such as item size/returns or delivery requirements.

Sources: [Microsoft Foundry SDK overview](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/sdk-overview), [Foundry function tools and conversations](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/function-calling), and [VI modes](https://github.com/agent-intent/verifiable-intent/).

## Safe-stop status supersedes historical cloud snapshot

The Foundry agent wizard subsequently created intent-judge-assistant version 1 with gpt-oss-120b Global Standard selected. Instructions remain blank and tools unconfigured; no live inference was tested. Offline foundry_client.py and conversation.py prototypes exist on victor/rules with 17 new tests plus 16 existing adapter tests passing (33 total). Live transport, rules, consent enforcement, evidence builder, and complete API/UI flow remain incomplete. Victor clarified that he intended separate Devin sessions to perform implementation; DEVIN-HANDOFF.md is the current execution entry point.
