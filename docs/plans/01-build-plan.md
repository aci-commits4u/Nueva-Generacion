# Plan 1 — Build plan: how we build, with what, who owns what

> **Status: confirmed by Jossue (Oct 12); Victor's confirmation not yet recorded.** Jossue's track is built through the demo UI. Victor's modules (rules engine, evidence, LLM client) are not merged yet.
> Source of truth for rules stays `AGENTS.md`; detailed specs stay in `docs/05`–`docs/08`. This plan only decides *order, split, interfaces, and fallbacks* for **two builders**.
> Written Oct 12, 2026 at 11:45 AM ET (T = 0).

## 0. Decisions to confirm (reply "confirmed" or change any)

| ID | Decision | Recommendation |
|---|---|---|
| D-A | Real build-freeze / submission time | **Unknown to me.** Plan is in T+ offsets, freeze at **T+2:45**. Tell me the real clock time and I re-anchor. |
| D-B | Demo link (optional in the kit) | **No link.** Run on localhost + recorded video. A public link adds deploy risk for no judged benefit. |
| D-C | LLM on stage | **Live Foundry with a 3 s timeout, auto-fallback to mock, badge shown.** Switch to always-mock only if rehearsals show >2 s latency twice. |
| D-D | VI SDK time-box | **45 minutes** on `vi_adapter.py`; then drop one rung of the fallback ladder (§6). |
| D-E | One contract tweak: `can_purchase` returns `(allowed, reason, uncovered_check_ids)` | The 409 body needs `uncovered_checks`; computing it twice would drift. |
| D-F | Git workflow | Trunk-based on `main`, separate files per owner, `git pull --rebase` before every push. No PRs today. |

## 1. What we are building (one screen)

A FastAPI backend + one static page. Pipeline per purchase:

```
text → [LLM] draft requirements + ≤2 questions → traveler APPROVES → signed into VI L2 custom constraint
agent picks offer → merchant signs checkout_jwt → verify VI chain + merchant sig
  → extract FlightOffer from the SIGNED payload only → rules_engine.evaluate → PASS / HOLD / BLOCK
  → [LLM] explains (display only) → traveler cancels or records a specific exception
  → POST /api/purchase enforces (409) → dispute → evidence packet (recommendation, analyst decides)
```

Non-negotiables are the 10 rules in `AGENTS.md`. The ones that shape the code: only `rules_engine.py` decides; decisions read approved requirements + merchant-signed data only; missing = HOLD; backend returns 409; exceptions bind to `offer_hash`.

## 2. Stack — what we use

| Layer | Choice | Why / note |
|---|---|---|
| Language/runtime | Python 3.12 (installed), venv | Matches doc stack (≥3.11); VI SDK needs ≥3.10 |
| API | FastAPI + Uvicorn, Pydantic v2 | Typed models double as the Victor↔Jossue contract |
| Credentials | Mastercard `verifiable-intent` SDK (Apache-2.0, `cryptography` only) | Repo reachable from this machine; install via git URL |
| LLM | Azure AI Foundry deployment via `openai.AzureOpenAI`, JSON mode, `temperature=0` | Plus the **Foundry portal agent** ("Intent Judge Assistant") — event requirement and a slide screenshot |
| Offline | `MOCK_LLM=1` deterministic extract/explain/evidence | Demo survives Wi-Fi/quota loss (D13) |
| Frontend | `web/index.html` + `app.js` + `styles.css`, vanilla JS, served by FastAPI | No build step; nothing to break on stage |
| Tests | pytest + httpx `TestClient` | 12 scenarios + enforcement + injection |
| Persistence | In-memory dicts (`store.py`) + a `POST /api/reset` | Demo is rerunnable in one click |
| Dev tooling | Coding assistants (read `AGENTS.md`), GitHub Copilot Free | Student Pack approval can take hours; don't wait for it |
| Secrets | `.env` (gitignored), `.env.example` committed | **The repo has no `.gitignore` yet — first commit adds it** |

## 3. Ownership split (two builders)

| Owner | Files | Why this split |
|---|---|---|
| **Victor** (domain + AI) | `rules_engine.py`, `tests/test_rules_engine.py`, `evidence.py`, `foundry_client.py` (+mock), `tests/test_injection.py` | Pure logic and prompts; testable with zero network and zero VI |
| **Jossue** (platform + UI) | scaffold, `.gitignore`, Foundry deployment + portal agent, `vi_adapter.py`, `store.py`, `main.py`, `web/*`, demo recording | The integration-risk and demo-facing parts |
| **Both** | `models.py` (frozen at T+0:20), `fixtures/offers.json`, `tests/test_enforcement.py`, `tests/test_scenarios.py` | Contract + acceptance |

Rule: after the freeze, **only the owner edits a file**. If you need a change in someone else's file, message them or add a failing test that shows the need.

## 4. Interface contracts (freeze at T+0:20 — this is what unblocks parallel work)

`app/models.py` = the Pydantic models in `docs/05-architecture.md` verbatim. Function signatures:

```python
# Victor
rules_engine.evaluate(req, offer, vi_chain_valid, merchant_signature_valid) -> Decision
rules_engine.can_purchase(decision, exceptions) -> tuple[bool, str, list[str]]   # D-E
evidence.build_packet(purchase, dispute_claim, decision, req, offer, exceptions, narrative=None) -> EvidencePacket
foundry_client.extract_requirements(text, today) -> ExtractResult      # {draft_requirements, questions, notes, llm_fallback}
foundry_client.explain(decision, req) -> ExplainResult                  # {traveler_message, suggested_next_step, llm_fallback}
foundry_client.evidence_narrative(packet) -> str | None

# Jossue
vi_adapter.issue_credentials(req) -> CredentialBundle                   # L1 + L2 (custom constraint) serialized
vi_adapter.merchant_sign_offer(offer_fixture) -> str                    # checkout_jwt (ES256, merchant demo key)
vi_adapter.verify_and_extract(bundle, checkout_jwt) -> VerifiedOffer    # {offer: FlightOffer|None, vi_chain_valid, merchant_signature_valid}
```

**One fixture file drives everything.** `app/fixtures/offers.json` holds the 12 scenarios as plain data: `FlightOffer` fields + metadata `{scenario, requirements_override, tamper: none|l2|checkout_sig, agent_claim}`. Victor tests the rules engine straight from it (no VI). Jossue's `vi_adapter` turns the same fixtures into signed JWTs, and a round-trip test asserts `verify_and_extract(...).offer == fixture offer`. This is what keeps the two halves from drifting.

## 5. Order of work and gates

| T+ | Jossue | Victor | Gate |
|---|---|---|---|
| 0:00 | Create Foundry resource + deploy model **first** (it takes minutes; quota is the unknown) · venv · scaffold · `.gitignore` · `.env.example` | Read `docs/07`; write `models.py` draft | — |
| 0:20 | Together: freeze `models.py` + signatures + fixture schema; commit | | **G0 contracts frozen** |
| 0:20–0:50 | `vi_adapter` stub (parses fixture → offer, flags `True`, labelled `STUB`) · `main.py` skeleton · `store.py` | `rules_engine.py` + `test_rules_engine.py` (spec §"Unit tests") | **G1 rules tests green** (Victor) |
| 0:50–1:35 | Real `vi_adapter` (copy from `examples/autonomous_flow.py`; time-boxed, D-D) | `can_purchase` + `test_enforcement.py` · mock `foundry_client` | **G2 scenarios 1 & 2 verify; tamper → invalid** |
| 1:35 | Wire real adapter behind the same interface; `/api/*` + 409 | `evidence.py` + responsibility table | — |
| **1:50** | | | **G3 CHECKPOINT: Offer B → HOLD → 409 → exception → purchase → evidence packet, end to end (ugly OK)** |
| 1:50–2:20 | `web/` full page + `/api/reset` + dispute modal | Live `foundry_client` + injection test + Foundry portal agent playground check | **G4 demo runs twice in a row** |
| 2:20–2:45 | Record backup video, screenshots to `demo-backup/` | `tests/test_scenarios.py` 12/12 + `python -m tests.report` table | **G5 12/12 or known gaps listed** |
| **2:45** | **FREEZE.** Only bug fixes after this | | **G6 freeze** |

**Cut line if behind at G3** (from the original plan): drop UI polish → drop `evidence_narrative` prompt → drop the vague-request clarify demo. **Never cut:** rules engine, enforcement (409), Offer B → HOLD.

## 6. Biggest risk: the VI SDK — fallback ladder

`vi_adapter.py` is the schedule risk (SDK is draft v0.1; the `examples/` folder is not in the package; some helpers are underscore-internal).

1. **Full:** L1/L2 (+custom constraint)/merchant `checkout_jwt`/L3 → `verify_chain` + merchant-signature verify. Doc says this was already run successfully with the custom constraint on Oct 12.
2. **If L3 / `verify_chain` fights us past 45 min:** keep SDK-issued L1/L2 and verify the L2 signature + merchant `checkout_jwt` signature ourselves with the SDK's `es256_verify`. `vi_chain_valid` = L1→L2 binding + signature valid.
3. **Last resort:** simulated chain flags with real merchant-JWT signature checking. **This changes the pitch answer** to "VI credentials are simulated; merchant signing and rules are live" — we must say so out loud.

The interface in §4 never changes between rungs, so the UI and tests don't care.

## 7. Error handling we will actually build (maps to the official Readiness item)

| Failure | Behaviour |
|---|---|
| LLM timeout / bad JSON / no network | Mock fallback + `llm_fallback: true` badge; decision unaffected |
| Offer field missing | `missing` → HOLD |
| Bad L2 / merchant signature | BLOCK; `/api/purchase` 409; evidence → `fraud_path`, 4837 |
| Exception for an old `offer_hash` | Ignored → 409 |
| Unknown `decision_id` / `offer_id` | 404 with plain message |
| Injection text in traveler/merchant data | Passed to the model as JSON data only; rules engine never reads free text |

## 8. What is live vs simulated (we say this honestly)

Live: VI credential creation + verification (rung 1), merchant signature check, rules engine, enforcement, Foundry extract/explain. Simulated: the shopping agent's choice, the merchant, payment, the dispute system, all identities and keys (labelled demo keys).

## 9. Definition of done

Maps 1:1 to the official Build Readiness Checklist — the working copy with checkboxes is `CHECKLIST.md` at the repo root.
