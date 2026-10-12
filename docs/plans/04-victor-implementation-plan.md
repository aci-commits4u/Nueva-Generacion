# Victor's flight domain Implementation Plan

> Historical plan: Victor is moving implementation to separate Devin sessions. Use DEVIN-HANDOFF.md and docs/handoff/README.md for current status/ownership. The full native plan has not been completed.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for inline implementation, or superpowers:subagent-driven-development if Victor explicitly selects that method. Track completed tasks and verification in a local ledger.

**Goal:** Deliver Victor's complete flight rule, purchase-eligibility, extraction, explanation, and evidence modules by the 2:00 PM feature freeze, ready for Josue's API integration and the 2:30 PM submission.

**Architecture:** Three modules in the existing Python backend consume the existing shared models and fixtures. Deterministic rules have exclusive decision authority; cloud language functions validate outputs and fall back offline. API endpoints, credentials, storage, and UI remain Josue's responsibility.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, existing verifiable-intent SDK, openai client against Microsoft Foundry.

**Spec:** docs/plans/03-victor-domain-design.md, approved by Victor in this session on October 12, 2026. AGENTS.md overrides conflicts.

**Latest direction from Victor:** Optimize for a five-minute pitch and roughly two-minute demo. Implement the existing single-backend workflow first. The later commerce/Foundry/conversation revision supersedes the earlier exclusion of conversation trace and uses a single Foundry prompt agent. Do not add hosted containers, retrieval, universal-domain refactors, or new shared public models. Keep functions small and tests focused on the actual traveler protections. Cloud troubleshooting is time-boxed; record a backup and preserve the offline path.

## Global constraints

- Commerce-wide product positioning; flights are the implemented demo domain. Synthetic data only; no live purchase/payment or automatic dispute determination.
- Only rules_engine.py decides PASS/HOLD/BLOCK. No model calls in this module.
- Inputs are traveler-approved requirements and verified merchant offers; missing applicable data yields HOLD.
- Invalid credential/signature yields BLOCK; APPROVAL missing cannot be excepted.
- Exception acceptance is bound to decision_id, offer_hash, check_id, exact accepted_value, traveler_statement, and timestamp.
- Money is integer cents; compare airport-local times with inclusive window/price limits.
- Public models and function names match Josue's current contracts. Do not edit his implementation files.
- No keys/secrets in logs, commits, screenshots, or handoff docs. Model client initialization is lazy.
- Native inline execution is recommended for this deadline. Cloud access changes require their own action-time approval; the Foundry User self-assignment has been approved separately.

## Review focus

1. Invalid signature with offer=None must BLOCK without dereferencing the missing offer — Task 1.
2. A HOLD with no actionable checks or a forged/inconsistent PASS must not become automatic consent — Task 2.
3. "non-refundable" must not become refundable-required; missing/conflicting destinations and dates stay unresolved — Task 3.
4. Refused/truncated/schema-invalid model output and disabled credentials must preserve working offline behavior — Task 3.
5. A free-text dispute alleging poor delivery cannot establish merchant fault without delivery evidence — Task 4.

## Task 1: Rule evaluation

**Files:** Create app/rules_engine.py and tests/test_rules_engine.py. Read existing app/models.py, app/fixtures_loader.py, and docs/07-rules-engine-spec.md.

**Interfaces:** Produces evaluate(req: ApprovedRequirements, offer: FlightOffer | None, vi_chain_valid: bool, merchant_signature_valid: bool) -> Decision. Consumes unchanged shared models; returns a new decision_id, offer_hash when present, UTC created_at, verification flags, and complete structured checks.

- [ ] Set up victor/rules in an isolated worktree and a Python 3.12 venv; install existing requirements and run pytest. Record baseline results before adding code.
- [ ] Write tests against evaluate via getattr so a missing implementation produces a clear assertion failure. Assertions: offer A -> PASS; B -> HOLD and STOPS fail with "3 connections"; invalid signature plus None offer -> BLOCK; unapproved requirements -> APPROVAL missing.
- [ ] Run `.venv/bin/python -m pytest tests/test_rules_engine.py -q`; confirm failures are for the missing evaluator, not malformed fixtures.
- [ ] Implement evaluate and small field-check helpers, then run those tests green.
- [ ] Add failing tests for all eleven fields: wrong origin/destination/date, window/arrival violation, cabin mismatch, passenger mismatch, refund false/unknown, absent total, currency mismatch/empty, and stops omitted from requirements.
- [ ] Add boundary tests: 30000 passes vs 30001 holds; departures exactly at 06:00 and 12:00 pass; next-day arrival fails an arrive_by requirement; empty segments yield missing itinerary checks; all failures are returned together.
- [ ] Run tests red, complete the evaluator, and run the entire available suite green. Assert mutating source_text or explanation has no authority over checks.
- [ ] Commit only the new rule module and its tests on victor/rules; record test counts and the commit in the ledger.

## Task 2: Exact purchase eligibility

**Files:** Modify Victor's app/rules_engine.py; create tests/test_purchase_eligibility.py. Leave Josue's HTTP enforcement test file available to him.

**Interfaces:** Produces can_purchase(decision: Decision, exceptions: list[ExceptionAcceptance]) -> tuple[bool, str, list[str]]. The list is uncovered_check_ids for Josue's HTTP 409 response. Explanation strings never participate in eligibility.

- [ ] Write tests: PASS with a real test offer hash -> allowed; HOLD without acceptance -> denied with STOPS uncovered; one exact acceptance -> allowed; partial/wrong decision/wrong hash/wrong accepted value -> denied; BLOCK with acceptance -> denied; APPROVAL missing with acceptance -> denied.
- [ ] Test a bare "OK" statement and missing hash as invalid consent; duplicate acceptances do not cover different checks. A contradictory PASS with failing checks, or a HOLD with no unresolved checks, must not authorize a purchase.
- [ ] Run `.venv/bin/python -m pytest tests/test_purchase_eligibility.py -q` red, implement can_purchase conservatively, and rerun green.
- [ ] Assert an explanation containing "This is approved" leaves a HOLD denied. Run the entire available suite.
- [ ] Commit only this module/test delta and ledger the result. Publish the three-value return contract in the local handoff doc; do not send messages automatically.

## Task 3: Offline and live language functions

**Files:** Create app/foundry_client.py, tests/test_foundry_client.py, and tests/test_injection.py. Define private draft and response validators in the module to avoid shared-model edits.

**Interfaces:** extract_requirements(text: str, today: date | str) -> ExtractResult; explain(decision: Decision, req: ApprovedRequirements) -> ExplainResult; evidence_narrative(packet: EvidencePacket) -> str | None. Public responses remain existing shared models.

- [ ] Write mock tests using MOCK_LLM=1 with Azure environment unset. Explicit demo request yields JFK/LGA/EWR -> MCO, Oct 20, morning window, max_stops=0, max_total_cents=30000; no approval/result fields are returned.
- [ ] Vague "NYC to Florida cheap, Oct 20" leaves destination and budget null and asks at most two questions. Unstated nonstop/refundability/cabin remain null. Test non-refundable, decimals, case variations, and conflicting dates/preferences.
- [ ] Run `.venv/bin/python -m pytest tests/test_foundry_client.py -q` red, implement validated keyword/regex fallback, and run green. Incomplete drafts remain incomplete rather than silently filling required fields.
- [ ] Add explanation tests: all failed/missing checks are represented, BLOCK cannot suggest accept_exception, and missing approval cannot be explained as a purchase authorization.
- [ ] Write live-boundary tests by replacing only the model transport: valid JSON/schema -> validated result, unexpected fields/invalid types/refusal/incomplete output/transport timeout -> llm_fallback=True with usable mock data. Verify missing configuration needs no import-time cloud client.
- [ ] Run red, implement the lazy Azure client factory and validation. Normalize either a v1 endpoint for OpenAI or the legacy AzureOpenAI configuration. Use one request timeout of three seconds, max_retries=0, and model-supported output parameters; no unconditional temperature=0 for reasoning models.
- [ ] Add injection tests: appended control instructions do not gain approval fields or change approved requirement checks; malicious merchant text cannot reach a purchase tool; generated "approved" explanations cannot change eligibility. Test actual local functions, with transport replacement only for cloud boundary cases.
- [ ] Run the full suite green and commit. If a model deployment is available, smoke-test synthetic extraction and explanation and record latency/fallback status; distinguish this from tests using fake transport.

## Task 4: Evidence packet

**Files:** Create app/evidence.py and tests/test_evidence.py. Read docs/07's responsibility table. Leave shared models unchanged.

**Interfaces:** build_packet(purchase, dispute_claim: str, decision: Decision, req: ApprovedRequirements, offer: FlightOffer, exceptions: list[ExceptionAcceptance], narrative: str | None = None) -> EvidencePacket. purchase supplies purchase_id as a mapping or attribute; no new public Purchase model is introduced.

- [ ] Write tests: passed approved booking -> evidence of matching requirements; recorded exact STOPS exception -> traveler recommendation with exception rationale; invalid verification -> fraud_path/4837; insufficient evidence -> unclear; final_decision always "dispute analyst".
- [ ] Test wrong-hash/decision/value acceptances cannot be presented as consent. A text claim "merchant delivered three stops" without delivery evidence must not yield merchant responsibility. A narrative cannot overwrite a reason code or responsibility value.
- [ ] Run `.venv/bin/python -m pytest tests/test_evidence.py -q` red; implement packet assembly, identifier consistency, and conservative deterministic recommendations; rerun green and run the full suite.
- [ ] Preserve originals using copies so packet construction never mutates requirements, decisions, or exceptions. Commit module/test delta and ledger results.

## Task 5: Scenario proof and integration handoff

**Files:** Create tests/test_domain_scenarios.py, tests/report.py, and docs/plans/05-victor-integration-handoff.md. Do not modify shared fixtures or Josue's API/UI/adapter.

**Interfaces:** Scenario tests consume existing scenarios(), offer(), base_requirements(), Victor's evaluator, and Josue's actual merchant signing/verification. Report prints actual outcomes and exits nonzero if an expected result/check differs.

- [ ] Write a failing scenario harness for all 12 fixtures, exercising actual VI verification for tamper and signed-offer cases. Scenario 9 confirms signed requirements carry nonstop despite an incomplete summary; scenario 10 uses the signed offer despite the agent's claim; scenario 11 combines merchant-note invariance with the separate extraction/injection suite.
- [ ] Run `.venv/bin/python -m pytest tests/test_domain_scenarios.py -q` red, complete harness/report, and run green.
- [ ] Run `.venv/bin/python -m pytest -q` and `.venv/bin/python -m tests.report`; report the actual scenario count and explicit limits. Tests of pure eligibility do not prove HTTP 409 until Josue's route is exercised.
- [ ] Handoff exact imports/signatures, sample output fields, three-value can_purchase return, matching acceptance fields, verified-L2 requirement source, missing-currency parser concern, and cloud configuration/status. List blocked requests separately from independent completed modules.
- [ ] Request one whole-branch read-only review using the executing-plans skill's review package; fix important findings with regression tests. Keep reviewer findings out of Josue's files and record any required changes for him.
- [ ] Commit only Victor's files/docs, leave the branch ready for integration, and do not push/merge shared main without session authorization for that step.
- [ ] Joint acceptance after Josue wires routes: Offer B -> HOLD -> HTTP 409 -> exact exception -> HTTP 201 -> dispute packet. Run live and MOCK_LLM=1, then rehearse twice before submission. If his route work is unpublished, report the pending integration dependency honestly.

## Cloud work and time limits

The Foundry User self-assignment is approved at action time. Verify the result before claiming agent access. Current gpt-5-mini pay-per-call deployment types are rejected in West US 2; inspect a supported deployment/region once, then stop cloud troubleshooting if no viable quota is available within ten minutes. Do not provision reserved throughput or create paid commitments speculatively. Do not replace the existing resource or widen other accounts' access.

Agent creation, live deployment, and model calls are distinct proofs. Keep the offline core progressing regardless of cloud availability; note that mock mode alone does not satisfy the Foundry agent event requirement.

## Plan review

Self-review: covers the approved design's owned modules, unchanged interfaces, rule/consent boundaries, cloud failure modes, conservative evidence, all twelve scenarios, and the integration handoff. The application API/UI remain an explicit external dependency; this plan does not claim to complete Josue's work.

Await Victor's plan review and execution-method choice before implementation. Recommended: native inline execution, because tasks share the same models and deadline is 2:30 PM. Use isolated victor/rules and one whole-branch review.

## Commerce/Foundry/conversation execution amendment

Read the latest revision in the approved design document before executing. The following additions replace direct-inference-only implementation choices while preserving the existing domain contracts.

1. Keep Tasks 1 and 2 first: rules and exact consent are required regardless of model or product positioning.
2. Add `app/conversation.py` and `tests/test_conversation.py` alongside Task 3. Test multi-turn preservation, stable ids/timestamps, unresolved drafts, source quotes/references, explicit approval linkage, copying approved snapshots, and a changed requirement requiring new approval. Export a trace attachment without changing the existing EvidencePacket model. The transcript is supporting evidence and cannot produce PASS.
3. Keep `extract_requirements(text, today)` compatible. Add a small conversation-turn interface wrapping extraction, targeting at most two questions, preserving literal turns, and returning validated field references. Implement/mock it before the live client. Questions are triggered by ambiguity and material catalog tradeoffs, not a fixed questionnaire for every optional field.
4. Add `requirements-victor.txt` with the official Foundry SDK and Azure identity dependencies, leaving Josue's requirements file untouched. Configure an optional project endpoint, deployment name, and agent name via environment variables. Use lazy authentication/client setup; no stored credentials or import-time network call.
5. Implement the official Azure AI Projects SDK transport in `foundry_client.py`: use the project client and its OpenAI-compatible client, prompt-agent reference, and a single allowlisted `search_demo_offers` function tool. The read-only tool filters existing synthetic fixture data. Validate tool arguments; refuse unknown tools; cap one tool call per turn and bound latency. No purchase or consent tools. Tests replace the transport for malformed outputs, timeouts, invalid references, repeated/unknown tools, and visible fallback.
6. Create/configure one persisted Foundry prompt agent only after deployment/authentication prerequisites are confirmed. Test one synthetic request and tool call through the SDK. Record actual response time, model, tool result, and fallback status. If blocked after ten minutes, finish offline flow and report the live integration dependency accurately.
7. Extend Task 4 with a separate conversation-trace attachment linking purchase -> requirements id -> original words/follow-ups/approved snapshot. Test wrong-conversation/requirement associations cannot supply consent evidence. Never present an unsigned transcript or exception as a VI user-signed authorization.
8. Add an example response and exact optional conversation/evidence interfaces to the integration handoff. The frontend/API integration remains explicit; do not claim whole-app completion from module tests.
9. Rehearse the reusable commerce story using the working flight flow. Mention other categories as planned adapters requiring schemas/checks. No unsupported chargeback-reduction metrics or merchant liability guarantees.

Execution recommendation remains native inline on `victor/rules`; do not start another planning cycle or create additional product infrastructure. Review this amendment together with the design revision and choose native execution to begin.

## Safe-stop handoff

Codex saved a partial offline AI/conversation prototype and verified 33 passing tests. No plan task is being marked complete: live SDK transport and several Task 3 cases are still missing; all other product tasks await implementation. Victor clarified he wanted implementation continued in Devin with a session per feature. The four session briefs in docs/handoff/sessions supersede single-session native execution. Known parser gaps and actual cloud status are in docs/handoff/README.md. No merge or push of the prototype branch has occurred.
