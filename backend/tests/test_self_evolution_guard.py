def _create_completed_task(client):
    resp = client.post(
        "/tasks",
        json={
            "spec": {
                "goal": "draft deployment checklist with risk ordering",
                "constraints": {"format": "checklist"},
                "contextRefs": ["doc://deploy-notes"],
                "qualityTarget": 0.9,
                "priority": 2,
            },
            "runAsync": False,
        },
        headers={"X-User": "evolution-guard-user"},
    )
    assert resp.status_code == 200
    return resp.json()["id"]


def test_ensure_evolution_generates_feedback_and_candidate(client):
    task_id = _create_completed_task(client)

    ensure_resp = client.post(
        f"/tasks/{task_id}/ensure-evolution",
        json={"onlyIfMissing": True, "source": "test-guard"},
        headers={"X-User": "evolution-guard-user"},
    )
    assert ensure_resp.status_code == 200
    body = ensure_resp.json()
    assert body["status"] == "submitted"
    assert body["candidateId"]
    assert body["inferredFeedback"] is not None

    ensure_again = client.post(
        f"/tasks/{task_id}/ensure-evolution",
        json={"onlyIfMissing": True, "source": "test-guard"},
        headers={"X-User": "evolution-guard-user"},
    )
    assert ensure_again.status_code == 200
    body_again = ensure_again.json()
    assert body_again["status"] == "skipped"
