import uuid


def test_create_skill_from_factory(client):
    skill_id = f"skill_test_factory_{uuid.uuid4().hex[:8]}"
    resp = client.post(
        "/skills/factory",
        json={
            "skillId": skill_id,
            "name": "Skill Test Factory",
            "description": "Factory-generated skill for regression test.",
            "baseStrategy": "tool_first",
            "mcpConnectors": ["github", "filesystem"],
            "ioSchema": {"input": ["goal"], "output": ["result"]},
            "permissions": {"network": True, "filesystem": "read_write"},
            "costBudget": {"maxTokens": 9000},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == skill_id
    assert body["config"]["factory"]["mcpConnectors"] == ["github", "filesystem"]


def test_swarm_and_mcp_constraints_take_effect(client):
    resp = client.post(
        "/tasks",
        json={
            "spec": {
                "goal": "create integration plan with multi-worker ensemble",
                "constraints": {
                    "swarmConfig": {"workerCount": 5, "scoutCount": 4},
                    "mcpConnectors": ["github", "filesystem", "notion"],
                },
                "contextRefs": ["repo://backend/app", "doc://architecture-notes"],
                "qualityTarget": 0.9,
                "priority": 2,
            },
            "runAsync": False,
        },
    )
    assert resp.status_code == 200
    task = resp.json()

    assert task["planGraph"]["swarmConfig"]["workerCount"] == 5
    assert task["planGraph"]["swarmConfig"]["scoutCount"] == 4
    assert task["resultPayload"]["swarmTelemetry"]["workerCount"] == 5
    assert task["resultPayload"]["swarmTelemetry"]["scoutCount"] == 4
    assert task["scoutReport"]["swarmConfig"]["mcpConnectors"] == ["github", "filesystem", "notion"]
