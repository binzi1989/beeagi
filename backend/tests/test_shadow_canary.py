from app.services.canary_allocator import CanaryAllocator


def _find_canary_user(skill_id: str, candidate_id: str, ratio: float = 0.05) -> str:
    allocator = CanaryAllocator(ratio)
    for i in range(20000):
        user = f"canary-user-{i}"
        selected, _ = allocator.is_selected(user_id=user, skill_id=skill_id, candidate_id=candidate_id)
        if selected:
            return user
    raise AssertionError("unable to find canary user bucket")


def test_shadow_replay_and_real_canary_allocator(client):
    # Create historical tasks for shadow replay sampling
    for i in range(6):
        create_resp = client.post(
            "/tasks",
            json={
                "spec": {
                    "goal": f"historical task {i}",
                    "constraints": {"format": "json"},
                    "contextRefs": [],
                    "qualityTarget": 0.86,
                    "priority": 3,
                },
                "runAsync": False,
            },
            headers={"X-User": f"history-{i}"},
        )
        assert create_resp.status_code == 200

    skill_id = client.get("/skills").json()[0]["id"]
    candidate_resp = client.post(
        f"/skills/{skill_id}/candidate",
        json={
            "delta": {
                "targetSkill": skill_id,
                "changeType": "shadow_canary_test",
                "patch": {
                    "promptTweaks": {"mode": "structured"},
                    "toolPolicy": {"maxRetries": 2, "preferLowRiskTools": True},
                },
                "evidence": {"source": "test"},
            },
            "shadowScore": 1.0,
            "canaryScore": None,
        },
    )
    assert candidate_resp.status_code == 200
    candidate = candidate_resp.json()

    shadow_resp = client.post(
        f"/skills/{skill_id}/candidate/{candidate['id']}/shadow-replay",
        json={"sampleSize": 6},
    )
    assert shadow_resp.status_code == 200
    shadow_data = shadow_resp.json()
    assert shadow_data["sampleSize"] == 6
    assert shadow_data["improvementRatio"] > 1.08

    # First promotion with no canary score should enter validated state.
    validate_resp = client.post(
        f"/skills/{skill_id}/promote",
        json={"candidateId": candidate["id"], "approvedBy": "queen-test"},
    )
    assert validate_resp.status_code == 200
    assert validate_resp.json()["status"] == "validated"

    canary_user = _find_canary_user(skill_id=skill_id, candidate_id=candidate["id"], ratio=0.05)
    canary_task_resp = client.post(
        "/tasks",
        json={
            "spec": {
                "goal": "task for canary assignment",
                "constraints": {"mode": "canary"},
                "contextRefs": [],
                "qualityTarget": 0.9,
                "priority": 2,
            },
            "runAsync": False,
        },
        headers={"X-User": canary_user},
    )
    assert canary_task_resp.status_code == 200
    canary_task = canary_task_resp.json()
    assignments = canary_task["resultPayload"].get("canaryAssignments", [])
    assert len(assignments) >= 1
    assert any(item["candidateId"] == candidate["id"] for item in assignments)

    feedback_payload = {
        "feedback": {
            "explicitScore": 0.95,
            "corrections": "looks good",
            "implicitSignals": {
                "retryCount": 0,
                "editDistance": 0.05,
                "adoptionRate": 0.92,
                "errorRateRise": 0.0,
            },
        }
    }
    for _ in range(3):
        feedback_resp = client.post(f"/tasks/{canary_task['id']}/feedback", json=feedback_payload)
        assert feedback_resp.status_code == 200

    canary_status_resp = client.get(f"/skills/{skill_id}/candidate/{candidate['id']}/canary-status")
    assert canary_status_resp.status_code == 200
    canary_status = canary_status_resp.json()
    assert canary_status["feedbackCount"] == 1
    assert canary_status["canaryScore"] is not None

    for i in range(2):
        extra_task_resp = client.post(
            "/tasks",
            json={
                "spec": {
                    "goal": f"extra canary task {i}",
                    "constraints": {"mode": "canary"},
                    "contextRefs": [],
                    "qualityTarget": 0.9,
                    "priority": 2,
                },
                "runAsync": False,
            },
            headers={"X-User": canary_user},
        )
        assert extra_task_resp.status_code == 200
        extra_task = extra_task_resp.json()
        extra_feedback = client.post(f"/tasks/{extra_task['id']}/feedback", json=feedback_payload)
        assert extra_feedback.status_code == 200

    canary_status_resp = client.get(f"/skills/{skill_id}/candidate/{candidate['id']}/canary-status")
    assert canary_status_resp.status_code == 200
    canary_status = canary_status_resp.json()
    assert canary_status["feedbackCount"] >= 3

    promote_resp = client.post(
        f"/skills/{skill_id}/promote",
        json={"candidateId": candidate["id"], "approvedBy": "queen-test"},
    )
    assert promote_resp.status_code == 200
    assert promote_resp.json()["status"] == "promoted"
