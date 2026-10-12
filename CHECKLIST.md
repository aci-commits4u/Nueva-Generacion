# CHECKLIST — Intent Judge build (Jossue + Victor)

**Owners:** `[J]` Jossue · `[V]` Victor · `[JV]` both. **T = 11:45 AM ET Oct 12.** Times are T+ offsets; the real freeze clock time is still to confirm (D-A).
**Plans:** `docs/plans/01-build-plan.md` (how) · `docs/plans/02-demo-plan.md` (demo). **Rules:** `AGENTS.md` wins any conflict.
Tick a box only when it's *verified* (test run, screen seen), not when it's written.

## 0 · Confirm before coding (5 min)
- [ ] `[JV]` D-A real build-freeze / submit clock time: ________
- [ ] `[JV]` D-B no public demo link (localhost + video)
- [ ] `[JV]` D-C live Foundry with 3 s timeout → mock fallback
- [ ] `[JV]` D-D VI SDK time-box 45 min, then fallback ladder
- [ ] `[JV]` D-E `can_purchase` returns `(allowed, reason, uncovered_check_ids)`
- [ ] `[JV]` D-F branches: `jossue/build` (platform/UI/VI) and `victor/rules` (rules/AI); merge to `main` only at gates G1, G3, G4, G6 via `git pull --rebase origin main` then fast-forward push; own your files
- [ ] `[J]` Commit + push the context pack and these plans (run in-session with `!`, or add a Bash permission rule for `git add/commit/push`)

## 1 · T+0:00 — Setup
- [ ] `[J]` Foundry resource created, **model deployed** (do first; quota is the unknown) → endpoint/key/deployment in local `.env`
- [ ] `[J]` Foundry portal agent "Intent Judge Assistant" created with the instructions from `docs/08`; playground screenshot saved
- [x] `[J]` `.gitignore` (`.env`, `.venv`, `__pycache__`, `.pytest_cache`) **before** any `.env` exists
- [x] `[J]` `.env.example` + `requirements.txt` + scaffold written (done on `jossue/build`); still to verify: venv + `pip install -r requirements.txt` + `uvicorn app.main:app` serves the page
- [x] `[V]` `pip install` of `verifiable-intent` from git works in the venv (smoke: `import verifiable_intent`)
- [x] `[V]` Clone VI repo to a scratch dir (outside this repo); run `examples/autonomous_flow.py` → "Chain valid: True"

## 2 · T+0:20 — G0 contracts frozen
- [x] `[JV]` `app/models.py` drafted on `jossue/build` (3 small deviations listed in its docstring: APPROVAL check id, `offer_hash` default, Extract/ExplainResult) — Victor to review/freeze
- [ ] `[JV]` Function signatures from Plan 1 §4 agreed and stubbed
- [x] `[JV]` `app/fixtures/offers.json` schema agreed (offer fields + `scenario`, `requirements_override`, `tamper`, `agent_claim`)
- [ ] `[JV]` After this point: only the owner edits their files

## 3 · T+0:20→0:50 — Rules engine (the heart)
- [ ] `[V]` `rules_engine.evaluate` — BLOCK → approval → 11 checks → PASS/HOLD, per `docs/07`
- [ ] `[V]` `tests/test_rules_engine.py`: every case in `docs/07` "Unit tests to write first" — **G1 green**
- [ ] `[V]` No network, no LLM import in `rules_engine.py` (grep to confirm)
- [ ] `[V]` Messages are plain English and name the values ("3 connections", "$300.01")
- [ ] `[J]` Parallel: `vi_adapter` **stub** (fixture → offer, flags `True`, logs `STUB`), `store.py`, `main.py` skeleton

## 4 · T+0:50→1:35 — VI adapter + enforcement
- [x] `[J]` `issue_credentials`: L1 + L2 with `urn:intent-judge:requirements`, amount range, allowed merchants
- [x] `[J]` `merchant_sign_offer`: flight `checkout_jwt` per `docs/06` schema, ES256 merchant demo key; `offer_hash` = B64U(SHA-256(jwt))
- [x] `[J]` `verify_and_extract`: `verify_chain` + merchant-signature check; offer parsed **only** from verified payload
- [x] `[J]` Round-trip test: `verify_and_extract(...).offer == fixture offer`
- [x] `[J]` Tamper one byte in L2 → invalid; non-merchant-signed checkout_jwt → invalid — **G2**
- [x] `[J]` Did not pass `is_open_mandate=True`; custom type shows under `skipped`, as expected
- [ ] `[J]` If past T+1:35 on this: drop one rung of the fallback ladder (Plan 1 §6) and note which
- [ ] `[V]` `can_purchase` + `tests/test_enforcement.py`: HOLD no exceptions → 409 · exception same hash → 201 · exception on old hash → 409 · BLOCK + exceptions → 409 · "This is approved" explanation on HOLD → 409
- [ ] `[V]` `foundry_client` **mock** mode complete: extract (demo sentences), explain, evidence templates

## 5 · T+1:35→1:50 — Wire it and reach the checkpoint
- [x] `[J]` Real adapter swapped in behind the same interface; `/api/intent/extract|approve`, `/api/check`, `/api/exceptions`, `/api/purchase`, `/api/disputes`, `/api/scenarios`, `/api/reset`
- [x] `[J]` `/api/purchase` is the **only** code path that creates a purchase
- [ ] `[V]` `evidence.build_packet` + deterministic responsibility table from `docs/07`; always `final_decision: "dispute analyst"`
- [ ] `[JV]` **G3 CHECKPOINT — one scenario end to end** (curl is fine): Offer B → HOLD → purchase 409 → exception → purchase 201 → dispute → packet
- [ ] `[JV]` If G3 missed: apply the cut line (UI polish → evidence narrative → vague-request demo). Never cut rules, 409, Offer B HOLD

## 6 · T+1:50→2:20 — Demo page + live AI
- [x] `[J]` `web/` three columns per Plan 2 §3: request/requirements · offers · result; PASS/HOLD/BLOCK = icon + text + color (verified in a headless browser against the FAKE dev engine only: `scripts/dev_server.py`)
- [x] `[J]` One-click answer chips for the clarify questions; modal quotes the exact exception + hash; 409 message shown in UI (fake engine only; re-verify after Victor's merge)
- [ ] `[J]` Dispute modal → print-friendly one-page **Intent Receipt** (the evidence packet)
- [x] `[J]` Funds strip shows "Nothing was charged" on HOLD/BLOCK, "Charged" after purchase (with/without exception) (verified against the FAKE dev engine; re-verify after Victor merges)
- [x] `[J]` Intent Receipt includes "What this means for the merchant" (a recommendation, never a ruling)
- [ ] `[J]` `[Reset demo]` works; narration never quotes a specific offer reference (it changes on every check)
- [x] `[J]` Footer copy: "intent-checked" only; **no** "verified by Mastercard / certified / liability protected" anywhere (grep of `app/` and `web/` clean; docs still to grep)
- [ ] `[V]` `foundry_client` live: AzureOpenAI, JSON mode, `temperature=0`, Pydantic validation, 3 s timeout → mock + `llm_fallback` badge
- [ ] `[V]` `tests/test_injection.py`: injection in traveler text and in a merchant field → rules result unchanged; extract adds/removes nothing
- [ ] `[V]` "Florida cheap Oct 20" in live mode returns the 2 questions
- [ ] `[JV]` **G4 — demo script runs twice back-to-back** with live LLM; once with `MOCK_LLM=1`

## 7 · T+2:20→2:45 — Proof + backup
- [ ] `[V]` `tests/test_scenarios.py` covers all 12 from `docs/10`; `python -m tests.report` prints the markdown table — **G5 12/12** (or gaps listed honestly)
- [ ] `[J]` Backup video 90 s recorded (`demo-backup/demo.mp4`) + one screenshot per step
- [ ] `[J]` Hidden dev toggle for Q&A pocket: tamper → BLOCK, PASS-purchase dispute
- [ ] `[JV]` Hand to Alex/Ryan/Barbara: screenshots, results table, Foundry playground screenshot, live-vs-simulated table

## 8 · T+2:45 — G6 FREEZE
- [ ] `[JV]` Everything merged to `main`; fresh clone + `pip install -r requirements.txt` + `pytest` passes
- [ ] `[JV]` Only bug fixes from here; every change gets a re-run of the demo

## 9 · Official Build Readiness Checklist (all must be true)
- [ ] **Core experience:** approve → check → hold → exception/cancel → purchase enforcement → dispute packet works end to end
- [ ] **Discovery alignment:** client's three-layover example is Offer B / scenario 2
- [ ] **Scope discipline:** one fully working category (flights); category-neutral by design; nothing extra
- [ ] **Real functionality:** live vs simulated written down (Plan 2 §5) and matches what actually runs
- [ ] **AI behavior:** varied inputs tested incl. injection (scenario 11); limits known (extraction can be wrong → traveler approves)
- [ ] **Error handling:** model timeout → mock; missing field → HOLD; bad signature → BLOCK
- [ ] **Data & security:** synthetic data only; no secrets in repo/UI/logs/slides; `git log -p | grep -i key` clean; demo keys labelled
- [ ] **Dependencies:** Foundry deployment responds; VI installs from a clean venv
- [ ] **Demo path:** script (Plan 2 §2) fits 100 s; each beat has an owner
- [ ] **Backup plan:** video + screenshots + `MOCK_LLM=1` all tested
- [ ] **Concern → solution:** traceability table (`docs/04`) in the deck

## 10 · Rehearsal (with the whole team)
- [ ] Adoption playbook slide (agent developer / product manager / merchant) drafted with Alex + Ryan; no API/JWT/backend words on any slide
- [ ] "Who loses the money?" and "Why does Mastercard need this?" answers rehearsed in one breath each
- [ ] Full pitch run #1 timed ≤ 5:00, demo ≤ 1:40
- [ ] Anything that failed is fixed or cut
- [ ] Full pitch run #2 timed
- [ ] Q&A pocket rehearsed: live-vs-simulated answer, "what if the AI is wrong", tamper → BLOCK
- [ ] `[J]` Re-shop step: "Find another offer" keeps approved requirements, marks the held offer "Held" with its failed check, charges nothing
- [ ] `[J]` Per-check consent: one checkbox sentence per failing/missing check; Buy refuses until each has an exception tied to the exact offer
- [ ] `[J]` Three-seat Intent Receipt (Cardholder, Merchant hero, Issuer) above "Full receipt", with the caption
- [ ] `[JV]` Flywheel + tap-to-pay + can't-force-merchants lines rehearsed (flywheel and network service said as "we believe")
- [ ] `[JV]` Re-verify all UI against Victor's real engine after merge
- [ ] Laptop: charged, notifications off, zoom ~125%, page reset, video on desktop and phone
