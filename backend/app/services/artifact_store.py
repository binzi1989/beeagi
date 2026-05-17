from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile


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

    def resolve_workspace_binding(self, task_id: str, constraints: dict[str, Any] | None = None) -> dict[str, Any]:
        config = constraints or {}
        binding = config.get("workspaceBinding") if isinstance(config, dict) else {}
        if not isinstance(binding, dict):
            binding = {}

        requested_path = str(binding.get("targetDir", "") or "").strip()
        allow_write = bool(binding.get("allowWrite", True))
        allow_execute = bool(binding.get("allowExecute", False))

        if requested_path:
            path_obj = Path(requested_path).expanduser()
            if not path_obj.is_absolute():
                path_obj = (Path.cwd() / path_obj).resolve()
            source = "bound"
        else:
            path_obj = (self.base_path / "deliverables" / task_id).resolve()
            source = "default"

        if allow_write:
            path_obj.mkdir(parents=True, exist_ok=True)

        return {
            "path": str(path_obj),
            "allowWrite": allow_write,
            "allowExecute": allow_execute,
            "source": source,
        }

    def _safe_relative_path(self, relative_path: str) -> Path:
        candidate = str(relative_path or "").replace("\\", "/").strip().lstrip("/")
        if not candidate:
            return Path("output.txt")
        parts = [part for part in candidate.split("/") if part not in {"", ".", ".."}]
        if not parts:
            return Path("output.txt")
        return Path(*parts)

    def write_deliverable_files(
        self,
        *,
        workspace_path: str,
        files: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        root = Path(workspace_path).resolve()
        root.mkdir(parents=True, exist_ok=True)
        written: list[dict[str, Any]] = []
        for item in files:
            rel = self._safe_relative_path(str(item.get("path", "")))
            content = str(item.get("content", ""))
            target = (root / rel).resolve()

            try:
                target.relative_to(root)
            except ValueError as exc:
                raise ValueError(f"unsafe output path rejected: {rel}") from exc

            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            written.append(
                {
                    "path": str(rel).replace("\\", "/"),
                    "absolutePath": str(target),
                    "kind": str(item.get("kind", "file")),
                    "description": str(item.get("description", "")),
                    "bytes": len(content.encode("utf-8")),
                }
            )
        return written

    def build_deliverable_archive(
        self,
        *,
        task_id: str,
        workspace_path: str,
        files: list[dict[str, Any]],
    ) -> str:
        workspace_root = Path(workspace_path).resolve()
        if not workspace_root.exists():
            raise ValueError("workspace path does not exist")

        archive_dir = (self.base_path / "downloads").resolve()
        archive_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archive_path = archive_dir / f"{task_id}_deliverables_{now}.zip"

        entries: list[tuple[Path, str]] = []
        for item in files:
            abs_path = str(item.get("absolutePath", "") or "").strip()
            rel_path = str(item.get("path", "") or "").strip()
            if not abs_path:
                continue
            source = Path(abs_path).resolve()
            if not source.exists() or not source.is_file():
                continue
            try:
                source.relative_to(workspace_root)
            except ValueError:
                continue
            if not rel_path:
                rel_path = str(source.relative_to(workspace_root)).replace("\\", "/")
            entries.append((source, rel_path))

        if not entries:
            raise ValueError("no deliverable files available for archive")

        with ZipFile(archive_path, mode="w", compression=ZIP_DEFLATED) as zip_file:
            for source, rel_path in entries:
                zip_file.write(source, arcname=rel_path)

        return str(archive_path)
