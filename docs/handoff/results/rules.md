# Rules / consent delivery

Base: `f9848f13a369d5ac4210a4e6fa3f5e45b9fc8063`.
Implementation commit: `ffc441eb663eec2ee7913770c58430429f178a77` on `devin/rules-consent`.
This results record is committed separately after the implementation so its SHA is exact.
Only owned files changed: `app/rules_engine.py`, `tests/test_rules_engine.py`,
`tests/test_purchase_eligibility.py`, and this record. Existing saved tests were
continued, not discarded. No model, adapter, frontend, other worktree, or environment changes.

## Stable contract

```python
evaluate(req: ApprovedRequirements, offer: FlightOffer | None,
         vi_chain_valid: bool, merchant_signature_valid: bool) -> Decision
can_purchase(decision: Decision,
             exceptions: list[ExceptionAcceptance]) -> tuple[bool, str, list[str]]
# (allowed, plain-English reason, uncovered_check_ids)
```

- Integrity failures BLOCK before reading offer (including offer=None). Missing
  approval HOLDs with a non-exceptable APPROVAL check.
- Eleven flight checks, in documented order: ORIGIN, DESTINATION, DATE,
  DEPART_WINDOW, ARRIVE_BY, STOPS, PRICE, CURRENCY, CABIN, REFUNDABLE, PASSENGERS.
  All applicable unknown fields are `missing`; unspecified optional requirements
  are `not_required`. Four segments mean THREE connections.
- Integer cents, inclusive price/clock boundaries, timezone-aware airport-local
  dates and clocks; a next-day arrival never passes same-day arrive_by.
- UUID decision id, UTC created_at, exact supplied offer hash, no input mutation.
  No LLM/network imports or source_text/summary/narrative decision authority.
- PASS eligibility still requires nonblank identity/hash, valid signature flags,
  aware nonfuture creation time, complete consistent checks, and no fail/missing.
  BLOCK, incomplete/duplicate/unknown checks, missing approval, and contradictory
  PASS/HOLD objects cannot be purchased.
- HOLD needs a record for EVERY fail/missing check with exact decision_id,
  offer_hash, check_id, and accepted_value. accepted_at must be aware and between
  decision creation and current time (inclusive). Duplicates do not cover another
  check, and old decisions/hashes cannot reuse acceptance. Missing facts can be
  accepted only with a check-specific acknowledgment of `Not stated`.

## Consent wording compatible with the real UI

Accepted for B's STOPS failure (also accepts a final period):

- `I accept 3 connections (STOPS) on offer OFFER-B-3STOP` — Josue UI.
- `I accept 3 connections on this itinerary` — documented wording for STOPS.
- `I accept STOPS: 3 connections` — structured wording for any specific check.

The UI's multiple clauses joined by `; ` are accepted when every clause is
specific. Each exception record covers only its own exact check/value; a combined
statement alone cannot replace missing records. Bare OK, negations, partial
coverage, wrong binding/value, and appended instructions/model claims are rejected.

The shared Decision has no offer_id: UI offer labels are display text, not
independently cross-checked against an id in this function. The authoritative
binding is the separately recorded exact decision_id and offer_hash. Mixed offer
labels in a combined UI statement are rejected. If human-readable offer-id
cross-checking is desired, the integration route has the stored offer and can
validate that label without changing this three-value contract.

## Exact test proof

Working directory: `/Users/victor/Nueva-Generacion/.worktrees/devin-rules-consent`.
Existing interpreter: `/Users/victor/Nueva-Generacion/.worktrees/victor-rules/.venv/bin/python`.
Commands run with `MOCK_LLM=1 PYTHONDONTWRITEBYTECODE=1`:

```sh
/Users/victor/Nueva-Generacion/.worktrees/victor-rules/.venv/bin/python -m pytest -q tests/test_rules_engine.py tests/test_purchase_eligibility.py
# 175 passed in 0.22s
/Users/victor/Nueva-Generacion/.worktrees/victor-rules/.venv/bin/python -m pytest -q
# 208 passed in 0.28s
```

TDD evidence: initial preserved tests failed collection because the module was
absent. With evaluate implemented and eligibility deliberately fail-closed, the
executable tests reported **17 failed, 145 passed**; failures included exact UI,
documented and structured wording, multi-check coverage, PASS eligibility,
timestamp boundaries, and the real signed-offer roundtrip. Implementing eligibility
made **162 pass**. Additional real SDK scenario coverage brought the final owned
suite to **175** and full suite to **208**. `git diff --cached --check` passed.

All 12 fixture scenarios also run through actual merchant signing and SDK chain
verification (including tampered L2), not just supplied True/False flags. A forged
merchant key returns offer=None and BLOCK. Signed B has STOPS HOLD; its exact
record permits eligibility. These are module/SDK tests, NOT proof of HTTP409/201,
receipt/UI behavior, or live Foundry. API integration must run those separately.

## Integration responsibilities / remaining limits

1. Use the server-stored decision and exceptions; do not accept a client-supplied
   PASS. Pass requirements bound to successfully verified L2 and the verified
   merchant payload, not summaries or evidence-only decoding helpers.
2. Preserve Josue's additive `category='flight'` and PRIMARY VI namespace
   `urn:intent-judge:requirements` in integration. This module has no URN dependency
   and does not change public models. No other category rules were added.
3. Currency None/blank/omitted on a FlightOffer is missing, even with the old model's
   implicit USD default. The base adapter still substitutes USD during payload
   parsing; once a parser explicitly inserts that default, rules cannot recover
   absence. Integration owns removing that substitution and optional currency None.
   The adapter already converts totals without included taxes/fees to None.
4. Exceptions are application records, not newly signed VI credentials. Signature
   validity proves integrity under demo keys, not delivery, certification, or liability.
5. No HTTP/product API was added here; integration owns B HOLD -> purchase409 ->
   exact UI acceptance -> purchase201 -> Intent Receipt, plus tamper BLOCK.
