from __future__ import annotations

from datetime import timedelta

from hosaka_social.clock import Clock
from hosaka_social.config import ChamberConfig, SocialConfig
from hosaka_social.models import CandidateKind, CandidateStatus, ThoughtCandidate


def candidate_utility(candidate: ThoughtCandidate) -> float:
    return (
        candidate.relevance * 0.45
        + candidate.importance * 0.35
        + candidate.urgency * 0.60
        + candidate.confidence * 0.25
        + candidate.novelty * 0.10
        + candidate.humor_value * 0.10
        - candidate.social_risk * 0.50
    )


def ttl_seconds(candidate: ThoughtCandidate, config: ChamberConfig) -> float:
    exp = config.expiration
    if candidate.kind == CandidateKind.DIRECT_RESPONSE:
        return exp.direct_response_seconds
    if candidate.kind == CandidateKind.URGENT_CORRECTION:
        return exp.urgent_correction_seconds
    if candidate.kind == CandidateKind.CLARIFICATION:
        return exp.direct_response_seconds
    if candidate.humor_value >= 0.5:
        return exp.humor_seconds
    if candidate.kind == CandidateKind.CHAMBERED_THOUGHT and candidate.importance >= 0.6:
        return exp.factual_callback_seconds
    return exp.default_seconds


class Chamber:
    """Single-slot thought chamber."""

    def __init__(self, config: SocialConfig, clock: Clock) -> None:
        self.config = config.chamber
        self.clock = clock
        self.current: ThoughtCandidate | None = None
        self._last_decay_mono: float | None = None

    def offer(
        self, candidate: ThoughtCandidate
    ) -> tuple[ThoughtCandidate | None, str]:
        """Try to place `candidate`. Returns (evicted_or_rejected, action)."""
        now_mono = self.clock.monotonic()
        now_wall = self.clock.wall_time()
        ttl = ttl_seconds(candidate, self.config)
        candidate.created_at = now_wall
        candidate.created_mono = now_mono
        candidate.expires_at = now_wall + timedelta(seconds=ttl)
        candidate.expires_mono = now_mono + ttl

        if self.current is None:
            candidate.status = CandidateStatus.CHAMBERED
            self.current = candidate
            self._last_decay_mono = now_mono
            return None, "placed"

        existing = self.current
        if existing.status in {CandidateStatus.AUTHORIZED, CandidateStatus.SPEAKING}:
            if candidate.kind != CandidateKind.DIRECT_RESPONSE:
                return candidate, "rejected_busy"

        direct = candidate.kind == CandidateKind.DIRECT_RESPONSE
        existing_direct = existing.kind == CandidateKind.DIRECT_RESPONSE
        if direct and not existing_direct:
            evicted = existing
            candidate.status = CandidateStatus.CHAMBERED
            self.current = candidate
            self._last_decay_mono = now_mono
            return evicted, "replaced_direct_priority"

        stale = self._is_stale(existing, now_mono)
        new_u = candidate_utility(candidate)
        old_u = candidate_utility(existing)
        if stale or new_u > old_u + self.config.replacement_margin:
            evicted = existing
            candidate.status = CandidateStatus.CHAMBERED
            self.current = candidate
            self._last_decay_mono = now_mono
            return evicted, "replaced"
        return candidate, "rejected_weaker"

    def decay(self, now_mono: float) -> bool:
        candidate = self.current
        if candidate is None:
            return False
        if candidate.status in {CandidateStatus.SPEAKING, CandidateStatus.AUTHORIZED}:
            return False
        interval = self.config.decay.interval_seconds
        if self._last_decay_mono is None:
            self._last_decay_mono = now_mono
            return False
        changed = False
        while now_mono - self._last_decay_mono >= interval:
            candidate.relevance *= self.config.decay.relevance_multiplier
            candidate.importance *= self.config.decay.importance_multiplier
            self._last_decay_mono += interval
            changed = True
        return changed

    def expire(self, now_mono: float) -> ThoughtCandidate | None:
        candidate = self.current
        if candidate is None:
            return None
        if candidate.status in {CandidateStatus.SPEAKING, CandidateStatus.AUTHORIZED}:
            return None
        if now_mono >= candidate.expires_mono:
            candidate.status = CandidateStatus.DISCARDED
            self.current = None
            return candidate
        return None

    def discard_if_topic_changed(self, current_topics: list[str]) -> ThoughtCandidate | None:
        candidate = self.current
        if candidate is None or not candidate.topic_id:
            return None
        if candidate.status in {CandidateStatus.SPEAKING, CandidateStatus.AUTHORIZED}:
            return None
        if current_topics and candidate.topic_id not in current_topics:
            candidate.status = CandidateStatus.DISCARDED
            self.current = None
            return candidate
        return None

    def clear(self, reason: str = "cleared") -> ThoughtCandidate | None:  # noqa: ARG002
        candidate = self.current
        if candidate is None:
            return None
        if candidate.status not in {CandidateStatus.COMPLETED, CandidateStatus.DISCARDED}:
            candidate.status = CandidateStatus.DISCARDED
        self.current = None
        return candidate

    def re_chamber_interrupted(self, candidate: ThoughtCandidate, topics: list[str]) -> bool:
        cfg = self.config.interrupted
        if candidate.attempts >= cfg.max_retries:
            candidate.status = CandidateStatus.DISCARDED
            if self.current is candidate:
                self.current = None
            return False
        if candidate.topic_id and topics and candidate.topic_id not in topics:
            candidate.status = CandidateStatus.DISCARDED
            if self.current is candidate:
                self.current = None
            return False
        candidate.attempts += 1
        candidate.kind = CandidateKind.INTERRUPTED_THOUGHT
        candidate.relevance *= cfg.priority_multiplier
        candidate.importance *= cfg.priority_multiplier
        candidate.status = CandidateStatus.CHAMBERED
        self.current = candidate
        self._last_decay_mono = self.clock.monotonic()
        return True

    def _is_stale(self, candidate: ThoughtCandidate, now_mono: float) -> bool:
        return now_mono >= candidate.expires_mono
