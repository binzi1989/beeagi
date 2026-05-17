def test_auto_promote_runner_progresses_candidate_state(client):
    skill_id = client.get("/skills").json()[0]["id"]
    candidate_resp = client.post(
        f"/skills/{skill_id}/candidate",
        json={
            "delta": {
                "targetSkill": skill_id,
                "changeType": "auto_promote_test",
                "patch": {"promptTweaks": {"style": "tight"}},
                "evidence": {"source": "auto-promote-test"},
            },
            "shadowScore": 1.12,
            "canaryScore": None,
        },
    )
    assert candidate_resp.status_code == 200
    candidate_id = candidate_resp.json()["id"]

    first_run = client.post(
        "/evolution/auto-promote",
        json={"limit": 50, "approvedBy": "queen-auto-test"},
    )
    assert first_run.status_code == 200
    first_data = first_run.json()
    first_item = next(item for item in first_data["outcomes"] if item["candidateId"] == candidate_id)
    assert first_item["decision"] == "validated"

    second_run = client.post(
        "/evolution/auto-promote",
        json={"limit": 50, "approvedBy": "queen-auto-test"},
    )
    assert second_run.status_code == 200
    second_data = second_run.json()
    second_item = next(item for item in second_data["outcomes"] if item["candidateId"] == candidate_id)
    assert second_item["decision"] == "skipped"
    assert "waiting canary feedback" in second_item["reason"]
