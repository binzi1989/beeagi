from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable

from app.core.config import Settings
from app.services.pipeline import PipelineService


class AutonomousLifeEngine:
    def __init__(self, *, pipeline: PipelineService, settings: Settings) -> None:
        self.pipeline = pipeline
        self.settings = settings
        self._lock = Lock()
        self._loop_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        now = datetime.now(timezone.utc)
        self._last_activity_at = now
        self._last_cycle_at: datetime | None = None
        self._started_at: datetime | None = None
        self._cycles = 0
        self._last_cycle_seconds = 0.0
        self._last_summary: dict[str, Any] = {}
        self._last_report: dict[str, Any] | None = None
        self._reports: deque[dict[str, Any]] = deque(maxlen=240)

    def touch(self, reason: str = "external") -> None:
        now = datetime.now(timezone.utc)
        with self._lock:
            self._last_activity_at = now
            self._last_summary = {
                **self._last_summary,
                "lastTouchReason": reason,
                "lastTouchAt": now.isoformat(),
            }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            now = datetime.now(timezone.utc)
            last_cycle_age = None
            if self._last_cycle_at is not None:
                last_cycle_age = max(0.0, (now - self._last_cycle_at).total_seconds())
            activity_age = max(0.0, (now - self._last_activity_at).total_seconds())
            status = "idle" if activity_age >= self.settings.autonomous_life_idle_after_seconds else "active"
            return {
                "enabled": self.settings.autonomous_life_enabled,
                "running": self._loop_task is not None and not self._loop_task.done(),
                "status": status,
                "startedAt": self._started_at.isoformat() if self._started_at else None,
                "lastActivityAt": self._last_activity_at.isoformat(),
                "lastCycleAt": self._last_cycle_at.isoformat() if self._last_cycle_at else None,
                "lastCycleAgeSeconds": round(last_cycle_age, 3) if last_cycle_age is not None else None,
                "cycles": self._cycles,
                "lastCycleSeconds": round(self._last_cycle_seconds, 3),
                "lastSummary": dict(self._last_summary),
                "lastReport": dict(self._last_report) if self._last_report else None,
                "reportCount": len(self._reports),
                "idleAfterSeconds": self.settings.autonomous_life_idle_after_seconds,
                "activeIntervalSeconds": self.settings.autonomous_life_min_interval_seconds,
                "idleIntervalSeconds": self.settings.autonomous_life_idle_interval_seconds,
            }

    def list_reports(self, *, limit: int = 24) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(limit, 200))
        with self._lock:
            rows = list(self._reports)[-bounded_limit:]
        rows.reverse()
        return [dict(item) for item in rows]

    async def start(self) -> None:
        if not self.settings.autonomous_life_enabled:
            return
        if self._loop_task is not None and not self._loop_task.done():
            return
        self._stop_event.clear()
        self._started_at = datetime.now(timezone.utc)
        self.touch("life-start")
        self._loop_task = asyncio.create_task(self._run_loop(), name="beeagi-autonomous-life")

    async def stop(self) -> None:
        self._stop_event.set()
        task = self._loop_task
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        self._loop_task = None

    async def run_cycle_now(self, reason: str = "manual") -> dict[str, Any]:
        summary = await asyncio.to_thread(self._run_cycle_sync, reason)
        return summary

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            now = datetime.now(timezone.utc)
            with self._lock:
                activity_age = max(0.0, (now - self._last_activity_at).total_seconds())
            is_idle = activity_age >= self.settings.autonomous_life_idle_after_seconds
            interval = (
                self.settings.autonomous_life_idle_interval_seconds
                if is_idle
                else self.settings.autonomous_life_min_interval_seconds
            )
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=max(1, interval))
                break
            except asyncio.TimeoutError:
                pass
            await asyncio.to_thread(self._run_cycle_sync, "heartbeat")

    def _run_cycle_sync(self, reason: str) -> dict[str, Any]:
        started = datetime.now(timezone.utc)
        with self._lock:
            activity_age = max(0.0, (started - self._last_activity_at).total_seconds())
        is_idle = activity_age >= self.settings.autonomous_life_idle_after_seconds

        patrol_sample = (
            self.settings.autonomous_life_patrol_sample_idle
            if is_idle
            else self.settings.autonomous_life_patrol_sample_active
        )
        evolution_limit = (
            self.settings.autonomous_life_evolution_limit_idle
            if is_idle
            else self.settings.autonomous_life_evolution_limit_active
        )
        promote_limit = (
            self.settings.autonomous_life_auto_promote_limit_idle
            if is_idle
            else self.settings.autonomous_life_auto_promote_limit_active
        )

        ensured = {"submitted": 0, "skipped": 0, "failed": 0}
        promoted = {"promoted": 0, "rolled_back": 0, "validated": 0, "rejected": 0, "skipped": 0}
        patrol = {"sampledTasks": 0, "deposited": 0}

        try:
            if self.settings.autonomous_life_self_evolution_enabled:
                ensured = self.pipeline.ensure_recent_tasks_self_evolution(
                    limit=evolution_limit,
                    created_by="life-loop",
                    source="autonomous-life",
                )
            patrol = self.pipeline.run_scout_patrol(sample_size=patrol_sample)
            if self.settings.autonomous_life_auto_promote_enabled:
                outcomes = self.pipeline.auto_promote_candidates(
                    limit=promote_limit,
                    approved_by="queen-autonomous-life",
                )
                for row in outcomes:
                    decision = str(row.get("decision", "skipped"))
                    if decision in promoted:
                        promoted[decision] += 1
                    else:
                        promoted["skipped"] += 1
        except Exception as exc:  # pragma: no cover
            ended = datetime.now(timezone.utc)
            report = self._compose_report(
                cycle=self._cycles + 1,
                reason=reason,
                status="error",
                is_idle=is_idle,
                ensured=ensured,
                patrol=patrol,
                promoted=promoted,
                created_at=ended,
                error=str(exc),
            )
            summary = {
                "reason": reason,
                "status": "error",
                "error": str(exc),
                "idle": is_idle,
                "ensured": ensured,
                "patrol": patrol,
                "promotions": promoted,
                "startedAt": started.isoformat(),
                "endedAt": ended.isoformat(),
                "report": report,
            }
            self._record_cycle(ended=ended, started=started, summary=summary, report=report)
            return summary

        ended = datetime.now(timezone.utc)
        report = self._compose_report(
            cycle=self._cycles + 1,
            reason=reason,
            status="ok",
            is_idle=is_idle,
            ensured=ensured,
            patrol=patrol,
            promoted=promoted,
            created_at=ended,
        )
        summary = {
            "reason": reason,
            "status": "ok",
            "idle": is_idle,
            "ensured": ensured,
            "patrol": {
                "sampledTasks": int(patrol.get("sampledTasks", 0)),
                "deposited": int(patrol.get("deposited", 0)),
                "evaporated": int(patrol.get("evaporated", 0)),
            },
            "promotions": promoted,
            "startedAt": started.isoformat(),
            "endedAt": ended.isoformat(),
            "report": report,
        }
        self._record_cycle(ended=ended, started=started, summary=summary, report=report)
        return summary

    def _record_cycle(
        self,
        *,
        ended: datetime,
        started: datetime,
        summary: dict[str, Any],
        report: dict[str, Any],
    ) -> None:
        with self._lock:
            self._last_cycle_at = ended
            self._cycles += 1
            self._last_cycle_seconds = max(0.0, (ended - started).total_seconds())
            self._last_summary = summary
            self._last_report = report
            self._reports.append(report)

    def _compose_report(
        self,
        *,
        cycle: int,
        reason: str,
        status: str,
        is_idle: bool,
        ensured: dict[str, int],
        patrol: dict[str, Any],
        promoted: dict[str, int],
        created_at: datetime,
        error: str | None = None,
    ) -> dict[str, Any]:
        ensured_submitted = int(ensured.get("submitted", 0))
        ensured_failed = int(ensured.get("failed", 0))
        patrol_deposited = int(patrol.get("deposited", 0))
        patrol_sampled = int(patrol.get("sampledTasks", 0))
        promoted_count = int(promoted.get("promoted", 0))
        validated_count = int(promoted.get("validated", 0))
        rejected_count = int(promoted.get("rejected", 0))
        rollback_count = int(promoted.get("rolled_back", 0))

        learned_parts: list[str] = []
        if ensured_submitted > 0:
            learned_parts.append(
                f"absorbed {ensured_submitted} unattended task feedback signal(s) into evolution candidates"
            )
        if patrol_deposited > 0:
            learned_parts.append(
                f"scouts deposited {patrol_deposited} pheromone route(s) from {patrol_sampled} sampled task(s)"
            )
        if promoted_count > 0:
            learned_parts.append(f"queen promoted {promoted_count} validated candidate skill(s)")
        if validated_count > 0:
            learned_parts.append(f"validated {validated_count} candidate(s) waiting for canary confidence")
        if status != "ok" and error:
            learned_parts.append(f"cycle hit an exception: {error}")
        if not learned_parts:
            learned_parts.append("this cycle stayed stable with no significant delta yet")

        if rollback_count > 0 or rejected_count > 0:
            next_focus = "tighten risk filters and revise low-performing deltas before promotion"
        elif validated_count > 0 and promoted_count == 0:
            next_focus = "collect more canary feedback and decide promote vs rollback"
        elif ensured_submitted > 0:
            next_focus = "replay new candidates in shadow mode and prepare canary exposure"
        elif is_idle:
            next_focus = "keep low-cost scouting and wait for fresh user interaction signals"
        else:
            next_focus = "increase scout patrol density and keep feedback absorption warm"

        vitality_score = (
            ensured_submitted * 1.2
            + patrol_deposited * 0.12
            + promoted_count * 1.6
            + validated_count * 0.5
            - rollback_count * 0.8
            - rejected_count * 0.5
            - ensured_failed * 0.6
        )
        if status != "ok":
            vitality_score -= 1.2

        if vitality_score >= 2.5:
            vitality = "high"
        elif vitality_score >= 0.8:
            vitality = "medium"
        else:
            vitality = "low"

        confidence = 0.58 + vitality_score * 0.08
        confidence = max(0.08, min(0.98, confidence))

        return {
            "id": f"life-cycle-{cycle}",
            "cycle": cycle,
            "reason": reason,
            "status": status,
            "idle": is_idle,
            "vitality": vitality,
            "confidence": round(confidence, 3),
            "learned": "; ".join(learned_parts),
            "nextFocus": next_focus,
            "signals": {
                "ensuredSubmitted": ensured_submitted,
                "ensuredFailed": ensured_failed,
                "patrolDeposited": patrol_deposited,
                "patrolSampledTasks": patrol_sampled,
                "promoted": promoted_count,
                "validated": validated_count,
                "rejected": rejected_count,
                "rolledBack": rollback_count,
            },
            "createdAt": created_at.isoformat(),
        }
