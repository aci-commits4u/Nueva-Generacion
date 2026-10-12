"""DEV ONLY: run the app with FAKE rules_engine/evidence/foundry_client so the UI can be built and
checked before Victor's modules are merged. The web page shows a red "DEV FAKE ENGINE" banner.
Never use for the real demo: run `uvicorn app.main:app` once the real modules exist.

    .venv/bin/python scripts/dev_server.py        # http://localhost:8001/?dev=1  (PORT=8011 to change)
"""
import os
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import uvicorn  # noqa: E402

from tests.test_api_wiring import _fake_evidence, _fake_rules  # noqa: E402

fake_foundry = ModuleType("app.foundry_client")
fake_foundry.extract_requirements = lambda text, today: {
    "draft_requirements": {"origin_airports": ["JFK", "LGA", "EWR"], "destination_airports": [], "depart_date": "2026-10-20",
                           "depart_window": {"earliest": "06:00", "latest": "12:00"}, "max_stops": None,
                           "max_total_cents": 30000, "passengers": 1},
    "questions": ["Which Florida airport works for you?", "Is a nonstop flight required?"], "notes": "", "llm_fallback": True}
fake_foundry.explain = lambda decision, req: {
    "traveler_message": " ".join(c.message for c in decision.checks if c.status in ("fail", "missing")) or "This itinerary matches what you approved.",
    "suggested_next_step": "none", "llm_fallback": True}
fake_foundry.evidence_narrative = lambda packet: None

sys.modules["app.rules_engine"] = _fake_rules()
sys.modules["app.evidence"] = _fake_evidence()
sys.modules["app.foundry_client"] = fake_foundry

if __name__ == "__main__":
    from app.main import app
    uvicorn.run(app, port=int(os.getenv("PORT", "8001")))
