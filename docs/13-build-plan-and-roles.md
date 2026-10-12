# Build plan, roles, checkpoints

## Roles
- **Jossue** — project lead; Foundry setup; `vi_adapter.py`; demo page; live demo; backup recording.
- **Victor** — lead AI builder; `rules_engine.py` (with tests); `foundry_client.py` prompts + mock; technical Q&A.
- **Alex** — deck story, numbers, competition slide, pitch close; drafts demo narration with Victor.
- **Ryan** — evidence: quotes, spec citations, traceability table slide; hook & insight in pitch; QA on copy (no overclaims).
- **Barbara** — test set fixtures and results report; security/RAI slide; enforcement tests review; roadmap in pitch.

## Order of work (T = build start)
| By | Milestone | Owner | Done when |
|---|---|---|---|
| T+0:20 | Repo scaffold, `.env.example`, requirements, FastAPI hello, Foundry deployment created | Jossue | `uvicorn` serves page; playground answers |
| T+0:50 | `rules_engine.py` + unit tests green | Victor | tests in `07-rules-engine-spec.md` pass |
| T+1:20 | `vi_adapter.py`: L1/L2 (custom constraint)/merchant checkout_jwt/L3; verify chain + merchant sig | Jossue | scenario 1 & 2 credentials verify; tamper → invalid |
| T+1:40 | API endpoints + enforcement + `test_enforcement.py` | Victor + Jossue | 409 behaviors pass |
| **T+1:50** | **Checkpoint: one scenario end to end (ugly OK)** | All | Offer B → HOLD → 409 → exception → purchase → evidence |
| T+2:30 | `foundry_client.py` live + mock; demo page complete | Victor, Jossue | demo script runs twice in a row |
| T+2:45 | 12 scenarios + report table | Barbara | 12/12 or known gaps listed |
| T+3:00 | **Build freeze**; backup video + screenshots | Jossue | files saved |
| T+3:00→ | Deck finalized, rehearsal ×2 with timer | Alex, Ryan, all | 5:00 or less |
If behind at the checkpoint: drop UI polish, Prompt 3 (evidence narrative), and the vague-request clarify demo — **never** drop rules engine, enforcement, or the Offer B HOLD.

## Definition of done (maps to official Build Readiness Checklist)
- [ ] Core journey works end to end (approve → check → hold → exception/cancel → purchase enforcement → dispute packet)
- [ ] Discovery alignment: client's three-layover example is scenario 2
- [ ] Scope: one fully working category (flights); category-neutral by design; no extra features
- [ ] We can state live vs simulated (see Q&A)
- [ ] AI tested with varied inputs incl. injection (scenario 11)
- [ ] Error handling: model timeout → mock fallback; missing fields → HOLD; bad signature → BLOCK
- [ ] No secrets in repo/UI/logs; synthetic data only
- [ ] Dependencies verified (Foundry deployment, VI install)
- [ ] Demo path rehearsed; owners assigned
- [ ] Backup video + screenshots
- [ ] Concern → solution table in deck
