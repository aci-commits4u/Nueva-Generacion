# Intent Judge Implementation Plan

> Execute with superpowers:executing-plans. User authorized autonomous recommended choices and deployment.

Goal: deliver a live Foundry-backed, VI-backed synthetic commerce demo on a separate Vercel project.
Architecture: static browser → FastAPI → signed session records → deterministic profile rules; VI and merchant signatures verified independently. SQLite locally, Azure Table optimistic concurrency in hosting. No real commerce.
Tech stack: Python, FastAPI, Pydantic, pinned VI SDK, OpenAI Python, Azure Tables, vanilla browser.
Spec: docs/04-architecture.md, docs/05-domain-profiles.md, docs/06-verifiable-intent-integration.md, user-provided AGENTS.md.

## Global Constraints
AI never authorizes. Approved structured requirements only. Signed merchant facts only. Missing means HOLD. Integrity gates are nonwaivable. Exceptions bind exact values and hashes. Every constraint receives an evaluator or HOLD. Synthetic identity, environment-only secrets. No implicit fallback. Total ordinary new Azure spending allowance $20; $10 emergency only. User wants at least $70 credit retained.

## Review Focus
Check independently: cross-session authorization; stale/replayed exceptions; malformed signed offers and unverified fields; custom/native constraint omission; prompt injection and unnoticed unsupported intent; live AI budget exhaustion and public abuse; concurrent purchase idempotency and serverless persistence.

### Task 1: Typed domain rules
Files: app/models.py, profiles/*.json, app/profile_registry.py, app/rules_engine.py, tests/test_rules_engine.py.
Interfaces: approved field states, profile digest, checks, deterministic PASS/HOLD/BLOCK.
Write boundary and missing-data tests first. Run pytest: expected missing modules. Implement registry and strict operators. Run pytest: expected green. Commit.

### Task 2: Signed VI and demo offers
Files: app/vi_adapter.py, demo/fixtures.py, tests/test_vi.py.
Interfaces: verified bundle → verified approved requirements and offer facts, integrity gates, native ledger.
Write tamper, unknown constraint, price and signature tests first; observe failure. Implement pinned SDK L1/L2/L3 issuance and composite verification. Run suite green. Commit.

### Task 3: Durable sessions and enforcement
Files: app/store.py, app/main.py, app/evidence.py, tests/test_enforcement.py.
Interfaces: session cookie; versioned approval; decision; exact exception; idempotent simulated receipt.
Write end-to-end 409, session isolation, stale consent, nonwaivable corruption, evidence tests first; observe failure. Implement transactional storage, API and synthetic commerce. Run suite green and one full scenario. Commit.

### Task 4: Live Foundry
Files: app/foundry_client.py, tests/test_intent.py, scripts/live_probe.py, .env.example.
Interfaces: validated extraction with source quotations, unknown conditions, usage and explicit mode; errors visible.
Write validation/injection/offline tests first; observe failure. Implement live provider with durable reservations and no silent fallback. Test real Foundry requests and corrections. Run suite green. Commit.

### Task 5: Demo interface
Files: web/*, DESIGN.md, docs/implementation-status.md.
Interfaces: same approval, check, exception and evidence API; no client approval shortcut.
Use image-first reference; implement intake, question/review, side-by-side signed offers, mismatch consent, receipt and evidence. Verify browser full flow, keyboard and mobile. Commit.

### Task 6: Deploy and verify
Files: requirements.txt, vercel.json, README.md, scripts/*.
Create separate Vercel project and durable storage; configure environment without printing credentials. Deploy committed branch, verify live extraction, mismatch refusal, consent, purchase, evidence and mobile. Fresh-context whole-branch review and regression fixes before final deployment. Record real URLs, tests, spend reservations and limitations. Commit.
