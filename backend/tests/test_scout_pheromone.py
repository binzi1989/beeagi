def test_scout_pheromone_closed_loop(client):
    create_resp = client.post(
        "/tasks",
        json={
            "spec": {
                "goal": "Build API checklist for payment retry",
                "constraints": {"format": "checklist"},
                "contextRefs": ["repo://backend/payment", "doc://runbook/retry"],
                "qualityTarget": 0.9,
                "priority": 2,
            },
            "runAsync": False,
        },
        headers={"X-User": "pheromone-user-1"},
    )
    assert create_resp.status_code == 200
    task = create_resp.json()
    assert task["status"] == "completed"

    report = task.get("scoutReport", {})
    assert report.get("pheromoneCount", 0) >= 1

    pheromone_resp = client.get("/evolution/pheromones?limit=20")
    assert pheromone_resp.status_code == 200
    pheromones = pheromone_resp.json()
    assert len(pheromones) >= 1

    initial = {item["id"]: item for item in pheromones}
    feedback_resp = client.post(
        f"/tasks/{task['id']}/feedback",
        json={
            "feedback": {
                "explicitScore": 0.95,
                "corrections": "looks good",
                "implicitSignals": {
                    "retryCount": 0,
                    "editDistance": 0.05,
                    "adoptionRate": 0.94,
                    "errorRateRise": 0.0,
                },
            }
        },
        headers={"X-User": "pheromone-user-1"},
    )
    assert feedback_resp.status_code == 200

    after_resp = client.get("/evolution/pheromones?limit=20")
    assert after_resp.status_code == 200
    updated = after_resp.json()
    assert len(updated) >= 1

    rewarded_rows = 0
    for row in updated:
        previous = initial.get(row["id"])
        if not previous:
            continue
        if row["reward"] > previous["reward"] or row["successCount"] > previous["successCount"]:
            rewarded_rows += 1
    assert rewarded_rows >= 1


def test_scout_patrol_endpoint(client):
    for idx in range(3):
        create_resp = client.post(
            "/tasks",
            json={
                "spec": {
                    "goal": f"research fallback path {idx}",
                    "constraints": {"style": "concise"},
                    "contextRefs": [f"doc://note/{idx}", f"db://metrics/{idx}"],
                    "qualityTarget": 0.88,
                    "priority": 3,
                },
                "runAsync": False,
            },
            headers={"X-User": f"patrol-user-{idx}"},
        )
        assert create_resp.status_code == 200

    patrol_resp = client.post("/evolution/scout-patrol", json={"sampleSize": 20})
    assert patrol_resp.status_code == 200
    body = patrol_resp.json()
    assert body["sampleSize"] == 20
    assert body["sampledTasks"] >= 1
    assert body["deposited"] >= 1

    events_resp = client.get("/evolution/events?limit=50")
    assert events_resp.status_code == 200
    topics = [item["topic"] for item in events_resp.json()]
    assert "scout.patrolled" in topics
