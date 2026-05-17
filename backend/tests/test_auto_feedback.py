def _create_completed_task(client) -> str:
    resp = client.post(
        "/tasks",
        json={
            "spec": {
                "goal": "Optimize feedback-driven execution loop",
                "constraints": {"output": "checklist"},
                "contextRefs": ["doc://brief"],
                "qualityTarget": 0.9,
                "priority": 2,
            },
            "runAsync": False,
        },
    )
    assert resp.status_code == 200
    return resp.json()["id"]


def test_auto_feedback_submits_candidate(client):
    task_id = _create_completed_task(client)
    payload = {
        "turns": [
            {"role": "user", "content": "这个方案可用，但请改成聊天气泡时间线，并突出交付产物。"},
            {"role": "assistant", "content": "收到，我会重构界面并强化结果展示。"},
            {"role": "user", "content": "如果我忘记反馈，也要自动感知并进化。"},
        ],
        "onlyIfMissing": True,
        "source": "test-auto",
    }
    resp = client.post(f"/tasks/{task_id}/auto-feedback", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "submitted"
    assert body["candidateId"]
    assert body["skillId"]
    assert body["candidateStatus"] == "proposed"
    assert body["inferredFeedback"]["implicitSignals"]["retryCount"] >= 0


def test_auto_feedback_skips_if_feedback_exists(client):
    task_id = _create_completed_task(client)
    manual_feedback = {
        "feedback": {
            "explicitScore": 0.9,
            "corrections": "Please improve risk ordering",
            "implicitSignals": {
                "retryCount": 0,
                "editDistance": 0.08,
                "adoptionRate": 0.9,
                "errorRateRise": 0.0,
            },
        }
    }
    feedback_resp = client.post(f"/tasks/{task_id}/feedback", json=manual_feedback)
    assert feedback_resp.status_code == 200

    auto_resp = client.post(
        f"/tasks/{task_id}/auto-feedback",
        json={
            "turns": [{"role": "user", "content": "Looks good"}],
            "onlyIfMissing": True,
            "source": "test-skip",
        },
    )
    assert auto_resp.status_code == 200
    body = auto_resp.json()
    assert body["status"] == "skipped"
    assert body["candidateId"] is None
