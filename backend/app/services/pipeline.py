from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Callable

from sqlalchemy import desc
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.models.evolution import CandidateStatusAudit, EvolutionEvent, ScoutPheromone
from app.models.feedback import TaskFeedback
from app.models.skill import CandidateStatus, Skill, SkillCandidate
from app.models.task import Task, TaskStatus
from app.schemas.feedback import ConversationTurn, FeedbackPacket
from app.schemas.skills import SkillDelta
from app.schemas.tasks import TaskSpec
from app.services.agents.queen import QueenAgent
from app.services.agents.scout import ScoutAgent
from app.services.agents.worker import WorkerAgent
from app.services.agents.worm import WormAgent
from app.services.artifact_store import ArtifactStore
from app.services.canary_allocator import CanaryAllocator
from app.services.event_bus import EventBus, EventTopic
from app.services.model_router import ModelRouter
from app.services.shadow_replay import ShadowReplayEvaluator


class PipelineService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        event_bus: EventBus,
        settings: Settings,
        artifact_store: ArtifactStore | None = None,
        model_router: ModelRouter | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.event_bus = event_bus
        self.settings = settings
        self.artifact_store = artifact_store
        self.model_router = model_router
        self.canary_allocator = CanaryAllocator(settings.canary_slice_ratio)
        self.shadow_replay = ShadowReplayEvaluator()
        self.scout = ScoutAgent()
        self.worker = WorkerAgent(model_router=model_router)
        self.worm = WormAgent()
        self.queen = QueenAgent(settings)
        self._life_signal: Callable[[str], None] | None = None

    def set_life_signal(self, callback: Callable[[str], None] | None) -> None:
        self._life_signal = callback

    def _signal_life(self, reason: str) -> None:
        if self._life_signal is None:
            return
        try:
            self._life_signal(reason)
        except Exception:
            return

    def _publish(self, db: Session, topic: str, payload: dict[str, Any]) -> None:
        self.event_bus.publish(topic, payload)
        db.add(EvolutionEvent(topic=topic, payload=payload))

    def _clamp(self, value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, value))

    def _normalize_intent_cluster(self, goal: str) -> str:
        tokens = re.findall(r"[a-z0-9\u4e00-\u9fff]+", goal.lower())
        if not tokens:
            return "general"
        return "-".join(tokens[:4])[:120]

    def _to_aware_utc(self, value: datetime | None) -> datetime:
        if value is None:
            return datetime.now(timezone.utc)
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _evaporate_pheromones(self, db: Session) -> tuple[int, int]:
        now = datetime.now(timezone.utc)
        evaporation_rate = self._clamp(self.settings.scout_pheromone_evaporation_rate, 0.0, 0.5)
        min_strength = self._clamp(self.settings.scout_pheromone_min_strength, 0.0, 0.5)
        rows = db.query(ScoutPheromone).all()

        evaporated = 0
        expired = 0
        for row in rows:
            expires_at = self._to_aware_utc(row.expires_at)
            updated_at = self._to_aware_utc(row.updated_at)

            if expires_at <= now:
                if row.strength > 0:
                    row.strength = 0.0
                    expired += 1
                continue

            elapsed_hours = max(0.0, (now - updated_at).total_seconds() / 3600.0)
            if elapsed_hours < 0.2:
                continue

            decay_factor = (1.0 - evaporation_rate) ** elapsed_hours
            next_strength = self._clamp(row.strength * decay_factor, 0.0, 1.0)
            if next_strength < min_strength:
                next_strength = next_strength * 0.5

            if abs(next_strength - row.strength) >= 0.005:
                row.strength = round(next_strength, 6)
                evaporated += 1

        if evaporated > 0 or expired > 0:
            self._publish(
                db,
                EventTopic.scout_pheromone_evaporated,
                {
                    "evaporated": evaporated,
                    "expired": expired,
                },
            )

        return evaporated, expired

    def _deposit_scout_pheromones(
        self,
        *,
        db: Session,
        intent_cluster: str,
        scout_report: dict[str, Any],
    ) -> list[str]:
        now = datetime.now(timezone.utc)
        ttl_seconds = max(3600, self.settings.scout_pheromone_ttl_hours * 3600)
        signals = scout_report.get("signals", [])
        if not isinstance(signals, list):
            return []

        inserted = 0
        updated = 0
        pheromone_ids: list[str] = []
        for signal in signals:
            if not isinstance(signal, dict):
                continue
            source = str(signal.get("source", "scout")).strip().lower()[:120] or "scout"
            route = str(signal.get("route", "unknown://route")).strip()[:300]
            novelty = self._safe_float(signal.get("novelty"), fallback=0.5, minimum=0.0, maximum=1.0)
            reliability = self._safe_float(signal.get("reliability"), fallback=0.7, minimum=0.0, maximum=1.0)
            cost = self._safe_float(signal.get("cost"), fallback=0.1, minimum=0.0, maximum=1.0)
            signal_strength = self._clamp(novelty * 0.35 + reliability * 0.55 - cost * 0.2, 0.0, 1.0)

            row = (
                db.query(ScoutPheromone)
                .filter(
                    ScoutPheromone.intent_cluster == intent_cluster,
                    ScoutPheromone.source == source,
                    ScoutPheromone.route == route,
                )
                .first()
            )
            if row is None:
                row = ScoutPheromone(
                    intent_cluster=intent_cluster,
                    source=source,
                    route=route,
                    novelty=novelty,
                    reliability=reliability,
                    cost=cost,
                    reward=0.0,
                    strength=signal_strength,
                    ttl_seconds=ttl_seconds,
                    usage_count=0,
                    success_count=0,
                    failure_count=0,
                    notes=str(signal.get("notes", "") or "")[:600] or None,
                    metadata_json={
                        "seed": signal,
                        "updatedBy": "scout.scan",
                    },
                    last_seen_at=now,
                    expires_at=now + timedelta(seconds=ttl_seconds),
                )
                db.add(row)
                db.flush()
                inserted += 1
            else:
                row.novelty = novelty
                row.reliability = reliability
                row.cost = cost
                row.strength = round(self._clamp(row.strength * 0.55 + signal_strength * 0.45, 0.0, 1.0), 6)
                row.last_seen_at = now
                row.ttl_seconds = ttl_seconds
                row.expires_at = now + timedelta(seconds=ttl_seconds)
                metadata = dict(row.metadata_json or {})
                metadata["seed"] = signal
                metadata["updatedBy"] = "scout.scan"
                row.metadata_json = metadata
                updated += 1

            pheromone_ids.append(row.id)

        if inserted > 0 or updated > 0:
            self._publish(
                db,
                EventTopic.scout_pheromone_deposited,
                {
                    "intentCluster": intent_cluster,
                    "inserted": inserted,
                    "updated": updated,
                    "total": inserted + updated,
                },
            )
        return pheromone_ids

    def _select_task_pheromones(self, db: Session, task: Task) -> list[ScoutPheromone]:
        now = datetime.now(timezone.utc)
        cluster = self._normalize_intent_cluster(task.goal)
        top_k = max(1, min(self.settings.scout_pheromone_top_k, 12))
        rows = (
            db.query(ScoutPheromone)
            .filter(
                ScoutPheromone.intent_cluster == cluster,
                ScoutPheromone.expires_at > now,
            )
            .order_by(desc(ScoutPheromone.strength), desc(ScoutPheromone.updated_at))
            .limit(top_k)
            .all()
        )

        for row in rows:
            row.usage_count += 1
            row.last_seen_at = now

        return rows

    def _reward_task_pheromones(
        self,
        *,
        db: Session,
        task: Task,
        packet: FeedbackPacket,
    ) -> int:
        scout_report = task.scout_report if isinstance(task.scout_report, dict) else {}
        pheromone_ids = scout_report.get("pheromoneIds", [])
        if not isinstance(pheromone_ids, list) or not pheromone_ids:
            return 0

        explicit_score = packet.explicit_score if packet.explicit_score is not None else 0.8
        retry_count = float(packet.implicit_signals.get("retryCount", 0.0))
        error_rise = float(packet.implicit_signals.get("errorRateRise", 0.0))
        adoption = float(packet.implicit_signals.get("adoptionRate", 0.8))

        reward = (explicit_score - 0.8) * 0.65 + (adoption - 0.8) * 0.25 - retry_count * 0.03 - error_rise * 0.8
        reward = self._clamp(reward, -0.5, 0.5)

        updated = 0
        for pheromone_id in pheromone_ids:
            row = db.get(ScoutPheromone, str(pheromone_id))
            if not row:
                continue
            row.reward = round(row.reward + reward, 6)
            row.strength = round(self._clamp(row.strength + reward * 0.25, 0.0, 1.0), 6)
            if reward >= 0:
                row.success_count += 1
            else:
                row.failure_count += 1
            updated += 1

        return updated

    def _audit_candidate_status(
        self,
        *,
        db: Session,
        candidate: SkillCandidate,
        from_status: str | None,
        to_status: str,
        actor: str,
        decision: str | None,
        reason: str | None,
        context: dict[str, Any] | None = None,
    ) -> None:
        if from_status == to_status:
            return
        db.add(
            CandidateStatusAudit(
                candidate_id=candidate.id,
                skill_id=candidate.skill_id,
                from_status=from_status,
                to_status=to_status,
                decision=decision,
                reason=reason,
                actor=actor,
                context=context or {},
            )
        )

    def _validate_patch_permissions(self, skill: Skill, patch: dict[str, Any]) -> None:
        proposed_permissions = patch.get("permissions")
        if not proposed_permissions:
            return
        for key, value in proposed_permissions.items():
            current = skill.permissions.get(key)
            if value != current:
                raise ValueError(f"permission escalation blocked for '{key}'")

    def _find_canary_candidate(self, db: Session, skill_id: str) -> SkillCandidate | None:
        return (
            db.query(SkillCandidate)
            .filter(
                SkillCandidate.skill_id == skill_id,
                SkillCandidate.status == CandidateStatus.validated.value,
            )
            .order_by(desc(SkillCandidate.updated_at))
            .first()
        )

    def _estimate_shadow_score_from_delta(self, delta: SkillDelta) -> float:
        patch = delta.patch or {}
        score = 1.0
        if "promptTweaks" in patch:
            score += 0.09
        tool_policy = patch.get("toolPolicy")
        if isinstance(tool_policy, dict):
            score += 0.09
            max_retries = tool_policy.get("maxRetries")
            if isinstance(max_retries, int) and max_retries <= 1:
                score -= 0.03
            if tool_policy.get("preferLowRiskTools") is True:
                score += 0.02
        return max(0.8, min(1.2, round(score, 4)))

    def _apply_patch_to_skill_config(self, config: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        updated = deepcopy(config)
        prompt_tweaks = patch.get("promptTweaks")
        if isinstance(prompt_tweaks, dict):
            updated["promptTweaks"] = {
                **dict(updated.get("promptTweaks") or {}),
                **prompt_tweaks,
            }

        tool_policy = patch.get("toolPolicy")
        if isinstance(tool_policy, dict):
            updated["toolPolicy"] = {
                **dict(updated.get("toolPolicy") or {}),
                **tool_policy,
            }
        return updated

    def _resolve_execution_skills(
        self,
        *,
        db: Session,
        task: Task,
        active_skills: list[Skill],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        selected: list[dict[str, Any]] = []
        canary_assignments: list[dict[str, Any]] = []
        for skill in active_skills:
            runtime = {
                "id": skill.id,
                "version": skill.version,
                "strategy": skill.config.get("strategy", "default"),
                "variant": "baseline",
            }
            candidate = self._find_canary_candidate(db, skill.id)
            if candidate is None:
                selected.append(runtime)
                continue

            is_canary, bucket = self.canary_allocator.is_selected(
                user_id=task.created_by,
                skill_id=skill.id,
                candidate_id=candidate.id,
            )
            if is_canary:
                runtime = {
                    **runtime,
                    "variant": "canary",
                    "candidateId": candidate.id,
                    "candidatePatch": candidate.proposed_delta.get("patch", {}),
                }
                canary_assignments.append(
                    {
                        "skillId": skill.id,
                        "candidateId": candidate.id,
                        "bucket": bucket,
                        "ratio": self.settings.canary_slice_ratio,
                    }
                )
            selected.append(runtime)
        return selected, canary_assignments

    def _update_canary_candidate_metrics(
        self,
        *,
        db: Session,
        task: Task,
        packet: FeedbackPacket,
    ) -> None:
        result_payload = task.result_payload or {}
        assignments = result_payload.get("canaryAssignments", [])
        if not isinstance(assignments, list):
            return

        for assignment in assignments:
            candidate_id = assignment.get("candidateId")
            if not candidate_id:
                continue
            candidate = db.get(SkillCandidate, candidate_id)
            if not candidate:
                continue
            evidence = dict(candidate.evidence or {})
            stats = dict(evidence.get("canaryStats") or {})
            counted_task_ids = list(stats.get("countedTaskIds") or [])
            counted_task_id_set = {str(task_id) for task_id in counted_task_ids}
            if task.id in counted_task_id_set:
                continue

            counted_task_id_set.add(task.id)
            exposures = int(stats.get("exposures", 0)) + 1
            feedback_count = int(stats.get("feedbackCount", 0)) + 1
            explicit_score_sum = float(stats.get("explicitScoreSum", 0.0))
            retry_count_sum = float(stats.get("retryCountSum", 0.0))
            error_rate_rise_sum = float(stats.get("errorRateRiseSum", 0.0))
            adoption_rate_sum = float(stats.get("adoptionRateSum", 0.0))

            explicit_score = packet.explicit_score if packet.explicit_score is not None else 0.8
            retry_count = float(packet.implicit_signals.get("retryCount", 0.0))
            error_rate_rise = float(packet.implicit_signals.get("errorRateRise", 0.0))
            adoption_rate = float(packet.implicit_signals.get("adoptionRate", 0.8))

            explicit_score_sum += explicit_score
            retry_count_sum += retry_count
            error_rate_rise_sum += error_rate_rise
            adoption_rate_sum += adoption_rate

            avg_explicit = explicit_score_sum / feedback_count
            avg_retry = retry_count_sum / feedback_count
            avg_error_rise = error_rate_rise_sum / feedback_count
            avg_adoption = adoption_rate_sum / feedback_count

            # combine quality, adoption, and reliability into canary score.
            computed_canary_score = max(
                0.0,
                min(
                    1.2,
                    1.0
                    + (avg_explicit - 0.8) * 0.5
                    + (avg_adoption - 0.8) * 0.2
                    - avg_retry * 0.02
                    - avg_error_rise * 0.5,
                ),
            )

            candidate.canary_score = computed_canary_score
            evidence["canaryErrorRise"] = avg_error_rise
            evidence["canaryStats"] = {
                "exposures": exposures,
                "feedbackCount": feedback_count,
                "countedTaskIds": sorted(counted_task_id_set)[-2000:],
                "explicitScoreSum": round(explicit_score_sum, 4),
                "retryCountSum": round(retry_count_sum, 4),
                "errorRateRiseSum": round(error_rate_rise_sum, 4),
                "adoptionRateSum": round(adoption_rate_sum, 4),
                "averageExplicitScore": round(avg_explicit, 4),
                "averageRetryCount": round(avg_retry, 4),
                "averageErrorRateRise": round(avg_error_rise, 4),
                "averageAdoptionRate": round(avg_adoption, 4),
                "computedCanaryScore": round(computed_canary_score, 4),
            }
            candidate.evidence = evidence
            self._publish(
                db,
                EventTopic.canary_observed,
                {
                    "taskId": task.id,
                    "candidateId": candidate.id,
                    "computedCanaryScore": round(computed_canary_score, 4),
                    "feedbackCount": feedback_count,
                },
            )

    def _safe_float(self, value: Any, fallback: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = fallback
        return max(minimum, min(maximum, parsed))

    def _extract_json_object(self, text: str) -> dict[str, Any] | None:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _infer_feedback_heuristic(
        self,
        *,
        task: Task,
        turns: list[ConversationTurn],
    ) -> tuple[FeedbackPacket, dict[str, Any]]:
        user_turns = [turn for turn in turns if turn.role.strip().lower() in {"user", "human", "client"}]
        conversation_text = "\n".join(turn.content for turn in turns if turn.content)
        user_text = "\n".join(turn.content for turn in user_turns if turn.content) or conversation_text
        lowered = user_text.lower()

        positive_keywords = [
            "good",
            "great",
            "solid",
            "nice",
            "works",
            "thanks",
            "满意",
            "很好",
            "不错",
            "可以",
            "赞",
        ]
        negative_keywords = [
            "bad",
            "wrong",
            "bug",
            "error",
            "issue",
            "fail",
            "broken",
            "problem",
            "差",
            "不行",
            "错误",
            "失败",
            "有问题",
            "抽象",
            "看不懂",
        ]
        action_keywords = [
            "please",
            "need",
            "should",
            "fix",
            "change",
            "improve",
            "加",
            "补",
            "优化",
            "改",
            "重做",
            "调整",
            "重新",
        ]
        retry_keywords = ["retry", "again", "rerun", "重试", "再来", "继续", "重新跑"]
        severe_keywords = ["critical", "严重", "崩溃", "crash", "high risk", "阻塞", "中断"]

        positive_hits = sum(1 for keyword in positive_keywords if keyword in lowered)
        negative_hits = sum(1 for keyword in negative_keywords if keyword in lowered)
        action_hits = sum(1 for keyword in action_keywords if keyword in lowered)
        retry_hits = sum(1 for keyword in retry_keywords if keyword in lowered)
        severe_hits = sum(1 for keyword in severe_keywords if keyword in lowered)

        quality_estimate_raw = task.result_payload.get("qualityEstimate") if isinstance(task.result_payload, dict) else None
        quality_estimate = self._safe_float(quality_estimate_raw, fallback=0.84, minimum=0.5, maximum=0.98)
        explicit_score = quality_estimate + (positive_hits - negative_hits) * 0.03 - action_hits * 0.012 - retry_hits * 0.015
        explicit_score = self._safe_float(explicit_score, fallback=quality_estimate, minimum=0.45, maximum=0.98)

        corrections = ""
        for turn in reversed(user_turns):
            text = turn.content.strip()
            if not text:
                continue
            if any(keyword in text.lower() for keyword in action_keywords + negative_keywords):
                corrections = text[:420]
                break
        if not corrections and user_turns:
            corrections = user_turns[-1].content.strip()[:320]

        summary_text = ""
        if isinstance(task.result_payload, dict):
            summary_value = task.result_payload.get("summary")
            if isinstance(summary_value, str):
                summary_text = summary_value

        if summary_text and (corrections or user_text):
            ratio = SequenceMatcher(
                a=summary_text.lower()[:1200],
                b=(corrections or user_text).lower()[:1200],
            ).ratio()
            edit_distance = self._safe_float(1 - ratio, fallback=0.12, minimum=0.03, maximum=0.95)
        else:
            edit_distance = self._safe_float(0.08 + action_hits * 0.03 + retry_hits * 0.02, fallback=0.12, minimum=0.03, maximum=0.5)

        metrics_retry = 0.0
        if isinstance(task.metrics, dict):
            metrics_retry = self._safe_float(task.metrics.get("retryCount"), fallback=0.0, minimum=0.0, maximum=8.0)
        retry_count = int(max(metrics_retry, retry_hits))

        adoption_rate = self._safe_float(
            0.8 + positive_hits * 0.03 - negative_hits * 0.04 - retry_count * 0.02,
            fallback=0.8,
            minimum=0.35,
            maximum=0.98,
        )
        error_rate_rise = self._safe_float(
            severe_hits * 0.02 + max(0, negative_hits - 1) * 0.01,
            fallback=0.0,
            minimum=0.0,
            maximum=0.3,
        )
        confidence = self._safe_float(
            0.55 + min(0.35, (positive_hits + negative_hits + action_hits) * 0.03),
            fallback=0.6,
            minimum=0.4,
            maximum=0.95,
        )

        packet = FeedbackPacket(
            explicit_score=round(explicit_score, 4),
            corrections=corrections or None,
            implicit_signals={
                "retryCount": retry_count,
                "editDistance": round(edit_distance, 4),
                "adoptionRate": round(adoption_rate, 4),
                "errorRateRise": round(error_rate_rise, 4),
                "confidence": round(confidence, 4),
                "inferenceSource": "heuristic",
            },
        )
        return packet, {
            "positiveHits": positive_hits,
            "negativeHits": negative_hits,
            "actionHits": action_hits,
            "retryHits": retry_hits,
            "severeHits": severe_hits,
            "confidence": round(confidence, 4),
        }

    def _infer_feedback_with_model(
        self,
        *,
        task: Task,
        turns: list[ConversationTurn],
    ) -> tuple[FeedbackPacket | None, dict[str, Any]]:
        if self.model_router is None:
            return None, {"enabled": False, "reason": "model router unavailable"}

        transcript = "\n".join(f"{turn.role}: {turn.content}" for turn in turns if turn.content)
        prompt = (
            "Infer a task feedback packet from the conversation. "
            "Return strict JSON with keys explicitScore, corrections, implicitSignals "
            "(retryCount, editDistance, adoptionRate, errorRateRise). "
            "Scores are in [0,1], retryCount is integer.\n\n"
            f"Task goal: {task.goal}\n"
            f"Task result: {task.result_payload}\n"
            f"Conversation:\n{transcript}\n"
        )
        try:
            llm_result = self.model_router.generate(prompt)
        except Exception as exc:  # pragma: no cover
            return None, {"enabled": True, "error": str(exc)}

        payload = self._extract_json_object(llm_result.text)
        if payload is None:
            return None, {
                "enabled": True,
                "provider": llm_result.provider,
                "model": llm_result.model,
                "error": "model output is not valid json",
            }

        feedback_payload = payload.get("feedback", payload)
        if not isinstance(feedback_payload, dict):
            return None, {
                "enabled": True,
                "provider": llm_result.provider,
                "model": llm_result.model,
                "error": "feedback payload is not an object",
            }

        implicit_payload = feedback_payload.get("implicitSignals", feedback_payload.get("implicit_signals"))
        if not isinstance(implicit_payload, dict):
            implicit_payload = {}

        explicit_score = feedback_payload.get("explicitScore", feedback_payload.get("explicit_score"))
        corrections = feedback_payload.get("corrections")
        packet = FeedbackPacket(
            explicit_score=self._safe_float(explicit_score, fallback=0.82, minimum=0.0, maximum=1.0),
            corrections=str(corrections).strip()[:420] if corrections else None,
            implicit_signals={
                "retryCount": int(self._safe_float(implicit_payload.get("retryCount"), fallback=0.0, minimum=0.0, maximum=8.0)),
                "editDistance": round(
                    self._safe_float(implicit_payload.get("editDistance"), fallback=0.12, minimum=0.0, maximum=1.0),
                    4,
                ),
                "adoptionRate": round(
                    self._safe_float(implicit_payload.get("adoptionRate"), fallback=0.8, minimum=0.0, maximum=1.0),
                    4,
                ),
                "errorRateRise": round(
                    self._safe_float(implicit_payload.get("errorRateRise"), fallback=0.0, minimum=0.0, maximum=1.0),
                    4,
                ),
                "inferenceSource": "model",
            },
        )
        return packet, {
            "enabled": True,
            "provider": llm_result.provider,
            "model": llm_result.model,
            "rawTextSize": len(llm_result.text),
        }

    def infer_feedback_packet(
        self,
        *,
        task: Task,
        turns: list[ConversationTurn],
    ) -> tuple[FeedbackPacket, dict[str, Any]]:
        heuristic_packet, heuristic_meta = self._infer_feedback_heuristic(task=task, turns=turns)
        model_packet, model_meta = self._infer_feedback_with_model(task=task, turns=turns)

        if model_packet is None:
            merged_packet = heuristic_packet
            merged_packet.implicit_signals["inferenceSource"] = "heuristic"
        else:
            merged_packet = FeedbackPacket(
                explicit_score=model_packet.explicit_score
                if model_packet.explicit_score is not None
                else heuristic_packet.explicit_score,
                corrections=model_packet.corrections or heuristic_packet.corrections,
                implicit_signals={
                    **heuristic_packet.implicit_signals,
                    **model_packet.implicit_signals,
                    "inferenceSource": "hybrid",
                },
            )

        return merged_packet, {
            "heuristic": heuristic_meta,
            "model": model_meta,
        }

    def auto_feedback_from_conversation(
        self,
        *,
        task_id: str,
        turns: list[ConversationTurn],
        created_by: str = "auto-feedback",
        only_if_missing: bool = True,
        source: str = "auto-inferred",
    ) -> dict[str, Any]:
        with self.session_factory() as db:
            task = db.get(Task, task_id)
            if not task:
                raise ValueError(f"task not found: {task_id}")
            existing_feedback = (
                db.query(TaskFeedback)
                .filter(TaskFeedback.task_id == task_id)
                .order_by(desc(TaskFeedback.created_at))
                .first()
            )
            if only_if_missing and existing_feedback:
                return {
                    "status": "skipped",
                    "reason": "manual feedback already exists",
                    "source": source,
                    "feedbackId": existing_feedback.id,
                    "candidateId": None,
                    "skillId": None,
                    "candidateStatus": None,
                    "inferredFeedback": None,
                }
            inferred_feedback, inference_meta = self.infer_feedback_packet(task=task, turns=turns)

        candidate = self.submit_feedback(task_id, inferred_feedback, created_by=created_by)

        with self.session_factory() as db:
            feedback = (
                db.query(TaskFeedback)
                .filter(TaskFeedback.task_id == task_id)
                .order_by(desc(TaskFeedback.created_at))
                .first()
            )
            self._publish(
                db,
                EventTopic.feedback_auto_inferred,
                {
                    "taskId": task_id,
                    "feedbackId": feedback.id if feedback else None,
                    "candidateId": candidate.id,
                    "source": source,
                    "inferenceMeta": inference_meta,
                },
            )
            db.commit()
        self._signal_life("feedback.auto_inferred")

        return {
            "status": "submitted",
            "reason": None,
            "source": source,
            "feedbackId": feedback.id if feedback else None,
            "candidateId": candidate.id,
            "skillId": candidate.skill_id,
            "candidateStatus": candidate.status,
            "inferredFeedback": inferred_feedback.model_dump(by_alias=True),
        }

    def ensure_task_self_evolution(
        self,
        *,
        task_id: str,
        created_by: str = "self-evolution",
        only_if_missing: bool = True,
        source: str = "self-evolution-guard",
    ) -> dict[str, Any]:
        with self.session_factory() as db:
            task = db.get(Task, task_id)
            if not task:
                raise ValueError(f"task not found: {task_id}")
            if task.status != TaskStatus.completed.value:
                raise ValueError("task is not completed yet")

            summary = ""
            if isinstance(task.result_payload, dict):
                raw_summary = task.result_payload.get("summary")
                if isinstance(raw_summary, str):
                    summary = raw_summary
                raw_llm_summary = task.result_payload.get("llmSummary")
                if isinstance(raw_llm_summary, str) and raw_llm_summary:
                    summary = f"{summary}\n{raw_llm_summary}".strip()

            if not summary:
                summary = task.goal

            turns = [
                ConversationTurn(role="user", content=task.goal),
                ConversationTurn(role="assistant", content=summary),
            ]

        result = self.auto_feedback_from_conversation(
            task_id=task_id,
            turns=turns,
            created_by=created_by,
            only_if_missing=only_if_missing,
            source=source,
        )

        with self.session_factory() as db:
            self._publish(
                db,
                EventTopic.feedback_self_evolution_guarded,
                {
                    "taskId": task_id,
                    "source": source,
                    "status": result.get("status"),
                    "reason": result.get("reason"),
                    "candidateId": result.get("candidateId"),
                },
            )
            db.commit()
        self._signal_life("feedback.self_evolution_guarded")
        return result

    def ensure_recent_tasks_self_evolution(
        self,
        *,
        limit: int = 3,
        created_by: str = "self-evolution-loop",
        source: str = "self-evolution-loop",
    ) -> dict[str, int]:
        bounded_limit = max(1, min(limit, 20))
        now = datetime.now(timezone.utc)
        lookback = now - timedelta(hours=24)

        with self.session_factory() as db:
            tasks = (
                db.query(Task)
                .filter(Task.status == TaskStatus.completed.value, Task.updated_at >= lookback)
                .order_by(desc(Task.updated_at))
                .limit(max(10, bounded_limit * 5))
                .all()
            )
            feedback_task_ids = {
                row[0]
                for row in db.query(TaskFeedback.task_id)
                .filter(TaskFeedback.task_id.in_([task.id for task in tasks]))
                .all()
            }

        submitted = 0
        skipped = 0
        failed = 0
        for task in tasks:
            if submitted >= bounded_limit:
                break
            if task.id in feedback_task_ids:
                skipped += 1
                continue
            try:
                result = self.ensure_task_self_evolution(
                    task_id=task.id,
                    created_by=created_by,
                    only_if_missing=True,
                    source=source,
                )
            except Exception:
                failed += 1
                continue
            if result.get("status") == "submitted":
                submitted += 1
            else:
                skipped += 1

        return {
            "submitted": submitted,
            "skipped": skipped,
            "failed": failed,
        }

    def create_task(self, spec: TaskSpec, created_by: str = "anonymous", run_immediately: bool = True) -> Task:
        with self.session_factory() as db:
            self._evaporate_pheromones(db)
            task = Task(
                goal=spec.goal,
                constraints=spec.constraints,
                context_refs=spec.context_refs,
                quality_target=spec.quality_target,
                priority=spec.priority,
                created_by=created_by,
                status=TaskStatus.queued.value,
            )
            db.add(task)
            db.flush()

            scout_report = self.scout.scan(spec)
            intent_cluster = self._normalize_intent_cluster(spec.goal)
            pheromone_ids = self._deposit_scout_pheromones(
                db=db,
                intent_cluster=intent_cluster,
                scout_report=scout_report,
            )
            scout_report["intentCluster"] = intent_cluster
            scout_report["pheromoneIds"] = pheromone_ids
            scout_report["pheromoneCount"] = len(pheromone_ids)
            task.scout_report = scout_report
            task.status = TaskStatus.planned.value
            self._publish(db, EventTopic.scout_reported, {"taskId": task.id, "report": scout_report})

            plan_graph = self.worker.build_plan(spec, scout_report)
            task.plan_graph = plan_graph
            self._publish(db, EventTopic.worker_planned, {"taskId": task.id, "planGraph": plan_graph})

            db.commit()
            db.refresh(task)
            self._signal_life("task.planned")

        if run_immediately:
            self.execute_task(task.id)
        return self.get_task(task.id)

    def execute_task(self, task_id: str) -> Task:
        with self.session_factory() as db:
            task = db.get(Task, task_id)
            if not task:
                raise ValueError(f"task not found: {task_id}")

            task.status = TaskStatus.running.value
            skills = db.query(Skill).filter(Skill.status == "active").order_by(Skill.id.asc()).all()
            selected, canary_assignments = self._resolve_execution_skills(
                db=db,
                task=task,
                active_skills=skills,
            )
            if canary_assignments:
                self._publish(
                    db,
                    EventTopic.canary_assigned,
                    {
                        "taskId": task.id,
                        "userId": task.created_by,
                        "ratio": self.settings.canary_slice_ratio,
                        "assignments": canary_assignments,
                    },
                )

            scout_pheromone_rows = self._select_task_pheromones(db, task)
            scout_pheromones = [
                {
                    "id": row.id,
                    "route": row.route,
                    "source": row.source,
                    "strength": row.strength,
                    "reliability": row.reliability,
                    "reward": row.reward,
                }
                for row in scout_pheromone_rows
            ]
            result, metrics = self.worker.execute(task, selected, scout_pheromones=scout_pheromones)
            deliverable_bundle = self.worker.build_deliverable_bundle(task, result)
            result["canaryAssignments"] = canary_assignments
            result["scoutPheromoneCount"] = len(scout_pheromones)
            metrics["canaryAssignedCount"] = len(canary_assignments)
            metrics["scoutPheromoneCount"] = len(scout_pheromones)

            deliverables: dict[str, Any] = {
                "scene": deliverable_bundle.get("scene", "general"),
                "title": deliverable_bundle.get("title", "Deliverable"),
                "status": "not_configured",
                "source": "none",
                "workspacePath": "",
                "allowWrite": False,
                "allowExecute": False,
                "files": [],
                "plannedFiles": [
                    {
                        "path": str(item.get("path", "")),
                        "kind": str(item.get("kind", "file")),
                        "description": str(item.get("description", "")),
                    }
                    for item in list(deliverable_bundle.get("files", []))
                    if isinstance(item, dict)
                ],
            }

            if self.artifact_store is not None:
                binding = self.artifact_store.resolve_workspace_binding(task.id, task.constraints)
                deliverables.update(
                    {
                        "status": "pending_write",
                        "workspacePath": binding["path"],
                        "allowWrite": bool(binding["allowWrite"]),
                        "allowExecute": bool(binding["allowExecute"]),
                        "source": str(binding["source"]),
                    }
                )
                metrics["workspaceBound"] = bool(binding["source"] == "bound")
                metrics["workspaceAllowWrite"] = bool(binding["allowWrite"])

                if binding["allowWrite"]:
                    try:
                        written_files = self.artifact_store.write_deliverable_files(
                            workspace_path=str(binding["path"]),
                            files=list(deliverable_bundle.get("files", [])),
                        )
                        deliverables["status"] = "written"
                        deliverables["files"] = written_files
                        deliverables["fileCount"] = len(written_files)
                        if written_files:
                            deliverables["primaryArtifact"] = written_files[0].get("absolutePath")
                        metrics["artifactFilesCount"] = len(written_files)
                        self._publish(
                            db,
                            EventTopic.worker_deliverable_written,
                            {
                                "taskId": task.id,
                                "scene": deliverables["scene"],
                                "workspacePath": deliverables["workspacePath"],
                                "fileCount": len(written_files),
                            },
                        )
                    except Exception as exc:
                        deliverables["status"] = "write_failed"
                        deliverables["error"] = str(exc)
                        metrics["artifactFilesCount"] = 0
                        task.status = TaskStatus.failed.value
                else:
                    deliverables["status"] = "write_disabled"
                    deliverables["reason"] = "workspaceBinding.allowWrite is false"
                    metrics["artifactFilesCount"] = 0
            else:
                deliverables["status"] = "artifact_store_unavailable"

            result["deliverables"] = deliverables
            task.result_payload = result
            task.metrics = metrics
            if task.status != TaskStatus.failed.value:
                task.status = TaskStatus.completed.value
            self._publish(
                db,
                EventTopic.worker_completed,
                {"taskId": task.id, "status": task.status, "metrics": metrics},
            )
            db.commit()
            db.refresh(task)
            self._signal_life("task.executed")
            return task

    def _extract_deliverables_payload(self, task: Task) -> dict[str, Any]:
        payload = task.result_payload if isinstance(task.result_payload, dict) else {}
        deliverables = payload.get("deliverables")
        if not isinstance(deliverables, dict):
            raise ValueError("deliverables are not available for this task")
        return deliverables

    def _resolve_workspace_root(self, deliverables: dict[str, Any]) -> Path:
        workspace_path = str(deliverables.get("workspacePath", "") or "").strip()
        if not workspace_path:
            raise ValueError("workspace path is missing")
        root = Path(workspace_path).resolve()
        if not root.exists():
            raise ValueError(f"workspace path not found: {workspace_path}")
        return root

    def _resolve_deliverable_file(
        self,
        *,
        deliverables: dict[str, Any],
        artifact_path: str | None = None,
    ) -> Path:
        root = self._resolve_workspace_root(deliverables)

        def _validate_under_workspace(candidate: Path) -> Path:
            resolved = candidate.resolve()
            try:
                resolved.relative_to(root)
            except ValueError as exc:
                raise ValueError("artifact path is outside workspace") from exc
            if not resolved.exists() or not resolved.is_file():
                raise ValueError(f"artifact file not found: {resolved}")
            return resolved

        if artifact_path:
            raw = str(artifact_path).strip()
            candidate = Path(raw).expanduser()
            if not candidate.is_absolute():
                candidate = root / raw
            return _validate_under_workspace(candidate)

        primary = deliverables.get("primaryArtifact")
        if isinstance(primary, str) and primary.strip():
            return _validate_under_workspace(Path(primary))

        files = deliverables.get("files", [])
        if isinstance(files, list):
            for item in files:
                if not isinstance(item, dict):
                    continue
                absolute_path = item.get("absolutePath")
                if isinstance(absolute_path, str) and absolute_path.strip():
                    return _validate_under_workspace(Path(absolute_path))

        raise ValueError("no deliverable file available")

    def _open_path_in_system(self, target: Path, reveal_file: bool = False) -> None:
        if sys.platform.startswith("win"):
            if reveal_file and target.is_file():
                subprocess.Popen(["explorer", "/select,", str(target)], shell=False)
                return
            os.startfile(str(target))  # type: ignore[attr-defined]
            return

        if sys.platform == "darwin":
            if reveal_file and target.is_file():
                subprocess.Popen(["open", "-R", str(target)], shell=False)
                return
            subprocess.Popen(["open", str(target)], shell=False)
            return

        open_target = target.parent if reveal_file and target.is_file() else target
        subprocess.Popen(["xdg-open", str(open_target)], shell=False)

    def open_deliverable(
        self,
        *,
        task_id: str,
        mode: str = "file",
        artifact_path: str | None = None,
    ) -> dict[str, Any]:
        with self.session_factory() as db:
            task = db.get(Task, task_id)
            if not task:
                raise ValueError(f"task not found: {task_id}")
            deliverables = self._extract_deliverables_payload(task)

        normalized_mode = mode.strip().lower()
        if normalized_mode not in {"file", "folder"}:
            raise ValueError("mode must be 'file' or 'folder'")

        if normalized_mode == "folder":
            root = self._resolve_workspace_root(deliverables)
            self._open_path_in_system(root)
            return {
                "taskId": task_id,
                "mode": "folder",
                "openedPath": str(root),
            }

        target = self._resolve_deliverable_file(deliverables=deliverables, artifact_path=artifact_path)
        self._open_path_in_system(target, reveal_file=True)
        return {
            "taskId": task_id,
            "mode": "file",
            "openedPath": str(target),
        }

    def resolve_deliverable_download(
        self,
        *,
        task_id: str,
        artifact_path: str | None = None,
    ) -> str:
        with self.session_factory() as db:
            task = db.get(Task, task_id)
            if not task:
                raise ValueError(f"task not found: {task_id}")
            deliverables = self._extract_deliverables_payload(task)
        target = self._resolve_deliverable_file(deliverables=deliverables, artifact_path=artifact_path)
        return str(target)

    def build_deliverable_archive(self, *, task_id: str) -> str:
        if self.artifact_store is None:
            raise ValueError("artifact store is unavailable")
        with self.session_factory() as db:
            task = db.get(Task, task_id)
            if not task:
                raise ValueError(f"task not found: {task_id}")
            deliverables = self._extract_deliverables_payload(task)

        workspace_root = self._resolve_workspace_root(deliverables)
        files = deliverables.get("files", [])
        if not isinstance(files, list):
            files = []
        return self.artifact_store.build_deliverable_archive(
            task_id=task_id,
            workspace_path=str(workspace_root),
            files=[item for item in files if isinstance(item, dict)],
        )

    def get_task(self, task_id: str) -> Task:
        with self.session_factory() as db:
            task = db.get(Task, task_id)
            if not task:
                raise ValueError(f"task not found: {task_id}")
            return task

    def list_skills(self) -> list[Skill]:
        with self.session_factory() as db:
            return db.query(Skill).order_by(Skill.id.asc()).all()

    def create_skill_from_factory(
        self,
        *,
        skill_id: str,
        name: str,
        description: str,
        base_strategy: str = "tool_first",
        mcp_connectors: list[str] | None = None,
        io_schema: dict[str, Any] | None = None,
        permissions: dict[str, Any] | None = None,
        cost_budget: dict[str, Any] | None = None,
        created_by: str = "skills-factory",
    ) -> Skill:
        normalized_id = skill_id.strip().lower().replace(" ", "_")
        if not normalized_id:
            raise ValueError("skill_id is required")
        if not re.fullmatch(r"[a-z0-9_\\-]{3,64}", normalized_id):
            raise ValueError("skill_id must match [a-z0-9_-]{3,64}")
        if not name.strip():
            raise ValueError("name is required")

        connectors = []
        for item in mcp_connectors or []:
            text = str(item).strip()
            if text:
                connectors.append(text[:120])
        connectors = connectors[:20]

        with self.session_factory() as db:
            existing = db.get(Skill, normalized_id)
            if existing:
                raise ValueError(f"skill already exists: {normalized_id}")

            skill = Skill(
                id=normalized_id,
                name=name.strip()[:120],
                description=description.strip()[:1200],
                version=1,
                io_schema=io_schema or {"input": ["goal", "context"], "output": ["result"]},
                permissions=permissions or {"network": True, "filesystem": "read_write"},
                cost_budget=cost_budget or {"maxTokens": 8000},
                config={
                    "strategy": base_strategy,
                    "factory": {
                        "createdBy": created_by,
                        "createdAt": datetime.now(timezone.utc).isoformat(),
                        "mcpConnectors": connectors,
                    },
                },
            )
            db.add(skill)
            db.flush()

            self._publish(
                db,
                EventTopic.skill_factory_created,
                {
                    "skillId": skill.id,
                    "name": skill.name,
                    "strategy": base_strategy,
                    "mcpConnectors": connectors,
                },
            )
            db.commit()
            db.refresh(skill)
            return skill

    def get_candidate(self, skill_id: str, candidate_id: str) -> SkillCandidate:
        with self.session_factory() as db:
            candidate = db.get(SkillCandidate, candidate_id)
            if not candidate:
                raise ValueError(f"candidate not found: {candidate_id}")
            if candidate.skill_id != skill_id:
                raise ValueError("candidate-skill mismatch")
            return candidate

    def create_candidate(
        self,
        skill_id: str,
        delta: SkillDelta,
    ) -> SkillCandidate:
        with self.session_factory() as db:
            skill = db.get(Skill, skill_id)
            if not skill:
                raise ValueError(f"skill not found: {skill_id}")
            self._validate_patch_permissions(skill, delta.patch)
            shadow_score = self._estimate_shadow_score_from_delta(delta)

            candidate = SkillCandidate(
                skill_id=skill_id,
                proposed_delta={
                    "targetSkill": delta.target_skill,
                    "changeType": delta.change_type,
                    "patch": delta.patch,
                },
                evidence=delta.evidence,
                shadow_score=shadow_score,
                canary_score=None,
                status=CandidateStatus.proposed.value,
            )
            db.add(candidate)
            db.flush()
            self._audit_candidate_status(
                db=db,
                candidate=candidate,
                from_status=None,
                to_status=candidate.status,
                actor="worm-manual",
                decision="proposed",
                reason="manual candidate created",
                context={"skillId": skill_id},
            )
            self._publish(
                db,
                EventTopic.worm_proposed,
                {
                    "candidateId": candidate.id,
                    "skillId": skill_id,
                    "shadowScore": shadow_score,
                    "canaryScore": None,
                },
            )
            db.commit()
            db.refresh(candidate)
            self._signal_life("feedback.submitted")
            return candidate

    def evaluate_shadow_replay(
        self,
        *,
        skill_id: str,
        candidate_id: str,
        sample_size: int = 50,
    ) -> tuple[SkillCandidate, dict[str, Any]]:
        with self.session_factory() as db:
            skill = db.get(Skill, skill_id)
            candidate = db.get(SkillCandidate, candidate_id)
            if not skill:
                raise ValueError(f"skill not found: {skill_id}")
            if not candidate:
                raise ValueError(f"candidate not found: {candidate_id}")
            if candidate.skill_id != skill_id:
                raise ValueError("candidate-skill mismatch")
            bounded_sample_size = max(1, min(sample_size, 500))

            tasks = (
                db.query(Task)
                .filter(Task.status == TaskStatus.completed.value)
                .order_by(desc(Task.created_at))
                .limit(bounded_sample_size)
                .all()
            )
            task_ids = [task.id for task in tasks]
            feedback_entries: list[TaskFeedback] = []
            if task_ids:
                feedback_entries = (
                    db.query(TaskFeedback)
                    .filter(TaskFeedback.task_id.in_(task_ids))
                    .order_by(desc(TaskFeedback.created_at))
                    .all()
                )
            feedback_by_task: dict[str, TaskFeedback] = {}
            for fb in feedback_entries:
                if fb.task_id not in feedback_by_task:
                    feedback_by_task[fb.task_id] = fb

            patch = candidate.proposed_delta.get("patch", {})
            replay = self.shadow_replay.estimate(
                patch=patch,
                tasks=tasks,
                feedback_by_task=feedback_by_task,
            )
            candidate.shadow_score = float(replay["shadowScore"])
            evidence = dict(candidate.evidence or {})
            evidence["shadowReplay"] = replay
            candidate.evidence = evidence
            self._publish(
                db,
                EventTopic.shadow_evaluated,
                {
                    "candidateId": candidate.id,
                    "skillId": skill_id,
                    "sampleSize": replay["sampleSize"],
                    "shadowScore": replay["shadowScore"],
                    "improvementRatio": replay["improvementRatio"],
                },
            )
            db.commit()
            db.refresh(candidate)
            return candidate, replay

    def submit_feedback(self, task_id: str, packet: FeedbackPacket, created_by: str = "anonymous") -> SkillCandidate:
        with self.session_factory() as db:
            task = db.get(Task, task_id)
            if not task:
                raise ValueError(f"task not found: {task_id}")

            feedback = TaskFeedback(
                task_id=task_id,
                explicit_score=packet.explicit_score,
                corrections=packet.corrections,
                implicit_signals=packet.implicit_signals,
                created_by=created_by,
            )
            db.add(feedback)
            db.flush()
            self._publish(
                db,
                EventTopic.feedback_received,
                {"taskId": task_id, "feedbackId": feedback.id},
            )
            self._update_canary_candidate_metrics(db=db, task=task, packet=packet)
            rewarded_pheromones = self._reward_task_pheromones(db=db, task=task, packet=packet)

            base_skill = db.query(Skill).filter(Skill.status == "active").order_by(Skill.updated_at.desc()).first()
            if not base_skill:
                raise ValueError("no active skill found")

            derived = self.worm.derive_skill_delta(task, feedback, base_skill)
            candidate = SkillCandidate(
                skill_id=base_skill.id,
                proposed_delta={
                    "targetSkill": base_skill.id,
                    "changeType": derived["changeType"],
                    "patch": derived["patch"],
                },
                evidence=derived["evidence"],
                shadow_score=float(derived["shadowScore"]),
                canary_score=float(derived["canaryScore"]),
                status=CandidateStatus.proposed.value,
            )
            db.add(candidate)
            db.flush()
            candidate.evidence = {
                **dict(candidate.evidence or {}),
                "scoutPheromoneRewarded": rewarded_pheromones,
            }
            self._audit_candidate_status(
                db=db,
                candidate=candidate,
                from_status=None,
                to_status=candidate.status,
                actor="worm-feedback",
                decision="proposed",
                reason="derived from task feedback",
                context={"taskId": task.id, "feedbackId": feedback.id},
            )
            if self.artifact_store is not None:
                bundle_path = self.artifact_store.write_replay_bundle(
                    task_id=task.id,
                    candidate_id=candidate.id,
                    payload={
                        "taskId": task.id,
                        "skillId": base_skill.id,
                        "feedback": packet.model_dump(),
                        "candidate": {
                            "shadowScore": candidate.shadow_score,
                            "canaryScore": candidate.canary_score,
                            "delta": candidate.proposed_delta,
                        },
                    },
                )
                candidate.evidence = {**candidate.evidence, "replayBundlePath": bundle_path}
            self._publish(
                db,
                EventTopic.worm_proposed,
                {
                    "candidateId": candidate.id,
                    "skillId": candidate.skill_id,
                    "shadowScore": candidate.shadow_score,
                    "canaryScore": candidate.canary_score,
                    "canarySliceRatio": self.settings.canary_slice_ratio,
                    "scoutPheromoneRewarded": rewarded_pheromones,
                },
            )
            db.commit()
            db.refresh(candidate)
            return candidate

    def promote_candidate(self, skill_id: str, candidate_id: str, approved_by: str = "queen") -> tuple[SkillCandidate, str, str]:
        with self.session_factory() as db:
            skill = db.get(Skill, skill_id)
            candidate = db.get(SkillCandidate, candidate_id)
            if not skill:
                raise ValueError(f"skill not found: {skill_id}")
            if not candidate:
                raise ValueError(f"candidate not found: {candidate_id}")
            if candidate.skill_id != skill_id:
                raise ValueError("candidate-skill mismatch")
            if candidate.status in {
                CandidateStatus.promoted.value,
                CandidateStatus.rejected.value,
                CandidateStatus.rolled_back.value,
            }:
                raise ValueError(f"candidate status is terminal: {candidate.status}")
            if candidate.status not in {
                CandidateStatus.proposed.value,
                CandidateStatus.validated.value,
            }:
                raise ValueError(f"candidate status cannot be promoted: {candidate.status}")

            if candidate.status == CandidateStatus.validated.value:
                stats = dict((candidate.evidence or {}).get("canaryStats") or {})
                feedback_count = int(stats.get("feedbackCount", 0))
                if feedback_count < self.settings.canary_min_feedback_count:
                    raise ValueError(
                        f"insufficient canary feedback: {feedback_count} < {self.settings.canary_min_feedback_count}"
                    )

            decision, reason = self.queen.decide(candidate)
            previous_status = candidate.status

            if decision == "promoted":
                previous_config = dict(skill.config or {})
                release_history = list(previous_config.get("releaseHistory") or [])
                config_snapshot = {
                    key: deepcopy(value)
                    for key, value in previous_config.items()
                    if key != "releaseHistory"
                }
                release_history.append(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "version": skill.version,
                        "candidateId": candidate.id,
                        "approvedBy": approved_by,
                        "config": config_snapshot,
                    }
                )
                patch = candidate.proposed_delta.get("patch", {})
                merged_config = self._apply_patch_to_skill_config(config_snapshot, patch)
                skill.version += 1
                skill.config = {
                    **merged_config,
                    "lastDelta": candidate.proposed_delta,
                    "lastPromotionBy": approved_by,
                    "canarySliceRatio": self.settings.canary_slice_ratio,
                    "releaseHistory": release_history[-30:],
                }
                candidate.status = CandidateStatus.promoted.value
                self._audit_candidate_status(
                    db=db,
                    candidate=candidate,
                    from_status=previous_status,
                    to_status=candidate.status,
                    actor=approved_by,
                    decision=decision,
                    reason=reason,
                    context={"skillVersion": skill.version},
                )
                self._publish(
                    db,
                    EventTopic.queen_promoted,
                    {
                        "candidateId": candidate.id,
                        "skillId": skill_id,
                        "version": skill.version,
                        "canarySliceRatio": self.settings.canary_slice_ratio,
                        "reason": reason,
                    },
                )
            elif decision == "rolled_back":
                candidate.status = CandidateStatus.rolled_back.value
                self._audit_candidate_status(
                    db=db,
                    candidate=candidate,
                    from_status=previous_status,
                    to_status=candidate.status,
                    actor=approved_by,
                    decision=decision,
                    reason=reason,
                )
                self._publish(
                    db,
                    EventTopic.queen_rolled_back,
                    {
                        "candidateId": candidate.id,
                        "skillId": skill_id,
                        "reason": reason,
                    },
                )
            elif decision == "validated":
                candidate.status = CandidateStatus.validated.value
                self._audit_candidate_status(
                    db=db,
                    candidate=candidate,
                    from_status=previous_status,
                    to_status=candidate.status,
                    actor=approved_by,
                    decision=decision,
                    reason=reason,
                )
            else:
                candidate.status = CandidateStatus.rejected.value
                self._audit_candidate_status(
                    db=db,
                    candidate=candidate,
                    from_status=previous_status,
                    to_status=candidate.status,
                    actor=approved_by,
                    decision=decision,
                    reason=reason,
                )

            db.commit()
            db.refresh(candidate)
            self._signal_life(f"candidate.{decision}")
            return candidate, decision, reason

    def rollback_skill(self, skill_id: str, reason: str, requested_by: str = "queen") -> Skill:
        with self.session_factory() as db:
            skill = db.get(Skill, skill_id)
            if not skill:
                raise ValueError(f"skill not found: {skill_id}")
            current_config = dict(skill.config or {})
            release_history = list(current_config.get("releaseHistory") or [])
            if not release_history:
                raise ValueError("no rollback snapshot available")

            snapshot = dict(release_history[-1] or {})
            remaining_history = release_history[:-1]
            snapshot_config = dict(snapshot.get("config") or {})
            restored_version = int(snapshot.get("version", skill.version))
            restored_candidate_id = snapshot.get("candidateId")

            restored_config = {
                **snapshot_config,
                "rollback": {
                    "reason": reason,
                    "requestedBy": requested_by,
                    "restoredFromCandidateId": restored_candidate_id,
                    "restoredVersion": restored_version,
                },
            }
            if remaining_history:
                restored_config["releaseHistory"] = remaining_history

            skill.version = restored_version
            skill.config = restored_config

            if restored_candidate_id:
                candidate = db.get(SkillCandidate, restored_candidate_id)
                if candidate and candidate.skill_id == skill_id:
                    previous_status = candidate.status
                    candidate.status = CandidateStatus.rolled_back.value
                    self._audit_candidate_status(
                        db=db,
                        candidate=candidate,
                        from_status=previous_status,
                        to_status=candidate.status,
                        actor=requested_by,
                        decision="rolled_back",
                        reason=reason,
                        context={
                            "restoredVersion": restored_version,
                            "skillId": skill_id,
                        },
                    )
            self._publish(
                db,
                EventTopic.queen_rolled_back,
                {
                    "skillId": skill_id,
                    "reason": reason,
                    "requestedBy": requested_by,
                    "restoredVersion": restored_version,
                    "restoredFromCandidateId": restored_candidate_id,
                },
            )
            db.commit()
            db.refresh(skill)
            self._signal_life("skill.rollback")
            return skill

    def list_scout_pheromones(
        self,
        *,
        limit: int = 100,
        intent_cluster: str | None = None,
        only_active: bool = True,
    ) -> list[ScoutPheromone]:
        bounded_limit = max(1, min(limit, 500))
        now = datetime.now(timezone.utc)
        with self.session_factory() as db:
            query = db.query(ScoutPheromone)
            if intent_cluster:
                query = query.filter(ScoutPheromone.intent_cluster == intent_cluster)
            if only_active:
                query = query.filter(ScoutPheromone.expires_at > now, ScoutPheromone.strength > 0)
            return query.order_by(desc(ScoutPheromone.strength), desc(ScoutPheromone.updated_at)).limit(bounded_limit).all()

    def run_scout_patrol(self, *, sample_size: int | None = None) -> dict[str, Any]:
        patrol_size = sample_size if sample_size is not None else self.settings.scout_patrol_sample_size
        bounded_sample_size = max(1, min(int(patrol_size), 200))

        with self.session_factory() as db:
            evaporated, expired = self._evaporate_pheromones(db)

            tasks = (
                db.query(Task)
                .order_by(desc(Task.updated_at))
                .limit(bounded_sample_size)
                .all()
            )
            task_ids = [task.id for task in tasks]
            feedback_by_task: dict[str, TaskFeedback] = {}
            if task_ids:
                entries = (
                    db.query(TaskFeedback)
                    .filter(TaskFeedback.task_id.in_(task_ids))
                    .order_by(desc(TaskFeedback.created_at))
                    .all()
                )
                for entry in entries:
                    if entry.task_id not in feedback_by_task:
                        feedback_by_task[entry.task_id] = entry

            sampled_tasks = 0
            touched_clusters: set[str] = set()
            deposited_total = 0
            for task in tasks:
                refs = list(task.context_refs or [])
                if not refs:
                    continue

                signals: list[dict[str, Any]] = []
                for route in refs[:4]:
                    route_text = str(route)
                    source = "context"
                    if "://" in route_text:
                        source = route_text.split("://", 1)[0].strip().lower() or "context"
                    signals.append(
                        {
                            "source": source,
                            "route": route_text[:300],
                            "novelty": 0.52,
                            "reliability": 0.68,
                            "cost": 0.08,
                            "notes": "patrol sampled from historical task context",
                        }
                    )

                latest_feedback = feedback_by_task.get(task.id)
                if latest_feedback and latest_feedback.corrections:
                    correction_text = str(latest_feedback.corrections).strip()
                    if correction_text:
                        signals.append(
                            {
                                "source": "feedback",
                                "route": f"feedback://{task.id}",
                                "novelty": 0.63,
                                "reliability": 0.72,
                                "cost": 0.06,
                                "notes": correction_text[:280],
                            }
                        )

                if not signals:
                    continue

                cluster = self._normalize_intent_cluster(task.goal)
                ids = self._deposit_scout_pheromones(
                    db=db,
                    intent_cluster=cluster,
                    scout_report={"signals": signals},
                )
                if ids:
                    sampled_tasks += 1
                    touched_clusters.add(cluster)
                    deposited_total += len(ids)

            summary = {
                "sampleSize": bounded_sample_size,
                "sampledTasks": sampled_tasks,
                "touchedClusters": sorted(touched_clusters),
                "deposited": deposited_total,
                "evaporated": evaporated,
                "expired": expired,
            }
            self._publish(db, EventTopic.scout_patrolled, summary)
            db.commit()
            self._signal_life("scout.patrolled")
            return summary

    def list_events(self, limit: int = 100, topic: str | None = None) -> list[EvolutionEvent]:
        with self.session_factory() as db:
            query = db.query(EvolutionEvent)
            if topic:
                query = query.filter(EvolutionEvent.topic == topic)
            return query.order_by(EvolutionEvent.created_at.desc()).limit(limit).all()

    def build_evolution_telemetry(self, *, window_minutes: int = 180) -> dict[str, Any]:
        bounded_window = max(30, min(int(window_minutes), 1440))
        now = datetime.now(timezone.utc)
        start_24h = now - timedelta(hours=24)
        start_60m = now - timedelta(minutes=60)
        start_5m = now - timedelta(minutes=5)

        bucket_minutes = 10 if bounded_window <= 240 else 30
        bucket_count = max(1, min(48, bounded_window // bucket_minutes))
        timeline_start = now - timedelta(minutes=bucket_count * bucket_minutes)
        bucket_seconds = bucket_minutes * 60

        with self.session_factory() as db:
            events = (
                db.query(EvolutionEvent)
                .filter(EvolutionEvent.created_at >= timeline_start)
                .order_by(EvolutionEvent.created_at.asc())
                .all()
            )
            tasks_24h = db.query(Task).filter(Task.created_at >= start_24h).all()
            candidates = db.query(SkillCandidate).all()
            active_pheromones = (
                db.query(ScoutPheromone)
                .filter(ScoutPheromone.expires_at > now, ScoutPheromone.strength > 0)
                .count()
            )

        def _is_since(evt: EvolutionEvent, threshold: datetime) -> bool:
            return self._to_aware_utc(evt.created_at) >= threshold

        events_60m = [evt for evt in events if _is_since(evt, start_60m)]
        events_5m = [evt for evt in events if _is_since(evt, start_5m)]

        proposals_60m = sum(1 for evt in events_60m if evt.topic == EventTopic.worm_proposed)
        promotions_60m = sum(1 for evt in events_60m if evt.topic == EventTopic.queen_promoted)
        rollbacks_60m = sum(1 for evt in events_60m if evt.topic == EventTopic.queen_rolled_back)
        patrols_60m = sum(1 for evt in events_60m if evt.topic == EventTopic.scout_patrolled)

        def _count_prefix(prefix: str) -> int:
            return sum(1 for evt in events_60m if evt.topic.startswith(prefix))

        scout_events_60m = _count_prefix("scout.")
        worker_events_60m = _count_prefix("worker.") + _count_prefix("canary.") + _count_prefix("shadow.")
        worm_events_60m = _count_prefix("worm.") + _count_prefix("skill.")
        queen_events_60m = _count_prefix("queen.")
        feedback_events_60m = _count_prefix("feedback.")
        system_events_60m = max(
            0,
            len(events_60m)
            - scout_events_60m
            - worker_events_60m
            - worm_events_60m
            - queen_events_60m
            - feedback_events_60m,
        )

        status_counts = {
            CandidateStatus.proposed.value: 0,
            CandidateStatus.validated.value: 0,
            CandidateStatus.promoted.value: 0,
            CandidateStatus.rejected.value: 0,
            CandidateStatus.rolled_back.value: 0,
        }
        for candidate in candidates:
            if candidate.status in status_counts:
                status_counts[candidate.status] += 1

        total_candidates = len(candidates)
        validation_ratio = (
            (status_counts[CandidateStatus.validated.value] + status_counts[CandidateStatus.promoted.value])
            / max(1, total_candidates)
        )
        promotion_ratio = status_counts[CandidateStatus.promoted.value] / max(1, total_candidates)
        rollback_ratio = status_counts[CandidateStatus.rolled_back.value] / max(
            1,
            status_counts[CandidateStatus.promoted.value] + status_counts[CandidateStatus.rolled_back.value],
        )

        completed_24h = sum(1 for task in tasks_24h if task.status == TaskStatus.completed.value)
        failed_24h = sum(1 for task in tasks_24h if task.status == TaskStatus.failed.value)
        considered_24h = max(1, completed_24h + failed_24h)
        success_rate_24h = completed_24h / considered_24h

        durations: list[float] = []
        for task in tasks_24h:
            metrics = task.metrics if isinstance(task.metrics, dict) else {}
            duration = metrics.get("durationMs")
            if duration is None:
                continue
            try:
                parsed = float(duration)
            except (TypeError, ValueError):
                continue
            if parsed > 0:
                durations.append(parsed)
        avg_duration_ms_24h = sum(durations) / len(durations) if durations else 0.0
        tasks_per_hour_24h = len(tasks_24h) / 24.0

        decision_minutes: list[float] = []
        decision_statuses = {
            CandidateStatus.promoted.value,
            CandidateStatus.rejected.value,
            CandidateStatus.rolled_back.value,
        }
        for candidate in candidates:
            if candidate.status not in decision_statuses:
                continue
            candidate_updated = self._to_aware_utc(candidate.updated_at)
            if candidate_updated < start_24h:
                continue
            candidate_created = self._to_aware_utc(candidate.created_at)
            delta_minutes = (candidate_updated - candidate_created).total_seconds() / 60.0
            if delta_minutes >= 0:
                decision_minutes.append(delta_minutes)
        avg_decision_minutes_24h = sum(decision_minutes) / len(decision_minutes) if decision_minutes else 0.0

        events_per_minute_5m = len(events_5m) / 5.0
        progress_score = self._clamp(
            success_rate_24h * 45.0
            + min(20.0, promotion_ratio * 100.0 * 0.3 + validation_ratio * 100.0 * 0.1)
            + min(20.0, events_per_minute_5m * 12.0)
            + max(0.0, 15.0 - rollback_ratio * 30.0),
            0.0,
            100.0,
        )
        velocity_score = self._clamp(
            events_per_minute_5m * 40.0
            + proposals_60m * 1.2
            + promotions_60m * 4.0
            - rollbacks_60m * 3.0,
            0.0,
            100.0,
        )

        timeline = []
        for idx in range(bucket_count):
            bucket_start = timeline_start + timedelta(minutes=idx * bucket_minutes)
            timeline.append(
                {
                    "bucket": bucket_start.isoformat(),
                    "events": 0,
                    "promotions": 0,
                    "proposals": 0,
                }
            )

        for evt in events:
            event_time = self._to_aware_utc(evt.created_at)
            if event_time < timeline_start:
                continue
            delta_seconds = (event_time - timeline_start).total_seconds()
            idx = int(delta_seconds // bucket_seconds)
            idx = max(0, min(bucket_count - 1, idx))
            timeline[idx]["events"] += 1
            if evt.topic == EventTopic.queen_promoted:
                timeline[idx]["promotions"] += 1
            if evt.topic == EventTopic.worm_proposed:
                timeline[idx]["proposals"] += 1

        return {
            "generated_at": now,
            "window_minutes": bounded_window,
            "active_pheromones": int(active_pheromones),
            "roles": {
                "scout_events_60m": scout_events_60m,
                "worker_events_60m": worker_events_60m,
                "worm_events_60m": worm_events_60m,
                "queen_events_60m": queen_events_60m,
                "feedback_events_60m": feedback_events_60m,
                "system_events_60m": system_events_60m,
            },
            "funnel": {
                "proposed": status_counts[CandidateStatus.proposed.value],
                "validated": status_counts[CandidateStatus.validated.value],
                "promoted": status_counts[CandidateStatus.promoted.value],
                "rejected": status_counts[CandidateStatus.rejected.value],
                "rolled_back": status_counts[CandidateStatus.rolled_back.value],
                "total_candidates": total_candidates,
                "validation_ratio": round(validation_ratio, 4),
                "promotion_ratio": round(promotion_ratio, 4),
                "rollback_ratio": round(rollback_ratio, 4),
            },
            "tasks": {
                "total_24h": len(tasks_24h),
                "completed_24h": completed_24h,
                "failed_24h": failed_24h,
                "success_rate_24h": round(success_rate_24h, 4),
                "avg_duration_ms_24h": round(avg_duration_ms_24h, 2),
                "tasks_per_hour_24h": round(tasks_per_hour_24h, 3),
            },
            "speed": {
                "events_last_5m": len(events_5m),
                "events_per_minute_5m": round(events_per_minute_5m, 3),
                "proposals_last_60m": proposals_60m,
                "promotions_last_60m": promotions_60m,
                "rollbacks_last_60m": rollbacks_60m,
                "patrols_last_60m": patrols_60m,
                "avg_decision_minutes_24h": round(avg_decision_minutes_24h, 3),
                "progress_score": round(progress_score, 2),
                "velocity_score": round(velocity_score, 2),
            },
            "timeline": timeline,
        }

    def get_token_statistics(self, *, limit: int = 300) -> dict[str, Any]:
        bounded_limit = max(1, min(limit, 5000))
        with self.session_factory() as db:
            tasks = (
                db.query(Task)
                .filter(Task.metrics.isnot(None))
                .order_by(desc(Task.created_at))
                .limit(bounded_limit)
                .all()
            )

        total_tokens = 0
        prompt_tokens_total = 0
        completion_tokens_total = 0
        by_model: dict[str, dict[str, Any]] = {}
        recent_tasks: list[dict[str, Any]] = []

        for task in tasks:
            metrics = task.metrics if isinstance(task.metrics, dict) else {}
            prompt_tokens = int(metrics.get("promptTokens", 0) or 0)
            completion_tokens = int(metrics.get("completionTokens", 0) or 0)
            total = int(metrics.get("totalTokens", metrics.get("tokenEstimate", 0)) or 0)
            if total <= 0:
                total = prompt_tokens + completion_tokens

            payload = task.result_payload if isinstance(task.result_payload, dict) else {}
            llm_meta = payload.get("llmMeta") if isinstance(payload.get("llmMeta"), dict) else {}
            provider = str(llm_meta.get("provider", "unknown"))
            model = str(llm_meta.get("model", "unknown"))
            key = f"{provider}:{model}"

            row = by_model.setdefault(
                key,
                {
                    "provider": provider,
                    "model": model,
                    "taskCount": 0,
                    "totalTokens": 0,
                    "promptTokens": 0,
                    "completionTokens": 0,
                    "averageTokens": 0.0,
                },
            )
            row["taskCount"] += 1
            row["totalTokens"] += total
            row["promptTokens"] += prompt_tokens
            row["completionTokens"] += completion_tokens

            total_tokens += total
            prompt_tokens_total += prompt_tokens
            completion_tokens_total += completion_tokens
            recent_tasks.append(
                {
                    "taskId": task.id,
                    "goal": task.goal,
                    "provider": provider,
                    "model": model,
                    "totalTokens": total,
                    "promptTokens": prompt_tokens,
                    "completionTokens": completion_tokens,
                    "createdAt": task.created_at,
                }
            )

        by_model_list = list(by_model.values())
        for row in by_model_list:
            if row["taskCount"] > 0:
                row["averageTokens"] = round(row["totalTokens"] / row["taskCount"], 2)
        by_model_list.sort(key=lambda item: item["totalTokens"], reverse=True)

        average_tokens = round(total_tokens / len(tasks), 2) if tasks else 0.0
        return {
            "sampleSize": bounded_limit,
            "totalTasks": len(tasks),
            "totalTokens": total_tokens,
            "promptTokens": prompt_tokens_total,
            "completionTokens": completion_tokens_total,
            "averageTokensPerTask": average_tokens,
            "byModel": by_model_list,
            "recentTasks": recent_tasks[:50],
        }

    def list_candidate_audits(
        self,
        *,
        limit: int = 100,
        candidate_id: str | None = None,
        skill_id: str | None = None,
    ) -> list[CandidateStatusAudit]:
        with self.session_factory() as db:
            query = db.query(CandidateStatusAudit)
            if candidate_id:
                query = query.filter(CandidateStatusAudit.candidate_id == candidate_id)
            if skill_id:
                query = query.filter(CandidateStatusAudit.skill_id == skill_id)
            return query.order_by(CandidateStatusAudit.created_at.desc()).limit(max(1, limit)).all()

    def build_hardening_report(self) -> dict[str, Any]:
        required_topics = {
            EventTopic.scout_reported,
            EventTopic.worker_planned,
            EventTopic.worker_completed,
            EventTopic.feedback_received,
            EventTopic.worm_proposed,
        }
        event_bus_backend = type(self.event_bus).__name__
        api_key_enabled = bool(self.settings.control_plane_api_key)

        with self.session_factory() as db:
            skills = db.query(Skill).all()
            candidates = db.query(SkillCandidate).all()
            recent_events = db.query(EvolutionEvent).order_by(desc(EvolutionEvent.created_at)).limit(200).all()
            recent_audits = (
                db.query(CandidateStatusAudit).order_by(desc(CandidateStatusAudit.created_at)).limit(200).all()
            )

        missing_topics = sorted(required_topics - {evt.topic for evt in recent_events})
        snapshot_ready_skills = 0
        for skill in skills:
            release_history = list((skill.config or {}).get("releaseHistory") or [])
            if release_history:
                snapshot_ready_skills += 1

        waiting_validated = 0
        for candidate in candidates:
            if candidate.status != CandidateStatus.validated.value:
                continue
            stats = dict((candidate.evidence or {}).get("canaryStats") or {})
            feedback_count = int(stats.get("feedbackCount", 0))
            if feedback_count < self.settings.canary_min_feedback_count:
                waiting_validated += 1

        checks: list[dict[str, str]] = []
        checks.append(
            {
                "id": "api_key_guard",
                "level": "pass" if api_key_enabled else "warn",
                "message": (
                    "write endpoints protected by api key"
                    if api_key_enabled
                    else "api key is disabled; write endpoints are open in current environment"
                ),
            }
        )
        checks.append(
            {
                "id": "event_bus_backend",
                "level": "pass" if event_bus_backend != "InMemoryEventBus" else "warn",
                "message": f"event bus backend: {event_bus_backend}",
            }
        )
        checks.append(
            {
                "id": "rollback_snapshots",
                "level": "pass" if snapshot_ready_skills > 0 else "warn",
                "message": (
                    f"{snapshot_ready_skills}/{len(skills)} skills have rollback snapshots"
                    if skills
                    else "no skills registered"
                ),
            }
        )
        checks.append(
            {
                "id": "candidate_audit_trail",
                "level": "pass" if len(recent_audits) > 0 else "warn",
                "message": (
                    f"{len(recent_audits)} candidate status audits found (last 200)"
                    if recent_audits
                    else "no candidate status audits found yet"
                ),
            }
        )
        checks.append(
            {
                "id": "topic_coverage",
                "level": "pass" if not missing_topics else "warn",
                "message": (
                    "all required evolution topics observed recently"
                    if not missing_topics
                    else f"missing topics: {', '.join(missing_topics)}"
                ),
            }
        )

        overall = "pass"
        if any(item["level"] == "warn" for item in checks):
            overall = "warn"

        return {
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "overall": overall,
            "summary": {
                "skillCount": len(skills),
                "candidateCount": len(candidates),
                "recentEventCount": len(recent_events),
                "recentAuditCount": len(recent_audits),
                "waitingValidatedCandidates": waiting_validated,
                "eventBusBackend": event_bus_backend,
                "apiKeyEnabled": api_key_enabled,
            },
            "checks": checks,
            "missingTopics": missing_topics,
        }

    def auto_promote_candidates(
        self,
        *,
        limit: int = 20,
        approved_by: str = "queen-auto",
    ) -> list[dict[str, Any]]:
        with self.session_factory() as db:
            rows = (
                db.query(SkillCandidate.id, SkillCandidate.skill_id)
                .filter(
                    SkillCandidate.status.in_(
                        [
                            CandidateStatus.proposed.value,
                            CandidateStatus.validated.value,
                        ]
                    )
                )
                .order_by(desc(SkillCandidate.updated_at))
                .limit(max(1, limit))
                .all()
            )

        outcomes: list[dict[str, Any]] = []
        for candidate_id, skill_id in rows:
            try:
                with self.session_factory() as db:
                    candidate_state = db.get(SkillCandidate, candidate_id)
                    if candidate_state is None:
                        outcomes.append(
                            {
                                "candidateId": candidate_id,
                                "skillId": skill_id,
                                "status": "missing",
                                "previousStatus": None,
                                "decision": "skipped",
                                "reason": "candidate not found",
                            }
                        )
                        continue
                    previous_status = candidate_state.status
                    if candidate_state.status == CandidateStatus.validated.value:
                        stats = dict((candidate_state.evidence or {}).get("canaryStats") or {})
                        feedback_count = int(stats.get("feedbackCount", 0))
                        if feedback_count < self.settings.canary_min_feedback_count:
                            outcomes.append(
                                {
                                    "candidateId": candidate_id,
                                    "skillId": skill_id,
                                    "status": candidate_state.status,
                                    "previousStatus": previous_status,
                                    "decision": "skipped",
                                    "reason": (
                                        f"waiting canary feedback: {feedback_count}"
                                        f" < {self.settings.canary_min_feedback_count}"
                                    ),
                                }
                            )
                            continue

                candidate, decision, reason = self.promote_candidate(
                    skill_id=skill_id,
                    candidate_id=candidate_id,
                    approved_by=approved_by,
                )
                outcomes.append(
                    {
                        "candidateId": candidate.id,
                        "skillId": skill_id,
                        "status": candidate.status,
                        "previousStatus": previous_status,
                        "decision": decision,
                        "reason": reason,
                    }
                )
            except ValueError as exc:
                outcomes.append(
                    {
                        "candidateId": candidate_id,
                        "skillId": skill_id,
                        "status": "skipped",
                        "previousStatus": None,
                        "decision": "skipped",
                        "reason": str(exc),
                    }
                )
        return outcomes
