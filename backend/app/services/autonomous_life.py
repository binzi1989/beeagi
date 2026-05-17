from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
import json
import re
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
        self._last_event_marker: str | None = None
        self._no_new_signal_streak = 0

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

        latest_event_marker = self._latest_event_marker()
        with self._lock:
            previous_marker = self._last_event_marker
            has_new_signal = latest_event_marker is not None and latest_event_marker != previous_marker
            if has_new_signal:
                self._no_new_signal_streak = 0
            else:
                self._no_new_signal_streak += 1
            no_new_signal_streak = self._no_new_signal_streak
            self._last_event_marker = latest_event_marker

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
            should_run_patrol = (
                reason == "manual"
                or has_new_signal
                or no_new_signal_streak % max(1, self.settings.autonomous_life_patrol_no_signal_interval) == 0
            )
            if should_run_patrol:
                patrol = self.pipeline.run_scout_patrol(sample_size=patrol_sample)
            else:
                patrol = {"sampledTasks": 0, "deposited": 0, "evaporated": 0, "expired": 0, "skipped": 1}
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
            event_mix = self._build_event_mix(limit=80)
            reflection = self._run_light_reflection(
                reason=reason,
                is_idle=is_idle,
                has_new_signal=has_new_signal,
                no_new_signal_streak=no_new_signal_streak,
                ensured=ensured,
                patrol=patrol,
                promoted=promoted,
                event_mix=event_mix,
            )
            report = self._compose_report(
                cycle=self._cycles + 1,
                reason=reason,
                status="error",
                is_idle=is_idle,
                has_new_signal=has_new_signal,
                no_new_signal_streak=no_new_signal_streak,
                ensured=ensured,
                patrol=patrol,
                promoted=promoted,
                event_mix=event_mix,
                reflection=reflection,
                created_at=ended,
                error=str(exc),
            )
            summary = {
                "reason": reason,
                "status": "error",
                "error": str(exc),
                "idle": is_idle,
                "hasNewSignal": has_new_signal,
                "noNewSignalStreak": no_new_signal_streak,
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
        event_mix = self._build_event_mix(limit=80)
        reflection = self._run_light_reflection(
            reason=reason,
            is_idle=is_idle,
            has_new_signal=has_new_signal,
            no_new_signal_streak=no_new_signal_streak,
            ensured=ensured,
            patrol=patrol,
            promoted=promoted,
            event_mix=event_mix,
        )
        report = self._compose_report(
            cycle=self._cycles + 1,
            reason=reason,
            status="ok",
            is_idle=is_idle,
            has_new_signal=has_new_signal,
            no_new_signal_streak=no_new_signal_streak,
            ensured=ensured,
            patrol=patrol,
            promoted=promoted,
            event_mix=event_mix,
            reflection=reflection,
            created_at=ended,
        )
        summary = {
            "reason": reason,
            "status": "ok",
            "idle": is_idle,
            "hasNewSignal": has_new_signal,
            "noNewSignalStreak": no_new_signal_streak,
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
        has_new_signal: bool,
        no_new_signal_streak: int,
        ensured: dict[str, int],
        patrol: dict[str, Any],
        promoted: dict[str, int],
        event_mix: dict[str, int],
        reflection: dict[str, Any] | None,
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
        if not has_new_signal:
            learned_parts.append(f"no new external signals detected for {no_new_signal_streak} cycle(s)")
            if no_new_signal_streak >= 2:
                probe = self._select_probe_focus(cycle=cycle)
                learned_parts.append(f"switched to exploratory probe: {probe['tag']}")
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

        if not has_new_signal and no_new_signal_streak >= 2:
            next_focus = self._select_probe_focus(cycle=cycle)["next"]

        if reflection:
            learned_delta = str(reflection.get("learnedDelta", "")).strip()
            next_probe = str(reflection.get("nextProbe", "")).strip()
            novelty_tag = str(reflection.get("noveltyTag", "")).strip()
            if learned_delta:
                learned_parts.append(f"lightweight-model reflection: {learned_delta}")
            if next_probe:
                next_focus = next_probe
            if novelty_tag:
                learned_parts.append(f"novelty tag: {novelty_tag}")

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
                "hasNewSignal": 1 if has_new_signal else 0,
                "noNewSignalStreak": int(no_new_signal_streak),
                "dominantTopicWeightPct": int(self._dominant_weight_pct(event_mix)),
            },
            "createdAt": created_at.isoformat(),
        }

    def _latest_event_marker(self) -> str | None:
        try:
            events = self.pipeline.list_events(limit=1)
        except Exception:
            return None
        if not events:
            return None
        evt = events[0]
        created = getattr(evt, "created_at", None)
        created_str = created.isoformat() if created is not None else ""
        return f"{getattr(evt, 'id', '')}|{getattr(evt, 'topic', '')}|{created_str}"

    def _build_event_mix(self, *, limit: int = 80) -> dict[str, int]:
        try:
            rows = self.pipeline.list_events(limit=max(5, min(limit, 300)))
        except Exception:
            return {}
        bucket: dict[str, int] = {}
        for evt in rows:
            topic = str(getattr(evt, "topic", "") or "")
            if not topic:
                continue
            bucket[topic] = bucket.get(topic, 0) + 1
        return bucket

    def _dominant_weight_pct(self, event_mix: dict[str, int]) -> float:
        if not event_mix:
            return 0.0
        total = sum(max(0, int(v)) for v in event_mix.values())
        if total <= 0:
            return 0.0
        dominant = max(max(0, int(v)) for v in event_mix.values())
        return round((dominant / total) * 100.0, 2)

    def _select_probe_focus(self, *, cycle: int) -> dict[str, str]:
        probes = [
            {
                "tag": "long-tail-intents",
                "next": "probe low-frequency intent clusters and lift route diversity before next promotion",
            },
            {
                "tag": "feedback-hard-cases",
                "next": "target high-edit-distance and retry-heavy tasks for corrective candidate generation",
            },
            {
                "tag": "reliability-balance",
                "next": "cross-check pheromone reliability against adoption signals and prune unstable routes",
            },
        ]
        index = max(0, cycle) % len(probes)
        return probes[index]

    def _run_light_reflection(
        self,
        *,
        reason: str,
        is_idle: bool,
        has_new_signal: bool,
        no_new_signal_streak: int,
        ensured: dict[str, int],
        patrol: dict[str, Any],
        promoted: dict[str, int],
        event_mix: dict[str, int],
    ) -> dict[str, Any] | None:
        if not self.settings.autonomous_life_reflection_enabled:
            return None
        if self.pipeline.model_router is None:
            return None
        every = max(1, self.settings.autonomous_life_reflection_every_cycles)
        if reason == "heartbeat" and (self._cycles + 1) % every != 0:
            return None

        top_topics = sorted(event_mix.items(), key=lambda item: item[1], reverse=True)[:5]
        history = self.list_reports(limit=3)
        history_focus = [str(item.get("nextFocus", "")).strip() for item in history if item.get("nextFocus")]

        prompt_payload = {
            "reason": reason,
            "idle": is_idle,
            "hasNewSignal": has_new_signal,
            "noNewSignalStreak": no_new_signal_streak,
            "ensured": ensured,
            "patrol": {
                "sampledTasks": int(patrol.get("sampledTasks", 0)),
                "deposited": int(patrol.get("deposited", 0)),
            },
            "promotions": promoted,
            "topTopics": top_topics,
            "recentNextFocus": history_focus,
        }
        payload_text = json.dumps(prompt_payload, ensure_ascii=False)
        max_chars = max(300, int(self.settings.autonomous_life_reflection_prompt_max_chars))
        if len(payload_text) > max_chars:
            payload_text = payload_text[:max_chars]

        prompt = (
            "You are BeeAGI lightweight self-evolution reflector. "
            "Generate a short novel evolution delta, avoid repeating previous focuses. "
            "Return strict JSON only with keys learnedDelta, nextProbe, noveltyTag.\n"
            f"{payload_text}"
        )
        try:
            result = self.pipeline.model_router.generate(prompt)
        except Exception:
            return None

        parsed = self._extract_json_dict(result.text)
        if not parsed:
            return None
        return {
            "provider": result.provider,
            "model": result.model,
            "learnedDelta": str(parsed.get("learnedDelta", "")).strip(),
            "nextProbe": str(parsed.get("nextProbe", "")).strip(),
            "noveltyTag": str(parsed.get("noveltyTag", "")).strip(),
        }

    def _extract_json_dict(self, text: str) -> dict[str, Any] | None:
        raw = text.strip()
        if not raw:
            return None
        candidates: list[str] = []
        if raw.startswith("{") and raw.endswith("}"):
            candidates.append(raw)
        matches = re.findall(r"\{[\s\S]*\}", raw)
        candidates.extend(matches)
        for chunk in candidates:
            try:
                payload = json.loads(chunk)
            except Exception:
                continue
            if isinstance(payload, dict):
                return payload
        return None
