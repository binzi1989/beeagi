from __future__ import annotations

import hashlib


class CanaryAllocator:
    def __init__(self, ratio: float) -> None:
        self.ratio = max(0.0, min(1.0, ratio))
        self.threshold = int(self.ratio * 100)

    def bucket(self, user_id: str, skill_id: str, candidate_id: str) -> int:
        raw = f"{user_id}:{skill_id}:{candidate_id}".encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()
        # deterministic 0-99 bucket
        return int(digest[:8], 16) % 100

    def is_selected(self, user_id: str, skill_id: str, candidate_id: str) -> tuple[bool, int]:
        b = self.bucket(user_id=user_id, skill_id=skill_id, candidate_id=candidate_id)
        return b < self.threshold, b
