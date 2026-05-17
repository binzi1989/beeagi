from app.db.session import SessionLocal
from app.models.skill import CandidateStatus, SkillCandidate
from app.api import security


def test_candidate_create_ignores_client_scores(client):
    skill_id = client.get("/skills").json()[0]["id"]
    resp = client.post(
        f"/skills/{skill_id}/candidate",
        json={
            "delta": {
                "targetSkill": skill_id,
                "changeType": "score_injection_attempt",
                "patch": {"promptTweaks": {"style": "tight"}},
                "evidence": {"source": "test"},
            },
            "shadowScore": 9.99,
            "canaryScore": 0.01,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["shadowScore"] <= 1.2
    assert body["shadowScore"] != 9.99
    assert body["canaryScore"] is None


def test_rollback_restores_previous_snapshot(client):
    skill = client.get("/skills").json()[0]
    skill_id = skill["id"]
    baseline_version = skill["version"]
    baseline_strategy = skill["config"].get("strategy")
    baseline_prompt_style = (skill["config"].get("promptTweaks") or {}).get("style")

    candidate_resp = client.post(
        f"/skills/{skill_id}/candidate",
        json={
            "delta": {
                "targetSkill": skill_id,
                "changeType": "rollback_snapshot_test",
                "patch": {"promptTweaks": {"style": "tight"}},
                "evidence": {"source": "rollback-test"},
            }
        },
    )
    assert candidate_resp.status_code == 200
    candidate_id = candidate_resp.json()["id"]

    with SessionLocal() as db:
        candidate = db.get(SkillCandidate, candidate_id)
        assert candidate is not None
        candidate.status = CandidateStatus.validated.value
        candidate.canary_score = 0.99
        candidate.evidence = {
            **dict(candidate.evidence or {}),
            "canaryStats": {"feedbackCount": 3},
        }
        db.commit()

    promote_resp = client.post(
        f"/skills/{skill_id}/promote",
        json={"candidateId": candidate_id, "approvedBy": "queen-test"},
    )
    assert promote_resp.status_code == 200
    assert promote_resp.json()["status"] == "promoted"

    promoted_skill = next(item for item in client.get("/skills").json() if item["id"] == skill_id)
    assert promoted_skill["version"] == baseline_version + 1
    assert promoted_skill["config"].get("promptTweaks", {}).get("style") == "tight"

    rollback_resp = client.post(
        f"/skills/{skill_id}/rollback",
        json={"reason": "test rollback", "requestedBy": "queen-test"},
    )
    assert rollback_resp.status_code == 200
    rolled_back_skill = rollback_resp.json()
    assert rolled_back_skill["version"] == baseline_version
    assert rolled_back_skill["config"].get("strategy") == baseline_strategy
    assert (rolled_back_skill["config"].get("promptTweaks") or {}).get("style") == baseline_prompt_style


def test_write_endpoint_requires_api_key_when_enabled(client):
    original_key = security.settings.control_plane_api_key
    security.settings.control_plane_api_key = "p0-secret"
    try:
        payload = {
            "spec": {
                "goal": "auth guard task",
                "constraints": {},
                "contextRefs": [],
                "qualityTarget": 0.9,
                "priority": 2,
            },
            "runAsync": False,
        }
        missing_key_resp = client.post("/tasks", json=payload)
        assert missing_key_resp.status_code == 401
        audit_missing_key = client.get("/evolution/candidate-audits")
        assert audit_missing_key.status_code == 401
        report_missing_key = client.get("/evolution/hardening-report")
        assert report_missing_key.status_code == 401

        ok_resp = client.post("/tasks", json=payload, headers={"X-API-Key": "p0-secret"})
        assert ok_resp.status_code == 200
        audit_ok = client.get("/evolution/candidate-audits", headers={"X-API-Key": "p0-secret"})
        assert audit_ok.status_code == 200
        report_ok = client.get("/evolution/hardening-report", headers={"X-API-Key": "p0-secret"})
        assert report_ok.status_code == 200
    finally:
        security.settings.control_plane_api_key = original_key
