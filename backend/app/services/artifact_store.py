from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


class ArtifactStore:
    def __init__(self, base_dir: str) -> None:
        self.base_path = Path(base_dir)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def write_replay_bundle(self, task_id: str, candidate_id: str, payload: dict[str, Any]) -> str:
        now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        file_name = f"{task_id}_{candidate_id}_{now}.json"
        target = self.base_path / file_name
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(target.resolve())
