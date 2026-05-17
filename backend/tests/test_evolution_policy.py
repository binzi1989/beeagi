def test_candidate_promotion_and_events(client):
    skills_resp = client.get("/skills")
    assert skills_resp.status_code == 200
    skill_id = skills_resp.json()[0]["id"]

    candidate_resp = client.post(
        f"/skills/{skill_id}/candidate",
        json={
            "delta": {
                "targetSkill": skill_id,
                "changeType": "prompt_tune",
                "patch": {"promptTweaks": {"verbosity": "medium"}},
                "evidence": {"sampleSize": 50},
            },
            "shadowScore": 1.12,
            "canaryScore": 0.99,
        },
    )
    assert candidate_resp.status_code == 200
    candidate = candidate_resp.json()

    promote_resp = client.post(
        f"/skills/{skill_id}/promote",
        json={
            "candidateId": candidate["id"],
            "approvedBy": "queen-1",
        },
    )
    assert promote_resp.status_code == 200
    promote_body = promote_resp.json()
    assert promote_body["status"] in {"promoted", "validated", "rejected", "rolled_back"}

    events_resp = client.get("/evolution/events")
    assert events_resp.status_code == 200
    assert len(events_resp.json()) >= 1


def test_auto_reject_low_shadow_gain(client):
    skill_id = client.get("/skills").json()[0]["id"]
    candidate_resp = client.post(
        f"/skills/{skill_id}/candidate",
        json={
            "delta": {
                "targetSkill": skill_id,
                "changeType": "policy_patch",
                "patch": {"toolPolicy": {"maxRetries": 1}},
                "evidence": {"sampleSize": 10},
            },
            "shadowScore": 1.02,
            "canaryScore": 0.99,
        },
    )
    candidate = candidate_resp.json()
    promote_resp = client.post(
        f"/skills/{skill_id}/promote",
        json={"candidateId": candidate["id"], "approvedBy": "queen-1"},
    )
    assert promote_resp.status_code == 200
    assert promote_resp.json()["decision"] == "rejected"


def test_auto_rollback_on_error_rise(client):
    skill_id = client.get("/skills").json()[0]["id"]
    candidate_resp = client.post(
        f"/skills/{skill_id}/candidate",
        json={
            "delta": {
                "targetSkill": skill_id,
                "changeType": "policy_patch",
                "patch": {"toolPolicy": {"maxRetries": 2}},
                "evidence": {"sampleSize": 24, "canaryErrorRise": 0.03},
            },
            "shadowScore": 1.15,
            "canaryScore": 0.99,
        },
    )
    candidate = candidate_resp.json()
    promote_resp = client.post(
        f"/skills/{skill_id}/promote",
        json={"candidateId": candidate["id"], "approvedBy": "queen-1"},
    )
    assert promote_resp.status_code == 200
    assert promote_resp.json()["decision"] == "rolled_back"


def test_permission_escalation_blocked(client):
    skills = client.get("/skills").json()
    skill_id = next(skill["id"] for skill in skills if skill["id"] == "plan_graph_builder")
    blocked_resp = client.post(
        f"/skills/{skill_id}/candidate",
        json={
            "delta": {
                "targetSkill": skill_id,
                "changeType": "permission_patch",
                "patch": {"permissions": {"network": True}},
                "evidence": {"source": "attack-sim"},
            },
            "shadowScore": 1.2,
            "canaryScore": 0.99,
        },
    )
    assert blocked_resp.status_code == 400
    assert "permission escalation blocked" in blocked_resp.text
