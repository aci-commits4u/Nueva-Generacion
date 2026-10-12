# Copilot instructions — Intent Judge
Follow `AGENTS.md` at the repo root. Most important rules:
- The AI (LLM) never approves a purchase; only `app/rules_engine.py` returns PASS/HOLD/BLOCK.
- Decide against the traveler-**approved** requirements (`ApprovedRequirements`, VI constraint `urn:intent-judge:flight-requirements`) and the **merchant-signed** `checkout_jwt` offer — never `prompt_summary` or agent descriptions.
- Missing data → HOLD. `/api/purchase` returns 409 unless PASS or every failed/missing check has a recorded, specific exception for the same `offer_hash`.
- Integer cents for money. Synthetic data only. Secrets from env vars only. Must run with `MOCK_LLM=1`.
- Python 3.11, FastAPI, Pydantic v2, pytest, vanilla JS frontend.
Context: `docs/00-index.md`.
