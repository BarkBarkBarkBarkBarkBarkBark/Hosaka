from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from hosaka_social.config import SocialConfig
from hosaka_social.models import CandidateKind, CandidateStatus, ConversationState, ThoughtCandidate, Utterance
from hosaka_social.social.cooldown import recent_speech_factor


class DecisionOutcome(str, Enum):
    NO_ACTION = "no_action"
    DISCARD = "discard"
    HOLD = "hold"
    SPEAK = "speak"
    SUPPRESS = "suppress"
    INTERRUPT = "interrupt"


class DecisionTrace(BaseModel):
    candidate_id: str | None = None
    outcome: DecisionOutcome = DecisionOutcome.NO_ACTION
    score: float = 0.0
    positive: dict[str, float] = Field(default_factory=dict)
    negative: dict[str, float] = Field(default_factory=dict)
    hard_inhibitors: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _last_utterance(state: ConversationState) -> Utterance | None:
    if not state.recent_utterances:
        return None
    return state.recent_utterances[-1]


def _is_question(text: str) -> bool:
    stripped = text.strip()
    if stripped.endswith("?"):
        return True
    head = stripped.lower()
    return head.startswith(
        ("what ", "why ", "how ", "when ", "where ", "who ", "which ", "can you", "could you")
    )


class SocialGovernor:
    """Deterministic speech authorization. The LLM does not get the floor."""

    def __init__(self, config: SocialConfig) -> None:
        self.config = config

    def evaluate(
        self,
        candidate: ThoughtCandidate | None,
        state: ConversationState,
        *,
        floor_open: bool,
        now_mono: float,
    ) -> DecisionTrace:
        if candidate is None:
            return DecisionTrace(outcome=DecisionOutcome.NO_ACTION, reasons=["no_candidate"])
        if candidate.status == CandidateStatus.DISCARDED:
            return DecisionTrace(
                candidate_id=str(candidate.id),
                outcome=DecisionOutcome.DISCARD,
                hard_inhibitors=["candidate_discarded"],
                reasons=["candidate_discarded"],
            )
        if candidate.status in {CandidateStatus.SPEAKING, CandidateStatus.AUTHORIZED}:
            return DecisionTrace(
                candidate_id=str(candidate.id),
                outcome=DecisionOutcome.NO_ACTION,
                reasons=["already_in_speech_path"],
            )

        inhibitors = self._hard_inhibitors(candidate, state)
        pos, neg = self._features(candidate, state, now_mono)
        score = self._score(candidate, pos, neg, state, include_recent_speech=True)
        durable = self._score(candidate, pos, neg, state, include_recent_speech=False)

        trace = DecisionTrace(
            candidate_id=str(candidate.id),
            score=score,
            positive=pos,
            negative=neg,
            hard_inhibitors=inhibitors,
        )

        if state.muted:
            trace.outcome = DecisionOutcome.SUPPRESS
            trace.reasons = ["muted"]
            return trace

        if inhibitors:
            trace.outcome = DecisionOutcome.SUPPRESS
            trace.reasons = list(inhibitors)
            return trace

        thresholds = self.config.governor.thresholds
        if durable < thresholds.discard_below:
            trace.outcome = DecisionOutcome.DISCARD
            trace.reasons = ["score_below_discard"]
            return trace

        if score >= thresholds.interrupt and not state.human_speaking:
            if floor_open:
                trace.outcome = DecisionOutcome.SPEAK
                trace.reasons = ["interrupt_threshold"]
                return trace

        if score >= thresholds.speak_at_gap:
            if floor_open:
                trace.outcome = DecisionOutcome.SPEAK
                trace.reasons = ["speak_at_gap"]
            else:
                trace.outcome = DecisionOutcome.HOLD
                trace.reasons = ["waiting_for_floor"]
            return trace

        trace.outcome = DecisionOutcome.HOLD
        trace.reasons = ["score_in_hold_band"]
        return trace

    def _hard_inhibitors(
        self, candidate: ThoughtCandidate, state: ConversationState
    ) -> list[str]:
        reasons: list[str] = []
        safety = candidate.kind == CandidateKind.URGENT_CORRECTION and candidate.urgency >= 0.95
        if (state.overlapping_human_speech or state.human_speaking) and not safety:
            if candidate.kind != CandidateKind.DIRECT_RESPONSE or state.human_speaking:
                reasons.append("human_speaking")
        if state.overlapping_human_speech and not safety:
            reasons.append("overlapping_human_speech")
        last = _last_utterance(state)
        floor = self.config.governor.asr_confidence_floor
        wake = bool(last and last.addressed_agent_probability >= 0.75)
        if last is not None and last.asr_confidence < floor and not wake:
            reasons.append("low_asr_confidence")
        return reasons

    def _features(
        self,
        candidate: ThoughtCandidate,
        state: ConversationState,
        now_mono: float,
    ) -> tuple[dict[str, float], dict[str, float]]:
        last = _last_utterance(state)
        addressed = 0.0
        question = 0.0
        asr = 1.0
        if last is not None:
            addressed = last.addressed_agent_probability
            question = 1.0 if _is_question(last.text) else 0.0
            asr = last.asr_confidence
            if candidate.kind == CandidateKind.DIRECT_RESPONSE:
                addressed = max(addressed, 1.0 if addressed >= 0.75 else addressed)

        unresolved = 1.0 if candidate.kind in {
            CandidateKind.DIRECT_RESPONSE,
            CandidateKind.CLARIFICATION,
        } and question else 0.0
        if candidate.kind == CandidateKind.URGENT_CORRECTION:
            unresolved = max(unresolved, 1.0)

        long_pause = 1.0 if state.silence_duration_ms >= self.config.governor.long_pause_ms else 0.0
        turns_feat = _clamp(state.turns_since_agent_spoke / self.config.governor.turns_since_spoke_full)

        ttl = max(candidate.expires_mono - candidate.created_mono, 0.001)
        age = max(now_mono - candidate.created_mono, 0.0)
        staleness = _clamp(age / ttl)

        topic_drift = 0.0
        if candidate.topic_id and state.current_topics:
            if candidate.topic_id not in state.current_topics:
                topic_drift = 1.0
        elif candidate.topic_id and not state.current_topics:
            topic_drift = 0.0

        recent = recent_speech_factor(
            state.last_agent_speech_mono,
            now_mono,
            self.config.cooldown.recent_speech_seconds,
        )

        low_asr = 1.0 if asr < 0.55 else _clamp((0.7 - asr) / 0.7)

        pos = {
            "direct_address": _clamp(addressed),
            "explicit_question": question,
            "unresolved_question": unresolved,
            "candidate_relevance": _clamp(candidate.relevance),
            "candidate_importance": _clamp(candidate.importance),
            "urgency": _clamp(candidate.urgency),
            "confidence": _clamp(candidate.confidence),
            "long_pause": long_pause,
            "turns_since_agent_spoke": turns_feat,
            "humor_value": _clamp(candidate.humor_value),
        }
        neg = {
            "human_currently_speaking": 1.0 if state.human_speaking else 0.0,
            "overlapping_human_speech": 1.0 if state.overlapping_human_speech else 0.0,
            "recent_agent_speech": recent,
            "rapid_exchange": _clamp(state.rapid_exchange_score),
            "low_asr_confidence": low_asr if asr < 0.7 else 0.0,
            "topic_drift": topic_drift,
            "candidate_social_risk": _clamp(candidate.social_risk),
            "candidate_staleness": staleness,
        }
        return pos, neg

    def _score(
        self,
        candidate: ThoughtCandidate,
        pos: dict[str, float],
        neg: dict[str, float],
        state: ConversationState,
        *,
        include_recent_speech: bool = True,
    ) -> float:
        wp = self.config.governor.weights_positive
        wn = self.config.governor.weights_negative
        raw = 0.0
        raw += wp.direct_address * pos["direct_address"]
        raw += wp.explicit_question * pos["explicit_question"]
        raw += wp.unresolved_question * pos["unresolved_question"]
        raw += wp.candidate_relevance * pos["candidate_relevance"]
        raw += wp.candidate_importance * pos["candidate_importance"]
        raw += wp.urgency * pos["urgency"]
        raw += wp.confidence * pos["confidence"]
        raw += wp.long_pause * pos["long_pause"]
        raw += wp.turns_since_agent_spoke * pos["turns_since_agent_spoke"]
        raw += wp.humor_value * pos["humor_value"]
        raw -= wn.human_currently_speaking * neg["human_currently_speaking"]
        raw -= wn.overlapping_human_speech * neg["overlapping_human_speech"]
        if include_recent_speech:
            raw -= wn.recent_agent_speech * neg["recent_agent_speech"]
        raw -= wn.rapid_exchange * neg["rapid_exchange"]
        raw -= wn.low_asr_confidence * neg["low_asr_confidence"]
        raw -= wn.topic_drift * neg["topic_drift"]
        raw -= wn.candidate_social_risk * neg["candidate_social_risk"]
        raw -= wn.candidate_staleness * neg["candidate_staleness"]

        unsolicited = candidate.kind not in {
            CandidateKind.DIRECT_RESPONSE,
            CandidateKind.URGENT_CORRECTION,
            CandidateKind.CLARIFICATION,
        }
        bias = self.config.governor.silence_bias
        if bias.enabled and unsolicited:
            raw -= bias.baseline_suppression
            share = state.agent_turn_share
            targets = bias.target_agent_share_of_turns
            if share > targets.maximum_soft_limit:
                raw -= 0.25
            elif share < targets.minimum and state.human_turn_count >= 8:
                raw += 0.05

        return _clamp(raw)
