# Vendor evidence result

Status: **DONE_WITH_CONCERNS** — packet assembly and offline tests complete; whole-app integration remains the API owner's work.

Completed October 12, 2026, before 13:27 EDT on `devin/vendor-evidence`, worktree `/Users/victor/Nueva-Generacion/.worktrees/devin-vendor-evidence`, base `f9848f1`. Continued the saved `tests/test_evidence.py`; nothing was discarded. Owned files only: `app/evidence.py`, `tests/test_evidence.py`, this result. No shared-model/VI/rules/AI/API/frontend edits, other-worktree writes, runtime changes, merge, or push.

Implementation/test commit: **`3ad58612dc503552ba8e493f91edc2a0d1ea6b0a`** (`Implement deterministic vendor evidence packet assembly`). This result is committed separately so it can reference the actual implementation SHA. Both commits carry `Generated with Devin` and `Co-Authored-By: Devin <devin@cognition.ai>`.

## Fixed contract

```python
build_packet(purchase, dispute_claim, decision, req, offer, exceptions,
             narrative=None) -> EvidencePacket
```

- Existing genuine Pydantic `ApprovedRequirements`, `FlightOffer`, `Decision`, and `ExceptionAcceptance` objects; no new Purchase model or generic category schema.
- `purchase` is a mapping or attribute object with a nonempty string `purchase_id`. Optional `decision_id`, `requirement_set_id`, `offer_hash`, and `offer_id`, when present, must match the supplied records exactly. A purchase-id-only object remains supported as specified; the caller must supply an actual server-stored purchase, not a client's allegation of purchase.
- The decision's requirement id and offer hash must match the supplied snapshots; hashes must be nonempty. Duplicate check ids, inconsistent links, or bad purchase ids raise `ValueError`; non-text claim/narrative raises `TypeError`. Do not silently join unrelated records or replace these errors with fabricated evidence.
- Return is the existing flat `EvidencePacket`; no conversation imports, mutable global state, wrapper, or new packet fields. Approved requirements, offer, all checks, and retained exceptions are independent deep copies. Original text/check messages remain data, never authority.
- `narrative` is an optional display-only string, preserved literally. Neither narrative nor `Decision.explanation` can change recommendation, reason code, exceptions, rationale, or `final_decision='dispute analyst'`.
- The builder consumes the server's verified merchant-offer snapshot and verification flags; it does not independently verify JWTs, re-run flight rules, enforce purchase, prove delivery, or create approvals. Invalid verification flags are preserved, not described as verified evidence.

## Consent and recommendation behavior

Accepted evidence requires exact `decision_id`, `offer_hash`, `check_id`, and `accepted_value == CheckResult.offer_value`; values are not trimmed, paraphrased, or case-normalized. Only failed/missing checks can have exceptions; APPROVAL, passed/unknown checks, BLOCK, and invalid signatures cannot. Invalid/stale exception records are excluded from `packet.exceptions`; the original input records are not changed.

Statements require an affirmative contextual phrase (`I accept …`, `I agree to …`, or `I approve …`) and cannot deny that acceptance. Bare OK/yes/empty acknowledgements or model approvals are insufficient. `I accept 3 connections, not nonstop` remains valid when its structured fields match exactly. This is deliberately limited English demo consent validation, not general natural-language understanding; keep the real exception route/enforcement validation aligned and use explicit structured acceptance UI copy.

Exception timestamps must be timezone-aware and no earlier than decision creation or traveler approval. If purchase `created_at` or `purchased_at` is provided, it must be an aware datetime or ISO timestamp and the exception cannot postdate it. With a purchase-id-only record, purchase chronology cannot be independently established; retain actual server timestamps in integration.

Deterministic recommendation precedence:

1. Invalid VI chain or merchant signature: `fraud_path` / `4837`, no accepted exceptions.
2. Recorded purchase against BLOCK, missing traveler approval, or uncovered failed/missing checks: `agent_platform` / `4853`. These recommendations require purchase/check records, not bare claims of bypass. Even an inconsistent PASS label cannot hide a recorded failed check.
3. Delivery/refund allegations or unsupported bypass allegations without relevant recorded evidence: `unclear` / `none`. The current fixed interface contains no authenticated actual-delivery evidence contract, so it never invents merchant fault from a claim or narrative.
4. Recognized approved-requirement preference disputes (or an exact check-id label) with matching passed/not-required checks or validated acceptance: `traveler` / `none`. Multiple identified preferences need all their checks. Missing/unmapped checks, unexplained HOLD, and unfamiliar claims: `unclear` / `none`.

Every rationale labels recommendations/reason codes advisory and exceptions **unsigned application records, not new VI authorizations**. Prototype codes are not certified/legal liability determinations. No vendor-win or liability-protection promise.

## Additive API trace attachment — preserve Josue's UI

The newer Josue update supersedes the older nested-envelope suggestion: `/api/disputes` must keep existing EvidencePacket fields at the response root. The API owner should attach the AI session's copied approval trace separately as an **additive root field**, not move the packet under `evidence_packet`:

```python
packet = build_packet(purchase, dispute_claim, decision, req, offer, exceptions)
response = packet.model_dump(mode="json")
response["conversation_trace"] = trace_for_requirements(req.requirement_set_id)
```

That call belongs in the API module, not `evidence.py`. The trace lookup returns a copied immutable application approval snapshot. Preserve `trace_status='application_record_not_user_signed_transcript'`; it contains literal words, follow-up answers, interpretations, and the approved snapshot, but **is not a user-signed transcript**. No trace should influence responsibility or be reconstructed from narrative. If a legacy purchase lacks a stored trace, report that absence rather than inventing one; the packet itself remains unchanged. Flat packet keys continue serving the current printable Intent Receipt; trace display is additive integration work.

Josue's latest shared `category='flight'` fields are additive; deep copies preserve declared shared fields without a schema migration. Integration must use the newer primary constraint **`urn:intent-judge:requirements`** and Josue's actual updated models/adapter. This worker intentionally does not alter the older adapter constant/models in the supplied `f9848f1` snapshot and imports neither constraint constant. Flights remain the only implemented category.

## Actual test proof

Runtime used without modifying its environment:
`/Users/victor/Nueva-Generacion/.worktrees/victor-rules/.venv/bin/python` (Python 3.12.13), always with this worker's workdir.

Red baseline: saved evidence test collection failed with `ModuleNotFoundError: No module named 'app.evidence'` (exit 2). First implementation: original **53 evidence tests passed**. Added regressions produced **3 failed / 85 passed** for unsupported delivery/refund/allegation findings; fixed them. Additional valid-consent-negation regressions produced **2 failed / 89 passed**; fixed them without accepting consent denials.

Final commands and captured results:

```text
MOCK_LLM=1 PYTHONDONTWRITEBYTECODE=1 /Users/victor/Nueva-Generacion/.worktrees/victor-rules/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_evidence.py
91 passed in 0.16s

MOCK_LLM=1 PYTHONDONTWRITEBYTECODE=1 /Users/victor/Nueva-Generacion/.worktrees/victor-rules/.venv/bin/python -m pytest -q -p no:cacheprovider
124 passed in 0.21s
```

The full count is 91 evidence + the 33 existing SDK/AI/conversation tests. Evidence coverage includes matching snapshots, attribute/mapping purchase IDs, exact accepted deviations/missing values, stale hash/decision/value/case/whitespace filtering, partial coverage, non-exceptable approval, fraud priority, recorded enforcement bypass, insufficient delivery proof, analyst authority, narrative/injection non-authority, deep-copy isolation, inconsistent IDs, duplicate checks, bare consent, timestamps, all named flight checks, and additive flight metadata preservation.

A real VI SDK round trip signs and verifies fixture B, passes the extracted four-segment offer and checkout hash into the builder, and preserves exact STOPS acceptance. Its `Decision` is explicitly constructed, not a fake rules implementation. Category compatibility is tested with model subclasses because this base predates Josue's additive fields; it is not a test of his actual integrated branch. `git diff --cached --check` also passed before the implementation commit.

## Integration concerns / remaining proof

- This branch has no real rules engine/product API/frontend assembly. The 124 tests are **not** proof of purchase HTTP 409/201, Josue's integrated flat receipt, full twelve-scenario enforcement, live Foundry, or the end-to-end demo. API owner still needs B HOLD → purchase 409 → exact acceptance → purchase 201 → flat receipt, plus tamper BLOCK.
- Match server-created exception formatting/value/timestamp and affirmative statements to these filters and the real `can_purchase`; never use receipt assembly as a substitute for checkout enforcement.
- No authenticated delivery-record interface exists here; merchant-delivery disputes need additional evidence and analyst review. Claim matching is limited demo vocabulary, not a universal dispute classifier.
- New shared category/constraint metadata and trace attachment must come from integration, not edits to these owned files. No secrets, real payments, or liability guarantees.
