from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from difflib import SequenceMatcher
import json
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.models.evolution import CandidateStatusAudit, EvolutionEvent
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

    def _publish(self, db: Session, topic: str, payload: dict[str, Any]) -> None:
        self.event_bus.publish(topic, payload)
        db.add(EvolutionEvent(topic=topic, payload=payload))

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

    def create_task(self, spec: TaskSpec, created_by: str = "anonymous", run_immediately: bool = True) -> Task:
        with self.session_factory() as db:
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
            task.scout_report = scout_report
            task.status = TaskStatus.planned.value
            self._publish(db, EventTopic.scout_reported, {"taskId": task.id, "report": scout_report})

            plan_graph = self.worker.build_plan(spec, scout_report)
            task.plan_graph = plan_graph
            self._publish(db, EventTopic.worker_planned, {"taskId": task.id, "planGraph": plan_graph})

            db.commit()
            db.refresh(task)

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

            result, metrics = self.worker.execute(task, selected)
            result["canaryAssignments"] = canary_assignments
            metrics["canaryAssignedCount"] = len(canary_assignments)
            task.result_payload = result
            task.metrics = metrics
            task.status = TaskStatus.completed.value
            self._publish(
                db,
                EventTopic.worker_completed,
                {"taskId": task.id, "status": task.status, "metrics": metrics},
            )
            db.commit()
            db.refresh(task)
            return task

    def get_task(self, task_id: str) -> Task:
        with self.session_factory() as db:
            task = db.get(Task, task_id)
            if not task:
                raise ValueError(f"task not found: {task_id}")
            return task

    def list_skills(self) -> list[Skill]:
        with self.session_factory() as db:
            return db.query(Skill).order_by(Skill.id.asc()).all()

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
            return skill

    def list_events(self, limit: int = 100, topic: str | None = None) -> list[EvolutionEvent]:
        with self.session_factory() as db:
            query = db.query(EvolutionEvent)
            if topic:
                query = query.filter(EvolutionEvent.topic == topic)
            return query.order_by(EvolutionEvent.created_at.desc()).limit(limit).all()

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
