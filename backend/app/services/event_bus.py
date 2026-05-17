from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from threading import Lock
from typing import Any

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None


class EventTopic:
    scout_reported = "scout.reported"
    scout_pheromone_deposited = "scout.pheromone_deposited"
    scout_pheromone_evaporated = "scout.pheromone_evaporated"
    scout_patrolled = "scout.patrolled"
    worker_planned = "worker.planned"
    worker_completed = "worker.completed"
    canary_assigned = "canary.assigned"
    canary_observed = "canary.observed"
    shadow_evaluated = "shadow.evaluated"
    feedback_received = "feedback.received"
    feedback_auto_inferred = "feedback.auto_inferred"
    worm_proposed = "worm.proposed"
    queen_promoted = "queen.promoted"
    queen_rolled_back = "queen.rolled_back"


@dataclass(slots=True)
class EventMessage:
    topic: str
    payload: dict[str, Any]
    timestamp: datetime


class EventBus(ABC):
    @abstractmethod
    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def recent(self, limit: int = 100, topic: str | None = None) -> list[EventMessage]:
        raise NotImplementedError


class InMemoryEventBus(EventBus):
    def __init__(self) -> None:
        self._events: list[EventMessage] = []
        self._lock = Lock()

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._events.append(
                EventMessage(
                    topic=topic,
                    payload=payload,
                    timestamp=datetime.now(timezone.utc),
                )
            )

    def recent(self, limit: int = 100, topic: str | None = None) -> list[EventMessage]:
        with self._lock:
            filtered = self._events
            if topic:
                filtered = [evt for evt in filtered if evt.topic == topic]
            return filtered[-limit:]


class RedisStreamEventBus(EventBus):
    def __init__(self, redis_url: str, stream_key: str = "beeagi:events") -> None:
        if redis is None:
            raise RuntimeError("redis package is not installed")
        self.client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        self.stream_key = stream_key

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        self.client.xadd(
            self.stream_key,
            {
                "topic": topic,
                "payload": json.dumps(payload, ensure_ascii=False),
                "timestamp": timestamp,
            },
        )

    def recent(self, limit: int = 100, topic: str | None = None) -> list[EventMessage]:
        rows = self.client.xrevrange(self.stream_key, count=limit)
        events: list[EventMessage] = []
        for _, data in reversed(rows):
            evt_topic = data.get("topic", "")
            if topic and evt_topic != topic:
                continue
            evt_payload = json.loads(data.get("payload", "{}"))
            timestamp_str = data.get("timestamp")
            if timestamp_str:
                timestamp = datetime.fromisoformat(timestamp_str)
            else:
                timestamp = datetime.now(timezone.utc)
            events.append(EventMessage(topic=evt_topic, payload=evt_payload, timestamp=timestamp))
        return events


def build_event_bus(redis_url: str | None) -> EventBus:
    logger = logging.getLogger(__name__)
    if redis_url and redis is not None:
        try:
            bus = RedisStreamEventBus(redis_url=redis_url)
            bus.client.ping()
            return bus
        except Exception as exc:
            logger.warning("Redis event bus unavailable; fallback to in-memory bus: %s", exc)
            return InMemoryEventBus()
    if redis_url and redis is None:
        logger.warning("redis package not installed; fallback to in-memory event bus")
    return InMemoryEventBus()
