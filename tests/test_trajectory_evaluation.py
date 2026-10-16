"""Harness-only checks; these tests never exercise a provider or a live URL."""

from copy import deepcopy
import os

from evals.trajectories import (ApiResult, ReplayApiSession, TrajectoryError,
                                TrajectoryRunner, _digest, _ledger_state_check,
                                _pipeline_metadata, _profile_digest,
                                _validate_evidence, _validate_live_provenance,
                                load_trajectory_set, score_live_row,
                                validate_trajectory_set)


def test_exposed_development_set_has_twelve_balanced_families():
    payload = load_trajectory_set()
    validate_trajectory_set(payload)
    assert len(payload["families"]) >= 12
    assert {domain: sum(item["domain"] == domain for item in payload["families"])
            for domain in ("flight", "hotel", "general")} == {
                "flight": 4, "hotel": 4, "general": 4,
            }
    for family in payload["families"]:
        assert family["semantic_adjudication"]["status"] == "pending_blinded_adjudication"
        assert all("expected_fields" in turn for turn in family["turns"])


def test_default_runner_is_fixture_validation_and_does_not_mutate_environment():
    before = dict(os.environ)
    report = TrajectoryRunner(load_trajectory_set(), live=False).run()
    assert report["mode"] == "offline_harness_validation"
    assert len(report["rows"]) == 12
    assert report["fixture_rows"] == 12
    assert report["primary_complete_denominator"] == 0
    assert all(row["status"] == "not_run" for row in report["rows"])
    assert dict(os.environ) == before


def test_replay_session_is_explicitly_http_like_and_has_no_retry():
    session = ReplayApiSession({("GET", "/api/session"): {"ai_calls": 0}})
    first = session.request("GET", "/api/session")
    second = session.request("GET", "/api/session")
    assert first.ok and second.ok
    assert len(session.requests) == 2


def test_live_runner_rejects_same_endpoint_before_any_api_transition():
    calls = []

    def factory(url):
        calls.append(url)
        return ReplayApiSession()

    runner = TrajectoryRunner(load_trajectory_set(), {"A": "https://dev.example", "B": "https://dev.example"},
                              live=True, max_conversations=2, max_model_calls=8,
                              session_factory=factory)
    try:
        runner.run()
    except TrajectoryError as exc:
        assert "distinct" in str(exc)
    else:
        raise AssertionError("same A/B endpoint must be rejected")
    assert calls == []


def test_live_runner_rejects_wrong_engine_contract_without_post():
    class ContractSession(ReplayApiSession):
        def request(self, method, path, body=None):
            if path == "/api/health":
                return ApiResult(200, {"status": "ok", "environment": "development"})
            if path == "/api/session":
                return ApiResult(200, {"environment": "development", "ai_calls": 0})
            if path == "/api/ai/status":
                return ApiResult(200, {"pipeline": "adaptive_fast", "available": True})
            return super().request(method, path, body)

    sessions = []
    def factory(url):
        session = ContractSession()
        sessions.append(session)
        return session

    runner = TrajectoryRunner(load_trajectory_set(), {"A": "https://a.example", "B": "https://b.example"},
                              live=True, max_conversations=2, max_model_calls=8,
                              session_factory=factory)
    try:
        runner.run()
    except TrajectoryError as exc:
        assert "engine mismatch" in str(exc)
    else:
        raise AssertionError("wrong B engine must be rejected")
    assert all(not session.requests for session in sessions)


def test_preflight_initializes_cookie_session_before_session_scoped_status():
    class SessionScopedStatus(ReplayApiSession):
        def __init__(self, pipeline):
            super().__init__()
            self.pipeline = pipeline
            self.initialized = False

        def request(self, method, path, body=None):
            if path == "/api/health":
                return ApiResult(200, {"status": "ok", "environment": "development"})
            if path == "/api/session":
                self.initialized = True
                return ApiResult(200, {"environment": "development", "ai_calls": 0})
            if path == "/api/ai/status":
                if not self.initialized:
                    return ApiResult(401, {"detail": "Start a demo session first."})
                return ApiResult(200, {"pipeline": self.pipeline, "available": True})
            return super().request(method, path, body)

    runner = TrajectoryRunner(
        load_trajectory_set(), {"A": "https://a.example", "B": "https://b.example"},
        live=True, max_conversations=2, max_model_calls=8,
        session_factory=lambda url: SessionScopedStatus("adaptive_fast" if "a.example" in url else "ledger"),
    )
    runner._validate_arm_contracts()
    assert runner._arm_contracts["A"]["session_init"]["status"] == 200


def test_preflight_rejects_missing_cookie_session_before_status_check():
    class MissingSession(ReplayApiSession):
        def request(self, method, path, body=None):
            if path == "/api/health":
                return ApiResult(200, {"status": "ok", "environment": "development"})
            if path == "/api/session":
                return ApiResult(401, {"detail": "Start a demo session first."})
            if path == "/api/ai/status":
                raise AssertionError("status must not be queried before session initialization")
            return super().request(method, path, body)

    runner = TrajectoryRunner(
        load_trajectory_set(), {"A": "https://a.example", "B": "https://b.example"},
        live=True, max_conversations=2, max_model_calls=8,
        session_factory=lambda url: MissingSession(),
    )
    try:
        runner._validate_arm_contracts()
    except TrajectoryError as exc:
        assert "session" in str(exc).lower()
    else:
        raise AssertionError("401 session initialization must fail closed")


def test_budget_guard_fails_closed_when_server_counts_are_unavailable():
    class MissingCounters(ReplayApiSession):
        def request(self, method, path, body=None):
            if path == "/api/session":
                return ApiResult(200, {"ai_calls": 0})
            if path == "/api/ai/status":
                return ApiResult(200, {"pipeline": "adaptive_fast", "available": True})
            return super().request(method, path, body)

    runner = TrajectoryRunner(load_trajectory_set(), live=False, max_model_calls=4)
    row = {"metadata": {}}
    observed, error = runner._budget_guard(
        MissingCounters(), "A", 0, 0, row,
    )
    assert observed == 0
    assert error["type"] == "invalid_or_unavailable_ledger_counter"


def test_counter_overshoot_is_retained_and_stops_followup_requests():
    class OvershootSession(ReplayApiSession):
        def request(self, method, path, body=None):
            if path == "/api/session":
                return ApiResult(200, {"ai_calls": 3})
            if path == "/api/ai/status":
                return ApiResult(200, {"remaining_calls": 20, "session_remaining_calls": 20})
            return super().request(method, path, body)

    runner = TrajectoryRunner(load_trajectory_set(), live=False, max_model_calls=8)
    row = {"metadata": {"interpretation_calls_max": 2},
           "counter_state": {"ai_calls": 0, "remaining_calls": 23}}
    error = runner._observe_server_counters(OvershootSession(), row)
    assert error["type"] == "server_counter_overshoot"


def _successful_row(family):
    turns = [{
        "field_checks": {"passed": True},
        "question_checks": {"forbidden_target_pass": True, "forbidden_term_pass": True},
        "provenance_checks": {"passed": True},
        "ledger_checks": {"passed": True},
    } for _ in family["turns"]]
    return {
        "turns": turns,
        "review": {"manual_rescue": False, "response": {"status": 200}},
        "review_revision_binding_verified": True,
        "approval_binding_verified": True,
        "approval": {"response": {"status": 200, "payload": {"offers": [{"id": "match"}, {"id": "mismatch"}]}}},
        "offer_paths": [
            {"name": "positive", "check_status_match": True,
             "check": {"payload": {"status": "PASS"}}, "purchase_status_match": True,
             "purchase": {"status": 200}, "evidence_status_match": True,
             "verified_path": True},
            {"name": "conflicting", "check_status_match": True,
             "check": {"payload": {"status": "HOLD"}}, "purchase_status_match": True,
             "purchase": {"status": 409}, "verified_path": True},
        ],
        "raw_proposals": [{"operations": []}],
        "compiled_states": [{"fields": {}}],
    }


def test_live_scorer_counts_positive_path_and_keeps_raw_compiled_artifacts():
    family = next(item for item in load_trajectory_set()["families"] if item["id"] == "flight_direct_retention")
    row = score_live_row(_successful_row(family), family)
    assert row["primary_complete"] is True
    assert row["false_hold"] is False
    assert row["raw_proposal_vs_compiled_state"]["raw_proposals"]
    assert row["semantic_adjudication"] if "semantic_adjudication" in row else True


def test_repeated_known_question_fails_primary_even_when_field_proxy_matches():
    family = next(item for item in load_trajectory_set()["families"] if item["id"] == "flight_direct_retention")
    row = _successful_row(family)
    row["turns"][1]["question_checks"]["repeated_target_observed"] = True
    scored = score_live_row(row, family)
    assert scored["known_question_checks_pass"] is False
    assert scored["primary_complete"] is False


def test_positive_http_shape_without_verified_offer_binding_cannot_pass():
    family = next(item for item in load_trajectory_set()["families"] if item["id"] == "flight_direct_retention")
    row = _successful_row(family)
    row["offer_paths"][0]["verified_path"] = False
    scored = score_live_row(row, family)
    assert scored["positive_completion"] is False
    assert scored["primary_complete"] is False


def test_evidence_digest_binding_excludes_appended_signature_token():
    receipt = {"id": "receipt-1", "decision_id": "decision-1"}
    approved = {"id": "intent-1", "domain": "general", "fields": {"max_total_cents": 30000}}
    evidence = {
        "schema": "intent-judge.evidence.v1",
        "purchase": receipt,
        "approved_requirements": approved,
        "signed_evidence": "synthetic-signature",
    }
    evidence["digest"] = _digest({key: value for key, value in evidence.items()
                                  if key not in {"digest", "signed_evidence"}})
    assert _validate_evidence(evidence, receipt, approved) == (True, None)
    evidence["purchase"] = {**receipt, "offer_hash": "changed"}
    assert _validate_evidence(evidence, receipt, approved)[0] is False


def test_hold_oracle_is_a_correct_refusal_and_never_a_false_positive():
    family = next(item for item in load_trajectory_set()["families"] if item["id"] == "general_generic_quiet_hold")
    row = _successful_row(family)
    row["offer_paths"][0]["check"]["payload"]["status"] = "HOLD"
    row["offer_paths"][0]["purchase"] = {"status": 409}
    row["offer_paths"][0]["purchase_status_match"] = True
    row["offer_paths"][0].pop("evidence_status_match", None)
    row["offer_paths"][1]["check"]["payload"]["status"] = "HOLD"
    row["offer_paths"][1]["purchase"] = {"status": 409}
    row["offer_paths"][1]["purchase_status_match"] = True
    row["turns"] = [{
        "field_checks": {"passed": True},
        "question_checks": {"forbidden_target_pass": True, "forbidden_term_pass": True},
        "provenance_checks": {"passed": True},
        "ledger_checks": {"passed": True},
    } for _ in family["turns"]]
    scored = score_live_row(row, family)
    assert scored["primary_complete"] is True
    assert scored["correct_refusal"] is True
    assert scored["false_hold"] is False


def test_ledger_oracle_grades_revision_retraction_no_preference_and_preservation():
    previous = {
        "revision": 1,
        "records": [
            {"id": "r1", "key": "max_total_cents", "field": "max_total_cents", "value": 30000, "status": "active"},
            {"id": "r2", "key": "breakfast", "field": "breakfast", "value": True, "status": "active"},
        ],
        "history": [{"revision": 1}],
    }
    current = {
        "intent_ledger": {
            "revision": 2,
            "records": [
                {"id": "r1", "key": "max_total_cents", "field": "max_total_cents", "value": 30000, "status": "active"},
                {"id": "r2", "key": "breakfast", "field": "breakfast", "value": True, "status": "superseded"},
                {"id": "r3", "key": "breakfast", "field": "breakfast", "value": None, "status": "no_preference"},
            ],
            "history": [{"revision": 1}, {"revision": 2}],
        }
    }
    oracle = {"revision_delta": 1, "expected_record_fields": ["max_total_cents"],
              "retracted_fields": [], "no_preference_fields": ["breakfast"],
              "preserve_unrelated_active_records": True}
    checked = _ledger_state_check(current, "B", family_id="hotel_city_correction",
                                  turn_index=2, previous_ledger=previous, expected=oracle)
    assert checked["passed"] is True
    current["intent_ledger"]["records"][0]["value"] = 25000
    assert _ledger_state_check(current, "B", previous_ledger=previous, expected=oracle)["passed"] is False


def test_declared_check_status_is_part_of_verified_path_and_primary_score():
    family = next(item for item in load_trajectory_set()["families"] if item["id"] == "flight_direct_retention")
    row = _successful_row(family)
    row["offer_paths"][0]["check_status_match"] = False
    scored = score_live_row(row, family)
    assert scored["positive_completion"] is False
    assert scored["primary_complete"] is False


def test_false_hold_denominator_keeps_provider_failure_out_of_policy_false_hold():
    family = next(item for item in load_trajectory_set()["families"] if item["id"] == "flight_direct_retention")
    row = _successful_row(family)
    row["turns"][0]["field_checks"]["passed"] = False
    row["offer_paths"][0]["local_evaluation"] = {"status": "HOLD"}
    row["errors"] = [{"type": "api_error", "status": 503}]
    scored = score_live_row(row, family)
    assert scored["false_hold_eligible"] is True
    assert "trusted_positive_facts" in scored["false_hold_eligibility_reasons"]
    assert scored["provider_failure"] is True
    assert scored["false_hold"] is False


def test_false_hold_requires_actual_api_hold_and_conflicting_purchase_with_local_pass():
    family = next(item for item in load_trajectory_set()["families"] if item["id"] == "flight_direct_retention")
    row = _successful_row(family)
    row["turns"][0]["field_checks"]["passed"] = False
    row["offer_paths"][0]["local_evaluation"] = {"status": "PASS"}
    row["offer_paths"][0]["check"]["payload"]["status"] = "HOLD"
    row["offer_paths"][0]["purchase"] = {"status": 409}
    row["offer_paths"][0]["purchase_status_match"] = False
    scored = score_live_row(row, family)
    assert scored["false_hold"] is True


def test_local_hold_with_api_pass_is_not_a_false_hold():
    family = next(item for item in load_trajectory_set()["families"] if item["id"] == "flight_direct_retention")
    row = _successful_row(family)
    row["turns"][0]["field_checks"]["passed"] = False
    row["offer_paths"][0]["local_evaluation"] = {"status": "HOLD"}
    scored = score_live_row(row, family)
    assert scored["false_hold"] is False


def test_ai_interpretation_502_is_model_failure_not_provider_outage():
    family = next(item for item in load_trajectory_set()["families"] if item["id"] == "flight_direct_retention")
    row = _successful_row(family)
    row["errors"] = [{"type": "api_error", "status": 502,
                      "error": {"code": "ai_interpretation"}}]
    scored = score_live_row(row, family)
    assert scored["model_failure"] is True
    assert scored["provider_failure"] is False


def test_primary_requires_review_revision_binding_and_b_ledger_approval_binding():
    family = next(item for item in load_trajectory_set()["families"] if item["id"] == "flight_direct_retention")
    row = _successful_row(family)
    row["review_revision_binding_verified"] = False
    assert score_live_row(row, family)["primary_complete"] is False
    runner = TrajectoryRunner(load_trajectory_set(), live=False)
    draft = {"id": "intent-1", "revision": 1, "digest": "draft", "fields": {},
             "unsupported": [], "intent_ledger": {"revision": 1, "records": [], "history": []}}
    approved = {"id": "intent-1", "revision": 1, "domain": "general",
                "profile_digest": _profile_digest("general"), "fields": {},
                "unsupported": [], "draft_digest": "draft"}
    row = {"errors": [], "metadata": {"request_count": 0, "latency_ms": 0}}
    paths = runner._offers(ReplayApiSession(), family, draft, approved, [], row, arm="B", budget_start=None)
    assert paths and row["approval_binding_verified"] is False


def test_provenance_requires_nonempty_trace_model_stage_and_source_coverage():
    base = {
        "mode": "live", "pipeline": "adaptive_fast",
        "fields": {"max_total_cents": 30000},
        "sources": {"max_total_cents": "under $300"},
        "ai_runs": [{"mode": "live", "pipeline": "adaptive_fast", "model": "model-x",
                      "trace": [{"stage": "adaptive_fast", "model": "model-x"}]}],
    }
    assert _validate_live_provenance(base, "A", ["under $300"]) is None
    empty = {**base, "ai_runs": [{**base["ai_runs"][0], "trace": []}]}
    assert _validate_live_provenance(empty, "A", ["under $300"])["type"] == "empty_ai_trace"
    missing_source = {**base, "sources": {}}
    assert _validate_live_provenance(missing_source, "A", ["under $300"])["type"] == "missing_source_quote"
    missing_stage = {**base, "ai_runs": [{"mode": "live", "pipeline": "adaptive_fast", "model": "model-x",
                                             "trace": [{"model": "model-x"}]}]}
    assert _validate_live_provenance(missing_stage, "A", ["under $300"])["type"] == "missing_model_stage_metadata"


def test_pipeline_metadata_uses_latest_persisted_run_once_for_metrics():
    payload = {"ai_runs": [
        {"model": "model-x", "pipeline": "adaptive_fast", "trace": [{"stage": "first", "tokens": {"total_tokens": 3}}]},
        {"model": "model-x", "pipeline": "adaptive_fast", "trace": [{"stage": "second", "tokens": {"total_tokens": 5}}]},
    ]}
    metadata = _pipeline_metadata(payload)
    assert metadata["stage_counts"] == {"second": 1}
    assert metadata["tokens"] == {"total_tokens": 5}


def test_generic_meaning_presence_remains_pending_and_does_not_gate_quality_claim():
    family = next(item for item in load_trajectory_set()["families"] if item["id"] == "flight_direct_retention")
    row = _successful_row(family)
    row["turns"][0]["question_checks"] = {
        "forbidden_target_pass": True, "forbidden_term_pass": True,
        "required_generic_meaning": "meaning needs a validator",
        "generic_meaning_question_present": True,
    }
    scored = score_live_row(row, family)
    assert scored["generic_meaning_checks_pending"] is True
    assert scored["primary_complete"] is True


def test_fixture_labels_and_subset_validation_are_explicit():
    payload = load_trajectory_set()
    assert payload["label_audit"]["classification"] == "fixture_label_audit"
    retraction = next(item for item in payload["families"] if item["id"] == "flight_retract_connection_limit")
    assert "nonstop" not in retraction["turns"][1]["expected_fields"]
    for family in payload["families"]:
        for path in family["offer_paths"]:
            if family["domain"] == "general" and path["name"] == "alternative":
                assert path["role"] == "synthetic_alternative"
                assert "not a negative case" in path["note"]
    subset = {**payload, "families": [payload["families"][0]], "selection": "subset"}
    report = TrajectoryRunner(subset, live=False).run()
    assert report["fixture_rows"] == 1


def test_arm_contracts_keep_decoded_status_with_the_correct_arm_and_timestamp():
    class ContractSession(ReplayApiSession):
        def __init__(self, pipeline):
            super().__init__()
            self.pipeline = pipeline

        def request(self, method, path, body=None):
            if path == "/api/health":
                return ApiResult(200, {"status": "ok", "environment": "development"})
            if path == "/api/session":
                return ApiResult(200, {"environment": "development", "ai_calls": 0})
            if path == "/api/ai/status":
                return ApiResult(200, {"pipeline": self.pipeline, "available": True})
            return super().request(method, path, body)

    runner = TrajectoryRunner(load_trajectory_set(), {"A": "https://a.example", "B": "https://b.example"},
                              live=True, max_conversations=2, max_model_calls=8,
                              session_factory=lambda url: ContractSession("adaptive_fast" if "a.example" in url else "ledger"))
    runner._validate_arm_contracts()
    assert runner._arm_contracts["A"]["first_status"]["payload"]["pipeline"] == "adaptive_fast"
    assert runner._arm_contracts["B"]["first_status"]["payload"]["pipeline"] == "ledger"
    assert runner._arm_contracts["A"]["checked_at"]


def test_explanation_non_2xx_is_retained_and_post_counters_are_observed():
    class ExplanationSession(ReplayApiSession):
        def __init__(self, check_payload, evidence_payload):
            super().__init__()
            self.check_payload = check_payload
            self.evidence_payload = evidence_payload
            self.calls = 0

        def request(self, method, path, body=None):
            self.requests.append({"method": method, "path": path, "body": body})
            if path == "/api/session":
                self.calls += 1
                return ApiResult(200, {"ai_calls": 0 if self.calls == 1 else 1})
            if path == "/api/ai/status":
                return ApiResult(200, {"available": True, "interpretation_calls_max": 1,
                                       "remaining_calls": 10 if self.calls < 2 else 9,
                                       "session_remaining_calls": 10 if self.calls < 2 else 9})
            if path == "/api/decisions/decision-1/explain":
                return ApiResult(500, {"detail": "explanation unavailable"})
            if path == "/api/check":
                return ApiResult(200, self.check_payload)
            if path == "/api/purchase":
                return ApiResult(200, {"id": "receipt-1", "decision_id": "decision-1",
                                       "offer_id": "offer-1", "offer_hash": "offer-hash",
                                       "approved_digest": self.check_payload["approved_digest"],
                                       "mode": "simulated", "outcome": "confirmed"})
            if path == "/api/purchases/receipt-1/evidence":
                return ApiResult(200, self.evidence_payload)
            return super().request(method, path, body)

    family = next(item for item in load_trajectory_set()["families"] if item["id"] == "general_budget_correction")
    draft = {"id": "intent-1", "revision": 1, "digest": "draft-digest",
             "fields": {"max_total_cents": 30000}, "unsupported": []}
    approved = {"id": "intent-1", "revision": 1, "domain": "general",
                "profile_digest": _profile_digest("general"), "fields": draft["fields"],
                "unsupported": [], "draft_digest": draft["digest"]}
    approved_digest = _digest(approved)
    facts = {"currency": "USD", "total_cents": 30000}
    check_payload = {"id": "decision-1", "status": "PASS", "facts": facts,
                     "offer_hash": "offer-hash", "approved_digest": approved_digest}
    receipt = {"id": "receipt-1", "decision_id": "decision-1", "offer_id": "offer-1",
               "offer_hash": "offer-hash", "approved_digest": approved_digest,
               "mode": "simulated", "outcome": "confirmed"}
    evidence = {"schema": "intent-judge.evidence.v1", "purchase": receipt,
                "approved_requirements": approved, "signed_evidence": "sig"}
    evidence["digest"] = _digest({k: v for k, v in evidence.items() if k not in {"digest", "signed_evidence"}})
    session = ExplanationSession(check_payload, evidence)
    row = {"run_id": "offline-explain", "errors": [], "metadata": {"request_count": 0, "latency_ms": 0,
            "explanation_attempted": False, "explanation_exercised": False}, "counter_state": {}}
    runner = TrajectoryRunner(load_trajectory_set(), live=False, max_model_calls=8, include_explanation=True)
    paths = runner._offers(session, family, draft, approved, [
        {"id": "offer-1", "signed": True, "offer_hash": "offer-hash", "facts": facts}
    ], row, arm="A", budget_start=0)
    assert row["metadata"]["explanation_attempted"] is True
    assert row["metadata"]["explanation_exercised"] is False
    assert any(error.get("status") == 500 for error in row["errors"])
    explain_index = next(i for i, req in enumerate(session.requests) if req["path"].endswith("/explain"))
    assert any(req["path"] == "/api/session" for req in session.requests[explain_index + 1:])
