def test_llm_config_get_and_update(client):
    get_resp = client.get("/llm/config")
    assert get_resp.status_code == 200
    original = get_resp.json()
    assert "llmMode" in original

    update_resp = client.put(
        "/llm/config",
        json={
            "llmMode": "mock",
            "llmModelName": "qwen2.5:7b",
            "llmTimeoutSeconds": 25,
        },
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["llmMode"] == "mock"
    assert updated["llmModelName"] == "qwen2.5:7b"
    assert updated["llmTimeoutSeconds"] == 25


def test_llm_token_stats(client):
    create_resp = client.post(
        "/tasks",
        json={
            "spec": {
                "goal": "Generate token usage example",
                "constraints": {"style": "clear"},
                "contextRefs": ["doc://seed"],
                "qualityTarget": 0.9,
                "priority": 2,
            },
            "runAsync": False,
        },
    )
    assert create_resp.status_code == 200

    stats_resp = client.get("/llm/token-stats?limit=30")
    assert stats_resp.status_code == 200
    body = stats_resp.json()
    assert body["totalTasks"] >= 1
    assert body["totalTokens"] > 0
    assert isinstance(body["byModel"], list)
    assert isinstance(body["recentTasks"], list)
