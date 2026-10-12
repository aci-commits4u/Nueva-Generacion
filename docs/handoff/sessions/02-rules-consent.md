# Devin session 2 — deterministic offer checks and exact consent

You own rule evaluation and purchase eligibility. Work on `devin/rules-consent` from the saved victor/rules snapshot in your own worktree. You are not alone: preserve others' edits and edit only your files. Read AGENTS.md, DEVIN-HANDOFF.md, docs/handoff/README.md, docs/07-rules-engine-spec.md, docs/10-test-plan.md, shared models, and fixture loader. AI/conversation is a separate session; evidence and API have other owners. Do not modify their code, shared models/fixtures/SDK adapter, or frontend.

Own `app/rules_engine.py`, `tests/test_rules_engine.py`, `tests/test_purchase_eligibility.py`, and `docs/handoff/results/rules.md`.

Implement:

```python
evaluate(req, offer: FlightOffer | None, vi_chain_valid: bool,
         merchant_signature_valid: bool) -> Decision
can_purchase(decision, exceptions) -> tuple[bool, str, list[str]]
```

The three returned values are allowed, plain-English reason, uncovered_check_ids. Existing docs may show two: use this fixed handoff contract.

Rules consume only traveler-approved requirements tied to verified L2 and fields from verified merchant checkout JWT. No source_text/prompt_summary, AI narrative, agent-described itinerary, or model call in this module. Invalid chain/signature => BLOCK before accessing offer (which can be None). Unapproved requirements => HOLD with APPROVAL missing, never exceptable. Applicable missing offer field => HOLD/status missing. Evaluate all eleven documented checks; optional unspecified requirement => not_required. New Decision id, UTC creation time, exact offer hash, complete structured messages/values. Budget integer cents; airport-local dates/times, inclusive boundaries; empty itinerary missing; next-day arrival cannot satisfy same-day arrive_by.

Eligibility is fail-closed. PASS requires a nonempty verified offer hash, valid flags, no contradictory fail/missing checks, and no missing approval. BLOCK never purchasable. HOLD requires meaningful unresolved checks and an explicit matching exception for EACH fail/missing check, bound to decision_id, exact offer_hash, check_id, exact accepted_value, specific traveler statement, and timestamp. Reject bare OK, partial coverage, wrong hash/decision/value, explanation-based authority, APPROVAL exceptions, and inconsistent decisions. Do not infer acceptance from AI/chat text. Backend stores decisions/exceptions and calls this function; your pure function does not prove HTTP409 until API integration tests run.

Write meaningful failing tests first, then code. Minimum outcomes: A PASS; B HOLD with THREE connections/STOPS fail; missing signature plus offer=None BLOCK; approval missing HOLD. Test all fields and boundaries, $300 pass/$300.01 HOLD, missing refundability, unknown price, wrong date/time, multiple failures, and full exact/partial/wrong exception matching. The source fixture has twelve scenarios; your pure tests are not a substitute for real signed/API scenarios.

Done: full suite green; no LLM dependency; signatures compatible; concise results/rules.md with actual test count/commit and the three-value purchase contract. Session 4 consumes these functions. Commit only owned files and do not merge/push main. Flights are the concrete rule set for a commerce product; do not build other categories now.
