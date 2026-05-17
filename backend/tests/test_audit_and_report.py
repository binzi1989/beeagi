from app.db.session import SessionLocal
from app.models.skill import SkillCandidate


def test_candidate_audits_and_hardening_report(client):
    skill_id = client.get("/skills").json()[0]["id"]
    candidate_resp = client.post(
        f"/skills/{skill_id}/candidate",
        json={
            "delta": {
                "targetSkill": skill_id,
                "changeType": "audit_flow_test",
                "patch": {"promptTweaks": {"style": "tight"}},
                "evidence": {"source": "audit-test"},
            }
        },
    )
    assert candidate_resp.status_code == 200
    candidate_id = candidate_resp.json()["id"]

    first_promote = client.post(
        f"/skills/{skill_id}/promote",
        json={"candidateId": candidate_id, "approvedBy": "queen-audit-test"},
    )
    assert first_promote.status_code == 200
    assert first_promote.json()["status"] == "validated"

    with SessionLocal() as db:
        candidate = db.get(SkillCandidate, candidate_id)
        assert candidate is not None
        candidate.canary_score = 0.99
        candidate.evidence = {
            **dict(candidate.evidence or {}),
            "canaryStats": {"feedbackCount": 3},
            "canaryErrorRise": 0.0,
        }
        db.commit()

    second_promote = client.post(
        f"/skills/{skill_id}/promote",
        json={"candidateId": candidate_id, "approvedBy": "queen-audit-test"},
    )
    assert second_promote.status_code == 200
    assert second_promote.json()["status"] == "promoted"

    rollback_resp = client.post(
        f"/skills/{skill_id}/rollback",
        json={"reason": "audit test rollback", "requestedBy": "queen-audit-test"},
    )
    assert rollback_resp.status_code == 200

    audits_resp = client.get(f"/evolution/candidate-audits?candidateId={candidate_id}&limit=20")
    assert audits_resp.status_code == 200
    audits = audits_resp.json()
    assert len(audits) >= 3
    seen_to_status = {item["toStatus"] for item in audits}
    assert "proposed" in seen_to_status
    assert "validated" in seen_to_status
    assert "promoted" in seen_to_status or "rolled_back" in seen_to_status

    report_resp = client.get("/evolution/hardening-report")
    assert report_resp.status_code == 200
    report = report_resp.json()
    assert report["overall"] in {"pass", "warn"}
    assert report["summary"]["skillCount"] >= 1
    assert report["summary"]["recentAuditCount"] >= 1
    assert isinstance(report["checks"], list)
