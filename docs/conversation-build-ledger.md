# SDD ledger — plan: docs/superpowers/plans/2026-10-13-conversational-intent.md
Task 1: complete (commits 986f0e0..9f62292, tests: .venv/bin/pytest -q → 56 passed, 1 warning in 1.05s)
Task 2: complete (commits 9f62292..33c565e, tests: .venv/bin/pytest -q → 69 passed, 1 warning in 1.13s)
Task 3: complete (commits 33c565e..0e37bc8, tests: .venv/bin/pytest -q → 69 passed, 1 warning in 1.08s)

Task 3: Ruling: allow specific traveler removal of a flagged condition during final review — a live experiment showed missing airports were incorrectly flagged as unsupported; a customer can edit what they authorize, while the AI still cannot discard conditions — cost if wrong: an extra review action and potential traveler error, preserved in signed evidence.
Task 4: Ruling: use modules for API and conversation while retaining proven review/exception/receipt handlers — minimizes regressions in exact consent gates — cost if wrong: the main view controller stays larger than ideal.
Task 4: complete (commits 0e37bc8..b9fa7f7, tests: .venv/bin/pytest -q → 70 passed, 1 warning in 1.11s)

Final: fixed short answers without question context — test_short_answer_is_bound_to_the_displayed_question and test_assistant_question_cannot_be_used_as_customer_source RED→GREEN, suite76/76.
Final: fixed overwritten source provenance — test_interpretation_snapshot_keeps_original_sources RED→GREEN, suite76/76; validated snapshots and source-message references are included in evidence.
Final: fixed unreviewable accumulated conditions — test_excessive_flags_reject_turn_without_destroying_reviewable_draft RED→GREEN, suite76/76.
Final: fixed interrupted canary visibility — test_interrupted_canary_becomes_visible_without_paid_replay RED→GREEN, suite76/76; stale jobs become unavailable without spending again.
Final: Ruling: promote disagreeing pipeline defaults to Important because the quality monitor must test the same inference as interactive requests — one shared audited default — cost if wrong: two calls rather than one for unconfigured development use.
Final: fixed default mismatch — test_unset_pipeline_uses_selected_audited_default RED→GREEN, suite76/76.
Final: Ruling: broader model accuracy remains limited to the recorded synthetic evidence — avoid extra paid experiments and disclose the direct-flight miss — cost if wrong: errors on untested requests still need traveler review.
Final: Ruling: verify hosted behavior after this local review and configure the daily platform scheduler — deployment checks belong to the release pass — cost if wrong: platform failures may occur between daily checks.
Final: Ruling: real commerce remains outside this synthetic prototype — preserve separate fixtures and payment simulation — cost if wrong: additional trusted merchant/payment integration is required before real purchases.
Final: Ruling: unchanged baseline retains its prior reviewed implementation — review only revision effects — cost if wrong: unrelated defects can remain outside this review.
Task 5: complete (commits b9fa7f7..50cce98, tests: .venv/bin/pytest -q → 76 passed, 1 warning in 1.16s)

Release: deployed source50cce98 to dpl_AanJqeeqf1ZXhFq6DbkSvN6wWyqe; stable public URL https://intent-judge-perfected.vercel.app. Hosted live two-stage conversation/approval/PASS-HOLD/409/exact exception/receipt/evidence/reload passed with no JavaScript page errors. Downloaded evidence digest and issuer signature verified; both interpretation snapshots, question binding and exact offer exception present. Mobile390 hotel explicit-offline full flow, keyboard focus, modal Escape and Quality deep-link reload passed without overflow.
CI: GitHub run38463770631 succeeded for50cce98; pytest and JS syntax steps succeeded.
Automation: Vercel project registered /api/internal/quality-check cron at07:00UTC for the deployed production id. Missing bearer secret401; authenticated hosted replay returned today's persisted passing report without new inference.
Budget: global99 reservations/$9.90 reserved, interactive36 today, evaluation60, monitor2. Recorded usage77997 prompt/21398 completion tokens. Reservation is not billing; unchanged lifetime200/$20 cap, no emergency increase.
Final: all Critical/Important findings reproduced RED then fixed GREEN; suite76/76. No deferred minors after re-grading the default mismatch.
Integration: retain victor/perfected, push the revised source and records, keep main untouched under Victor's existing branch/deployment instructions.

## Preflight decisions

Preflight: validated envelope is shared between baseline, guided and audit; AI stage never returns approval. Conversation sources bind original plus user turns, revision checked before and after inference. Purpose budget shares lifetime200/$20 and preserves old interactive counters.
Ruling: use existing gpt-oss deployment for controlled architecture comparison — current resource exposes no gpt-4.1-mini/gpt5-mini SKU; model engineering first needs measured prompt/process comparisons — cost if wrong: another model may offer better quality/latency. No new paid model created.
Ruling: graphical product direction is Swiss/minimal light workspace with charcoal navigation and teal actions — user rejected form-led editorial design; generated conversation image establishes geometry — cost if wrong: visual preference may need another iteration.
Spec/plan self-reviewed for source/consent budget authority. Prior user authorization overrides skill review handoffs; native inline execution plus one fresh final reviewer.
