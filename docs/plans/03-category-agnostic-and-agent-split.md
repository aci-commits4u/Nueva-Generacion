# Plan 3 — Category-agnostic Intent Judge + agent work packages (Jossue's half / Victor's half)

> **Status: DRAFT — pending confirmation by Jossue + Victor.** Supersedes D3 ("airline bookings only") and the "flights only" scope lines in `docs/04`, `docs/13`, `CHECKLIST.md`. AGENTS rules 1–10 are **unchanged** — none of them depended on flights.
> Written Oct 12, 2026. Trigger: team finding that the product is not limited to flights; flights are only the demo.

> **Update (judging guidance from the team): the pitch must show innovative thinking, be understood by a non-technical listener, appeal broadly, and be pitchable to Mastercard through a Microsoft employee's lens. Judges are not scoring tech stack or build sophistication.**
> Consequence: treat §2's generic engine as the *architecture story and roadmap*, not a build target. **Recommended build = "C0-lite"**: add a `category` field and the category-neutral constraint URN (`urn:intent-judge:requirements`) to the existing flight code; keep Victor's flight engine as is; hotel pack only as a stretch after G3. §3's agent split still applies, scoped to finishing the flight path and polishing the demo. The freed time goes to the story: see the reply that accompanies this update (tagline, "Intent Receipt", Microsoft lens, ask).

## 1. The product claim (what Mastercard should see)

> **Intent Judge is a conformance layer for agentic commerce: for *any* purchase where a person's approved intent can be compared with a merchant-signed order, it holds the agent to what the person approved — and produces the evidence when it's disputed.**

Why this is genuinely useful beyond one case:
- Mastercard's Agent Pay / Verifiable Intent (VI) will carry purchases in every category; each category has its own "not as described" disputes (travel, lodging, retail, subscriptions).
- The hard part of every category is identical: structure the person's words → person approves → compare with merchant-signed data → hold on any gap → evidence. Only the *field list* differs.
- So the product is **one engine + category packs**. A new category is a data file, reviewed like config — not a rewrite. That is also the roadmap: register `mandate.checkout.*` constraint types in the VI spec, one per pack.

Honest scope line for judges: **flights and hotels are built and tested; retail is a stretch; the engine is category-neutral by construction.**

## 2. Design: generic core + declarative packs

```
pack (data + tiny derive fn) ─┐
                              ├─► rules_engine.evaluate(req, offer, chain_ok, sig_ok)  # generic, deterministic
ApprovedRequirements{category, values{}} ─┘                                            # same PASS/HOLD/BLOCK
Offer{category, attributes{}, total_cents, ...}  (parsed ONLY from merchant-signed payload)
```

**Pack** = `app/packs/<category>.py` exporting:
- `CATEGORY`, `DISPLAY_NAME`
- `Requirements` — a Pydantic model for `values` (validation + JSON schema fed to the extract prompt)
- `derive(attributes: dict) -> dict` — turns merchant attributes into flat comparable values (e.g. flights: `stops = len(segments)-1`, `depart_time`, `origin`); `None` means *missing*
- `CHECKS: list[CheckDef]` — declarative rows:
  `{check_id, req_field, offer_attr, op, applies, requirement_text, fail_msg, missing_msg}`
  with `op ∈ {eq, in_set, lte, gte, time_between, time_lte, is_true}` and `applies ∈ {always, if_set, if_true}`
- `clarify_hints` — which fields are mandatory (drives "ask ≤2 questions")
- `reason_code_hint` — per-category dispute mapping used by `evidence.py`

The generic evaluator implements exactly `docs/07`'s semantics: BLOCK on invalid chain/signature → APPROVAL gate → run every check → PASS iff all `pass|not_required`; requirement set + offer attr `None` → `missing` → HOLD. The 12 scenarios in `docs/10` stay the acceptance suite — they are pack-agnostic outcomes.

### Contract changes vs what is on `jossue/build` now
| Item | Today | After |
|---|---|---|
| Requirements model | `ApprovedRequirements` with flight fields | `ApprovedRequirements{requirement_set_id, category, values: dict, source_text, approved_by_traveler, approved_at}`; `values` validated by the pack's `Requirements` |
| Offer model | `FlightOffer{segments,…}` | `Offer{category, offer_id, merchant_id, merchant_name, attributes: dict, total_cents, currency, offer_hash}`; flight `segments` live inside `attributes` |
| `CheckResult.check_id` | closed `Literal` of 12 ids | `str` (ids come from the pack) |
| VI constraint | `urn:intent-judge:flight-requirements` | `urn:intent-judge:requirements` with `{category, requirement_set_id, values, approved_at}` |
| Merchant `checkout_jwt` | `air_itinerary` item | `cart.items[0] = {sku, type: "<category>", attributes{…}, quantity}`, `cart.total = {amount_cents, currencyCode, includes_taxes_and_fees}` |
| Function signatures (Plan 1 §4) | flight-typed | **same names/arity**; types become the generic models; `extract_requirements(text, today, category)` gains `category` |
| API | `/api/check {requirement_set_id, offer_id}` | unchanged; `/api/intent/extract` and `/approve` accept `category`; `/api/scenarios` lists categories |

## 3. Agent work packages

Each package is one agent (a Claude Code session in its own git worktree) that **fully owns** a deliverable: a brief, the files it may touch, tests, and a "done" it can verify alone. Humans merge into their own branch (`jossue/build` / `victor/rules`); gates merge to `main`.

Run one: `git worktree add ../ij-<ID> -b <owner>/<id> <owner-branch>` → open Claude Code there → *"Read docs/plans/03-category-agnostic-and-agent-split.md §3 and complete package <ID>. Touch only the files it owns."*

### C0 — Contract (blocks everything; Jossue's session, ≈20 min)
- **Owns:** `app/models.py`, `app/packs/base.py` (CheckDef, ops, pack protocol), `app/packs/__init__.py` (registry), update `fixtures_loader.py`
- **Done when:** models + `CheckDef` types import cleanly; flight offers re-expressed as generic `Offer` in `offers.json`; pushed to `jossue/build`; Victor can fetch. Existing VI/API tests are updated or marked `xfail(reason="pending J1/J2")`.

### Jossue's agents (platform, trust, UX)
| ID | Deliverable | Owns | Done when |
|---|---|---|---|
| **J1 VI & credentials** | `vi_adapter` category-neutral: new URN/constraint payload, generic merchant `checkout_jwt` (`attributes`), `verify_and_extract` returns generic `Offer`; keep tamper/forged/injection behaviour | `app/vi_adapter.py`, `tests/test_vi_adapter.py` | round-trip for flight **and** hotel offers; tamper → invalid; forged merchant → no offer; `signed_requirements` returns `{category, values}` |
| **J2 API & store** | routes carry `category`; `/api/scenarios` lists categories/offers; 501/409/exception rules unchanged | `app/main.py`, `app/store.py`, `tests/test_api_wiring.py` | wiring tests green with fakes, then against Victor's real modules after merge |
| **J3 Demo UI** | page renders the requirement card and checks table **from pack metadata** (no hard-coded flight fields); category switcher; 3 columns per Plan 2 §3; exception + dispute modals; reset | `web/*` | click-through of Offer A → B → exception → dispute works; switching category changes the form/offers with no code change |
| **J4 Demo ops** (human + agent) | Foundry deployment + portal agent (manual), `.env`, backup video, screenshots, live-vs-simulated table | `demo-backup/*`, `CHECKLIST.md` ticks | G4/G5 items in checklist |

### Victor's agents (decisions, AI, evidence)
| ID | Deliverable | Owns | Done when |
|---|---|---|---|
| **V1 Rules engine** | generic `evaluate` + `can_purchase` + **flight pack** `CHECKS` reproducing `docs/07` | `app/rules_engine.py`, `app/packs/flight.py`, `tests/test_rules_engine.py` | all `docs/07` unit cases + 12 scenarios from fixtures green; no network, no LLM import |
| **V2 Second category** | **hotel pack** (city, check-in/out, max total, min stars, refundable, guests) with derive + checks + fixtures + 6 tests; stretch: retail pack | `app/packs/hotel.py` (`retail.py`), `app/fixtures/hotel_offers.json`, `tests/test_packs_hotel.py` | HOLD on non-refundable/over-budget/missing-star-rating; PASS on clean offer; added with **zero** edits to `rules_engine.py` (that is the proof) |
| **V3 LLM** | `foundry_client`: extract (prompt built from the pack's JSON schema + `clarify_hints`), explain, evidence narrative; `MOCK_LLM`; 3 s timeout → mock; injection-safe | `app/foundry_client.py`, `tests/test_injection.py` | flight + hotel sentences extract correctly in mock mode; "Florida cheap Oct 20" yields ≤2 questions; injected text changes nothing |
| **V4 Evidence** | generic `build_packet` + responsibility table from `docs/07`, `suggested_reason_code` via pack hint | `app/evidence.py`, `tests/test_evidence.py` | the 3 evidence tests in `docs/10`; works for flight and hotel purchases |

### Dependency order
```
C0 ──► J1, V1, V3, V4 (parallel) ──► J2 ──► [G3 end-to-end, flights]
 └──► V2 (needs V1's CheckDef semantics; can start once C0 lands)      J3 starts when J2's response shapes are stable
G3 ──► hotel end-to-end (V2 + J1/J3 category switch) ──► G4 rehearsal
```

## 4. Schedule (relative to now; freeze unchanged — **confirm the real clock time**)
| Mark | Milestone |
|---|---|
| +0:20 | **C0 pushed** (contract v2) |
| +1:00 | V1 green on flight pack; J1 green; V3 mock extract; V4 packet |
| **+1:20** | **G3: Offer B → HOLD → 409 → exception → 201 → dispute, end to end (flights)** |
| +1:50 | V2 hotel pack green; J3 category switcher; hotel end-to-end |
| +2:15 | G4: demo runs twice; G5: scenarios 12/12 + hotel cases |
| freeze | bug fixes only |

**Cut line (decide at G3, not before):** if the generic evaluator isn't green at +1:00, ship V1 as flight-only *behind the same pack interface*, drop V2 to a data-only hotel pack shown in Q&A, and tell judges honestly: "category-neutral by design; flights built." Never cut enforcement (409), the Offer B HOLD, or any AGENTS rule.

## 5. Demo and pitch impact
- Main path stays flights (client's three-layover example) — unchanged.
- **New 12–15 s beat:** switch the category selector to *Hotel*; the requirement card and offers change; a non-refundable $410 stay against "refundable, under $400" → HOLD. Line: **"Same engine. New category is a data file."** To stay inside 1:40, shorten the Clarify beat and merge the Offer A beat into one line; the dispute stays.
- Pitch headline changes from "flight checker" to **"a conformance layer for every agent purchase"**; the problem slide uses the cross-category chargeback figures already in `docs/03`; roadmap = registering pack constraints in the VI spec.
- Docs to update after confirmation: `AGENTS.md` (product sentence, tech/layout), `README.md`, `docs/04` scope, `docs/14` (new D14 superseding D3), `docs/13`/`CHECKLIST.md` scope lines, `docs/12` pitch headline.

## 6. Risks
| Risk | Mitigation |
|---|---|
| Victor is mid-build on the flight-typed engine | V1 keeps his check logic; only the data shape moves. Scenarios are the safety net. He should push whatever he has to `victor/rules` now. |
| Generalising slows the checkpoint | Cut line above; G3 target stays flights. |
| Over-claiming | Say "built and tested: flight, hotel"; "intent-checked" wording rule unchanged. |
| Parallel agents collide | Disjoint file ownership per package; worktree per agent; only `models.py`/`packs/base.py` are shared and frozen by C0. |
| Agents drift from AGENTS.md | Every brief starts with "Read AGENTS.md rules 1–10; they override this brief." |

## 7. Decisions to confirm
| ID | Decision | Recommendation |
|---|---|---|
| D-G | Generic engine + declarative packs (this plan) instead of flight-only code | **Yes** |
| D-H | Categories built: flight (full) + hotel (full); retail only if time | **Yes** |
| D-I | Package split as in §3 (J1–J4 / V1–V4) | **Yes** — swap any package if you or Victor want a different load |
| D-J | New D14 in `docs/14` superseding D3; reword pitch/scope docs | **Yes**, after D-G |
