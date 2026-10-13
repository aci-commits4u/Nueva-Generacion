# SDD ledger — plan: docs/superpowers/plans/2026-10-13-intent-judge.md
Pre-flight: Task 1 approved field schema consumed by Task 2 signing and Task 3 API; one common Pydantic object pinned by profile digest.
Pre-flight: Task 2 verified bundle consumed by Task 3 gate; raw client offer never passed to rules.
Pre-flight: Task 3 session storage consumed by Task 4 atomic call reservation; table ETags and SQLite transactions provide concurrency control.
Pre-flight: Task 4 draft consumed by Task 5; AI mode and uncertainty surfaced, no inferred approval.
Pre-flight: Task 6 hosts the same API; local memory excluded from authority.
Task 1: complete (commits bde8429..6b91d76, tests: .venv/bin/pytest -q → 11 passed in 0.01s)
Task 2: complete (commits 6b91d76..a823b03, tests: .venv/bin/pytest -q → 18 passed in 0.04s)
Task 3: complete (commits a823b03..a0ad2e2, tests: .venv/bin/pytest tests/test_rules_engine.py tests/test_vi.py tests/test_enforcement.py -q → 24 passed, 1 warning in 0.34s)
Task 4: complete (commits a0ad2e2..005714b, tests: .venv/bin/pytest -q → 31 passed, 1 warning in 0.53s)
Task 5: security correction — regression found exported actor identifiers were session credentials. Replaced with irreversible synthetic pseudonyms; evidence privacy test RED→GREEN. All customer signing remains a clearly synthetic, server-managed demo identity.
Task 5: live provider test — gpt-oss JSON mode returned invalid semantic envelope. Normal JSON instructions with low reasoning returned valid flight, hotel, unsupported general, and injection drafts. Strict validation and visible errors retained.
Task 5: complete (commits 005714b..abc965d, tests: .venv/bin/pytest -q → 42 passed, 1 warning in 0.91s)

Final: fresh-context whole-branch reviewer reported no Critical findings and four Important findings.
Final: fixed explanation GET/POST mismatch — browser_explanation.js GET405 RED to POST200 GREEN; suite50/50.
Final: fixed unchecked extra payment reference — test_extra_checkout_reference_cannot_receive_unchecked_pass RED to GREEN; suite50/50.
Final: fixed hosted entity capacity — test_full_decision_allowance_and_receipt_fit_hosted_entity RED to GREEN; actual Azure 25 checks/purchase/retry/recovery PASS; suite50/50.
Final: fixed silent offline unsupported omission — five test_offline_preserves_unrecognized_substantive_text cases RED to GREEN; review textbox missing RED to recorded condition and both offers HOLD GREEN; suite50/50.
Final: regraded duration rounding Important because a traveler could receive an itinerary beyond the approved maximum; test_fractional_duration_is_never_rounded_down RED to GREEN; suite50/50.
Final: Ruling: Foundry compatibility uses plain JSON instructions plus strict validation — existing deployment fails JSON response-format envelopes — cost if wrong: visible extraction errors.
Final: Ruling: Azure Table compressed atomic records — preserve receipt transaction and fit documented entity limits — cost if wrong: storage availability failure.
Final: Ruling: $0.10 per bounded inference reservation and $20 ordinary lifetime cap — protects student budget without automatic emergency use — cost if wrong: Azure billing and unrelated activity need separate inspection.
Final: Ruling: preserve branch and publish separate project under existing explicit authorization — no main merge — cost if wrong: integration remains a separate team decision.
Final: Ruling: reviewer declined-to-judge behaviors stand within synthetic scope — each behavior, rationale and cost is recorded exhaustively in docs/final-review.md — costs range from extra review clicks to prototype availability and authentication limitations.
Final: no unresolved authorization finding; residual limitations documented in final-review.md.
Task 6: production proof — public alias HTTP200; desktop/mobile live Foundry extraction+explanation full flow PASS; 390px no overflow and receipt reload PASS; hosted25check capacity PASS; downloaded evidence digest and issuer signature PASS; Vercel error query no matching logs.
Task 6: complete (commits abc965d..e9569e9, tests: .venv/bin/pytest -q → 50 passed, 1 warning in 1.11s)
