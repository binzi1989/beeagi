def test_task_create_and_get(client):
    payload = {
        "spec": {
            "goal": "Create a launch brief for product X",
            "constraints": {"tone": "executive"},
            "contextRefs": ["doc://brief", "db://pricing"],
            "qualityTarget": 0.9,
            "priority": 2,
        },
        "runAsync": False,
    }
    resp = client.post("/tasks", json=payload, headers={"X-User": "alice"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["planGraph"]["nodes"]

    task_id = body["id"]
    get_resp = client.get(f"/tasks/{task_id}")
    assert get_resp.status_code == 200
    detail = get_resp.json()
    assert detail["resultPayload"]["summary"]


def test_feedback_creates_candidate(client):
    create_resp = client.post(
        "/tasks",
        json={
            "spec": {
                "goal": "Generate API integration draft",
                "constraints": {},
                "contextRefs": [],
                "qualityTarget": 0.88,
                "priority": 3,
            },
            "runAsync": False,
        },
    )
    task_id = create_resp.json()["id"]
    feedback_payload = {
        "feedback": {
            "explicitScore": 0.92,
            "corrections": "Need better security rationale",
            "implicitSignals": {
                "retryCount": 0,
                "editDistance": 0.08,
                "adoptionRate": 0.91,
            },
        }
    }
    resp = client.post(f"/tasks/{task_id}/feedback", json=feedback_payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["candidateId"]
    assert body["status"] == "proposed"


def test_run_async_falls_back_when_celery_disabled(client):
    payload = {
        "spec": {
            "goal": "Write a migration checklist",
            "constraints": {},
            "contextRefs": [],
            "qualityTarget": 0.86,
            "priority": 3,
        },
        "runAsync": True,
    }
    resp = client.post("/tasks", json=payload, headers={"X-User": "bob"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
