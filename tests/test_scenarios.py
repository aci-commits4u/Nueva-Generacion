"""All twelve shared scenarios traverse actual merchant signing and serialized VI verification."""
import pytest

from app.fixtures_loader import scenarios
from app.store import store
from tests.test_enforcement import api, real_client, approve, check


@pytest.mark.parametrize("scenario", scenarios(), ids=lambda s: f"scenario-{s['id']}")
def test_all_twelve_real_signed_api_scenarios(real_client, scenario):
    overrides = dict(scenario["requirements_override"])
    if "prompt_summary" in scenario:
        overrides["source_text"] = scenario["prompt_summary"]
    rid = approve(real_client, **overrides)
    options = {}
    if "tamper" in scenario:
        options["tamper"] = scenario["tamper"]
    if "injection" in scenario:
        options["note"] = scenario["injection"]
    if "agent_claim" in scenario:
        options["note"] = scenario["agent_claim"]
    data = check(real_client, rid, scenario["offer"], **options)
    decision = data["decision"]
    assert decision["result"] == scenario["expected"]["result"]
    for status, key in (("fail", "failed"), ("missing", "missing")):
        if key in scenario["expected"]:
            assert [c["check_id"] for c in decision["checks"] if c["status"] == status] == scenario["expected"][key]
    if decision["result"] != "BLOCK":
        assert decision["vi_chain_valid"] and decision["merchant_signature_valid"]
        assert not data["vi_errors"]
    if scenario["id"] == 3:
        assert next(c for c in decision["checks"] if c["check_id"] == "STOPS")["status"] == "not_required"
    if scenario["id"] in (2, 9, 10, 11):
        assert len(data["offer"]["segments"]) == 4
        assert "3" in next(c for c in decision["checks"] if c["check_id"] == "STOPS")["offer_value"]
    purchase = real_client.post("/api/purchase", json={"decision_id": decision["decision_id"]})
    assert purchase.status_code == (201 if decision["result"] == "PASS" else 409)
    assert bool(store.purchases) is (decision["result"] == "PASS")
