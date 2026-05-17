from pathlib import Path
import shutil
import uuid


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
    deliverables = body["resultPayload"]["deliverables"]
    assert deliverables["status"] == "written"
    assert deliverables["fileCount"] >= 1
    assert Path(deliverables["primaryArtifact"]).exists()

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


def _fresh_target_dir(prefix: str) -> Path:
    target_dir = Path("artifacts") / "test_output" / f"{prefix}_{uuid.uuid4().hex[:8]}"
    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir.resolve()


def test_coding_scene_writes_project_files_into_bound_workspace(client):
    target_dir = _fresh_target_dir("coding_out")
    payload = {
        "spec": {
            "goal": "Build a runnable coding deliverable with tests",
            "constraints": {
                "scenarioId": "coding",
                "workspaceBinding": {
                    "targetDir": str(target_dir),
                    "allowWrite": True,
                    "allowExecute": False,
                },
            },
            "contextRefs": ["repo://backend/app/services", "doc://acceptance"],
            "qualityTarget": 0.91,
            "priority": 1,
        },
        "runAsync": False,
    }
    resp = client.post("/tasks", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    deliverables = body["resultPayload"]["deliverables"]
    assert deliverables["scene"] == "coding"
    assert deliverables["status"] == "written"
    assert deliverables["workspacePath"] == str(target_dir.resolve())
    assert deliverables["fileCount"] >= 5
    assert any(item["path"].endswith("README.md") for item in deliverables["files"])
    assert any(item["path"].endswith("test_planner.py") for item in deliverables["files"])

    for item in deliverables["files"]:
        assert Path(item["absolutePath"]).exists()


def test_skills_scene_writes_skill_markdown(client):
    target_dir = _fresh_target_dir("skills_out")
    payload = {
        "spec": {
            "goal": "Create a reusable skills markdown package",
            "constraints": {
                "scenarioId": "skills_factory",
                "workspaceBinding": {
                    "targetDir": str(target_dir),
                    "allowWrite": True,
                    "allowExecute": False,
                },
                "skillFactoryHints": {"targetSkillId": "skill_delivery_md"},
            },
            "contextRefs": ["repo://skills", "doc://skill-rules"],
            "qualityTarget": 0.9,
            "priority": 2,
        },
        "runAsync": False,
    }
    resp = client.post("/tasks", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    deliverables = body["resultPayload"]["deliverables"]
    assert deliverables["scene"] == "skills_factory"
    assert deliverables["status"] == "written"
    assert any(item["path"].endswith("SKILL.md") for item in deliverables["files"])
    skill_file = next(item for item in deliverables["files"] if item["path"].endswith("SKILL.md"))
    assert Path(skill_file["absolutePath"]).read_text(encoding="utf-8").startswith("# Skill:")


def test_workspace_write_disabled_keeps_planned_files_only(client):
    target_dir = _fresh_target_dir("readonly_out")
    payload = {
        "spec": {
            "goal": "Generate office brief without writing files",
            "constraints": {
                "scenarioId": "office",
                "workspaceBinding": {
                    "targetDir": str(target_dir),
                    "allowWrite": False,
                    "allowExecute": False,
                },
            },
            "contextRefs": ["doc://weekly-notes"],
            "qualityTarget": 0.88,
            "priority": 3,
        },
        "runAsync": False,
    }
    resp = client.post("/tasks", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    deliverables = body["resultPayload"]["deliverables"]
    assert deliverables["status"] == "write_disabled"
    assert deliverables["files"] == []
    assert deliverables["plannedFiles"]


def test_download_single_deliverable_file(client):
    target_dir = _fresh_target_dir("download_single")
    resp = client.post(
        "/tasks",
        json={
            "spec": {
                "goal": "Build coding package for download API test",
                "constraints": {
                    "scenarioId": "coding",
                    "workspaceBinding": {
                        "targetDir": str(target_dir),
                        "allowWrite": True,
                        "allowExecute": False,
                    },
                },
                "contextRefs": ["repo://backend/app"],
                "qualityTarget": 0.9,
                "priority": 2,
            },
            "runAsync": False,
        },
    )
    assert resp.status_code == 200
    task = resp.json()
    file_path = task["resultPayload"]["deliverables"]["files"][0]["absolutePath"]

    download_resp = client.get(f"/tasks/{task['id']}/deliverables/download", params={"artifactPath": file_path})
    assert download_resp.status_code == 200
    assert len(download_resp.content) > 0


def test_download_deliverable_archive(client):
    target_dir = _fresh_target_dir("download_archive")
    resp = client.post(
        "/tasks",
        json={
            "spec": {
                "goal": "Build skills package for archive download test",
                "constraints": {
                    "scenarioId": "skills_factory",
                    "workspaceBinding": {
                        "targetDir": str(target_dir),
                        "allowWrite": True,
                        "allowExecute": False,
                    },
                },
                "contextRefs": ["repo://skills"],
                "qualityTarget": 0.9,
                "priority": 2,
            },
            "runAsync": False,
        },
    )
    assert resp.status_code == 200
    task = resp.json()

    archive_resp = client.get(f"/tasks/{task['id']}/deliverables/archive")
    assert archive_resp.status_code == 200
    assert archive_resp.content[:2] == b"PK"
