# Conversational Intent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement inline, with one independent whole-branch review. Victor authorized autonomous recommended choices and deployment; no new human handoff is required.

**Goal:** Replace the form-led prototype with a conversational, evaluated intent assistant and continuous quality checks.
**Architecture:** Foundry extraction/coverage stages propose source-grounded drafts; profile questions guide clarification; revision-bound review and signed deterministic enforcement remain authoritative. Static modules render conversation, intent summary, review, offers and evidence. Synthetic evaluations score actual provider results.
**Tech Stack:** Existing Python/FastAPI/Pydantic, OpenAI Python, Azure Table, pinned VI SDK, vanilla HTML/CSS/ES modules, pytest, Playwright CLI and Vercel cron.
**Spec:** docs/superpowers/specs/2026-10-13-conversational-intent-design.md

## Global Constraints
- AI never approves; rules_engine alone emits PASS/HOLD/BLOCK.
- Approved structured fields and independently verified merchant facts remain authoritative.
- Missing facts HOLD; integrity/expiry/unknown constraints are unwaivable.
- All inference purposes share the existing 200-call/$20 lifetime reservation cap; no reset or emergency increase.
- Interactive 8/session and40/day; evaluation60/day; monitor2/day and40 lifetime.
- No implicit fallback, real commerce, credentials in reports or session-cookie disclosure.
- Fixed Python/static frontend stack; preserve victor/perfected and separate Vercel project.

## Review Focus
- Concurrent clarifications and changed approval cannot authorize an earlier offer.
- Unsupported conditions and source quotations cannot disappear across conversation turns.
- Model/JSON/audit failure remains visible and cannot create consent.
- Cron replay, missing authentication and exhausted budget cannot trigger unbounded paid calls.
- Responsive conversation/review and quality states must represent actual saved state.

### Task 1: Labeled evaluation and purpose budgets
Files: evals/cases.json, evals/scoring.py, tests/test_evaluation.py, app/store.py, .env.example.
Interfaces: `score_case(case:dict,result:dict)->dict`; `reserve_ai_call(session,purpose='interactive')->int`, shared lifetime cap with separate daily buckets.
- [ ] Write tests for label errors, omitted unsupported phrases, forbidden assumptions, source mismatch and purpose limits.
- [ ] Run targeted tests; expected missing scorer/API errors.
- [ ] Implement scorer, fixed development/holdout split and atomic purpose budgets.
- [ ] Run full suite green and commit.

### Task 2: Measured Foundry pipelines
Files: app/ai_pipeline.py, app/foundry_client.py, scripts/benchmark_ai.py, tests/test_ai_pipeline.py, evals/reports/*.
Interfaces: `run_pipeline(domain,text,session,variant,purpose)->dict` yields validated fields/sources/unsupported/explanation/mode/model/trace. Variants baseline/guided/audited; no purchase authority. Generic provider stages bound to JSON schema validation.
- [ ] Write mocked-provider tests for source spans, audit failures, traces, no preferences, error visibility and budget consumption; observe red.
- [ ] Implement baseline adapter, guided extraction and coverage audit.
- [ ] Run live development experiments within60 evaluation calls, choose measured best safety/latency, then untouched holdout. Preserve reports including failures.
- [ ] Run full suite green and commit.

### Task 3: Revision-bound conversation
Files: app/conversation.py, app/models.py, app/main.py, app/evidence.py, tests/test_conversation.py.
Interfaces: `conversation_context(messages)->str`; `draft_questions(domain,fields)->list`; clarify endpoint with revision/message and bounded turns; durable messages/trace/source references.
- [ ] Write multi-turn, changed-approval, unsupported-retention, race/revision, cross-session and evidence-provenance tests; observe red.
- [ ] Add conversation intake and clarification, preserve every safety gate and old session readability.
- [ ] Run full suite plus real multi-turn Foundry scenario green and commit.

### Task 4: Conversation-led product interface
Files: web/index.html, web/app.js, web/styles.css, web/api.js, web/views/*.js, DESIGN.md, scripts/browser_conversation.js.
Interfaces: API-driven conversation and live summary; explicit final review; existing signed comparison/consent/receipt endpoints.
- [ ] Analyze generated conversation and offer reference geometry/tokens.
- [ ] Implement responsive sidebar, calm composer, ranked follow-ups, review controls, compact offer differences and evidence; no fake quality numbers.
- [ ] Verify desktop/mobile, keyboard, live multi-turn,409 gate, exact exceptions, receipt and reload with Playwright; commit.

### Task 5: Continuous quality and release
Files: app/quality.py, evals/ canary corpus, .github/workflows/tests.yml, vercel.json, tests/test_quality.py, docs/implementation-status.md, scripts/configure_vercel.py.
Interfaces: authenticated daily `/api/internal/quality-check`, idempotent canary state, public synthetic-only `/api/quality`, shared spending cap.
- [ ] Write secret/replay/budget/failed-canary tests, observe red.
- [ ] Implement rotating canary and secret-free CI, configure secret through environment stdin, verify real canary and quality display.
- [ ] Fresh independent review, regression fix pass and full tests; deploy and exercise hosted conversation/enforcement/mobile.
- [ ] Record measured results, budget ledger, actual URL and remaining limits; commit/push branch.
