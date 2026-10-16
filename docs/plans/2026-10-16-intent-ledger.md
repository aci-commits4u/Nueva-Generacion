# Intent Ledger Implementation Plan

> Execution: approved by Victor on 2026-10-16 (“go for it. do what u think is best”). Root coordinates bounded workers and independent review. No further design approval is needed for B. Production remains unchanged; C is not implemented in this scope.

**Goal:** Replace repeated snapshot reconstruction in dev with AI-proposed transactional intent changes and dynamic, state-aware questions, and compare actual trajectories against incumbent A.

**Architecture:** New `ledger` pipeline uses the same Foundry deployment, exact customer source catalogue, capability metadata, and deterministic approval/VI/checkout gates. AI emits sourced add/replace/retract/resolve/no_preference operations; a pure reducer validates revisions, source identities, typed values and invariant conflicts without interpreting language with regex. Persist semantic records and history independently from the compiled enforceable field view. Omission is no operation. Selective source-first review is bounded at two calls. Incumbent adaptive_fast remains available as an A/B control.

**Stack:** Existing Python/FastAPI/Pydantic/Azure Tables/vanilla JS; no new framework, vector DB or paid service.

**Spec:** docs/architecture/SYSTEM.proposed-v2.md; docs/architecture/06-evals/rubric.proposed-v2.md; docs/architecture/final-corrections.md.

## Global constraints

- User approval and signed verified merchant facts remain authoritative. No AI purchase approval, auto-fallback, hidden provider retry, unknown validator execution, or live booking.
- Keep dev/prod stores/keys/project aliases separate. Existing shared money cap/reservations remain authoritative; no budget reset or limit increase.
- Preserve incumbent tests and expose errors honestly. Live model calls only through existing budget ledger; bounded UAT within remaining allowance, no paid resource provisioning.
- Headless browser only on the shared Mac. No desktop disruption. Never print env/keys/cookies.
- UI changes limited to rendering new ledger state and useful interaction feedback; retain design direction.

## Shared interfaces (worker contract)

`app/intent_ledger.py`:
- `empty_ledger(revision=0) -> dict`
- `bootstrap_ledger(domain, current_draft, catalog) -> dict` for explicit refresh/legacy imports, never invent source evidence.
- `reduce_ledger(domain, ledger, proposal, catalog, *, expected_revision, structured_answer=None) -> dict`: pure transactional reducer; output revision expected+1, records/history; invalid batch raises `LedgerError` and input stays unchanged.
- `compile_ledger(domain, ledger, catalog=None) -> dict`: fields/sources/unsupported/clarifications/criteria from semantic active records; preferred/declined meaning is not mandatory; missing/unknown required meaning cannot disappear.
- `proposal_schema(domain, catalog, ledger) -> dict` strict model schema.
- `LedgerError(ValueError)`.

Proposal top-level: `expected_revision` integer, `operations` array, `action` ask_user/ready_for_review/review_required, `question` nullable (criterion_key, field nullable, text, why, answer_kind, answer_semantics nullable, options), `assistant_message`, `explanation`.
Operations all have: `op` add/replace/retract/resolve/no_preference, `target_id` nullable server record ID, `key` stable semantic key, `field` nullable allowed profile field, `value` typed or null, `strength` required/preferred, `status` active/needs_clarification/no_preference, `text` short semantic description, `source_refs` actual catalogue IDs. Add `unit` nullable; monetary supported values explicitly require the profile currency and all-in-total scope; other scopes stay unsupported. Record IDs/history assigned by reducer, not by the model. `replace`/`resolve`/`retract` target existing active record and require latest-turn evidence; multiple edits to same target or conflicting active compiled field reject batch. Unknown semantic criteria remain records. All sources refer to customer evidence only.

`app/ledger_pipeline.py`:
- `run_ledger_pipeline(domain, message, session, *, purpose='interactive', source_text=None, source_messages=None, current_draft=None, reasoning_effort=None) -> dict`.
- Output same envelope as incumbent plus `pipeline='ledger'`, `intent_ledger`, `ledger_transition`, `criteria`, `adaptive_plan`, traces, model/mode. Revision must be next draft revision; source refs/ledger persisted server-side. Model is responsible for semantics and next question. Reducer rejects shape/state abuse; it does not certify entailment.
- Use structural/profile validation, not incumbent lexical grounding/repair. Source/literal contradiction alarms may request model review; they cannot promote fields. Review re-proposes one complete batch against original base ledger, no unbounded repair loop. Provider/budget/invalid required review preserves previous committed state and raises visible typed error. At most two calls.
- Payload has exact immutable customer turns/catalogue, active semantic state, latest verified turn/pending question, trusted clock, capability metadata and bounded airport identity references. Merchant context is separate data. No tool/write authority for B.

## Review focus

1. Multi-turn changes must preserve unrelated airports/dates, OR sets, no-preference and hard/soft distinction.
2. A stale/duplicate or malformed proposal must not partially apply or revive consent.
3. Required unsupported predicates and unit/scope ambiguity must remain visible/HOLD; ordinary phrases should not require regex aliases.
4. Answered questions must not recur through either question card or assistant bubble; multiple airport widgets remain valid.
5. Review edits, saved/reloaded drafts and explicit old-profile refresh must stay consistent with semantic ledger and exact approval digest.

## Task 1: Pure ledger and profile compiler

Owner worker ledger-core; files app/intent_ledger.py and tests/test_intent_ledger.py. Read spec and shared interfaces. Write failing tests first, implement immutable reducer/source validation/revision/history, then compile only supported active required values. Test omission, replacement, retract, no-preference, unsupported hard/soft, duplicate/source spoof/unknown target, stale revision, units, date/set values and structured airport binding. Run targeted tests and report outputs; no git commits by workers.

## Task 2: Foundry semantic operation pipeline

Owner worker ledger-ai; files app/ledger_pipeline.py, app/model_provider.py, tests/test_ledger_pipeline.py, tests/test_model_provider.py. Build dynamic strict schema prompt and bounded transport with usage/error traces; coordinate schema details with core worker. Use real-model path only when MOCK_LLM disabled and reservations succeed; no silent retry. Test model-proposed operation/review flows using fixtures, source/state isolation, no-question-known/declined, new generic criteria and failure/capacity preservation. No app/main/conversation/config changes owned here.

## Task 3: API/state integration

Owner root integration (or dedicated worker with these files only): app/main.py, app/conversation.py, app/ai_config.py, app/ai_pipeline.py routing only, app/evidence.py if needed, tests/test_ledger_api.py. Add ledger branch with per-draft architecture pinning; old draft stays A unless explicitly refreshed, new dev B only via selected config. Persist semantic state through intake/clarify/refresh/manual review. Do not pass B through incumbent snapshot repair or generic unknown-hardening. Validate exact revision/approval; record user review edits as customer-owned revisions. Derive live question/status from B record contract without generating questionnaire text in backend. Test full API flow, review/approve/mismatch/matching simulated checkout/evidence, reload, stale edit, failures and manual correction.

## Task 4: Trajectory evaluation adapter

Owner worker ledger-evals; files evals/trajectories.py (or package), evals/ledger_trajectories.json, scripts/benchmark_trajectories.py, tests/test_trajectory_evaluation.py. Consume actual API transitions for A and B, isolated sessions/process configuration; no global env mutation mid-request. Define at least 12 exposed development trajectory families with exact per-turn field/state, semantic duplicate adjudication placeholders, signed positive and conflicting offers, source/control expectations. Offline fake-provider checks validate harness ONLY. Live mode finite explicit --live --max-conversations --max-model-calls, existing ledger accounting, no hidden retries; every failure retained; record source/prompt/model/pipeline and raw proposal vs compiled state. Cost/token/latency per successful whole conversation and false-HOLD/refusal denominators. Never claim semantic utility from a field-null proxy. No live calls by worker.

## Task 5: Independent code review and actual product UAT

Fresh reviewer reads final diff and contracts, challenges sources/corrections/trust/gates. Separate fresh tester types unscripted tasks in headless actual chatbot, at least flight and hotel/general, changes supplied info and uses review/offer/evidence; no backend seeding/intercept/offline workaround for live success. Meter finite small UAT through existing allowance; missing capacity is reported, not bypassed. Run deterministic full suite and existing browser regression once integration stable. Fix failures with meaningful targeted tests. Compare live A/B on at least paired exposed tasks if capacity permits; label pilot small/unpowered and retain all failures.

## Task 6: Dev delivery

Commit reviewed source and documentation; push feature and run exact-source CI. Merge to develop only after passing required checks; use scripts/prepare_deployment.py before dev deployment. If release conditions permit, deploy to existing isolated dev project, verify actual dev version/UI/API; no prod promotion. Record implemented vs measured vs unknown, finite live results, caps, model-stage counts and limitations. Preserve old A and clear rollback path; no claim of powered superiority from small UAT.

## Metered validation window

Read-only shared-ledger preflight observed 2,484 cents reserved out of the existing 3,000-cent ceiling, with 173 current interactive stages available. This is conservative reservation accounting, not Azure billing. Root will use at most 32 new model stages for calibration, paired exposed trajectories and independent UI UAT combined (at configured 2-cent reservation, at most 64 cents of additional reservations), stopping sooner on lack of capacity or a critical failure. All calls retain reservations on failure; no resets, new model deployments or global cap increases. This limited validation cannot establish powered superiority or rare-failure bounds.
