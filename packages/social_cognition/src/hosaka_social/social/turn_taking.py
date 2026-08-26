from __future__ import annotations

from hosaka_social.config import SilenceWindows
from hosaka_social.models import CandidateKind, ConversationState, ThoughtCandidate


def required_gap_ms(candidate: ThoughtCandidate, windows: SilenceWindows) -> int:
    if candidate.kind in {CandidateKind.URGENT_CORRECTION}:
        return windows.minimal_gap
    if candidate.kind in {
        CandidateKind.DIRECT_RESPONSE,
        CandidateKind.CLARIFICATION,
        CandidateKind.TOOL_RESULT,
    }:
        return windows.normal_response_gap
    if candidate.kind == CandidateKind.INTERRUPTED_THOUGHT:
        return windows.chambered_thought_gap
    if candidate.kind == CandidateKind.CHAMBERED_THOUGHT:
        return windows.chambered_thought_gap
    return windows.unsolicited_initiative_gap


def floor_available(
    state: ConversationState,
    candidate: ThoughtCandidate,
    windows: SilenceWindows,
) -> bool:
    if state.human_speaking or state.overlapping_human_speech:
        return False
    if state.agent_is_speaking:
        return False
    return state.silence_duration_ms >= required_gap_ms(candidate, windows)
