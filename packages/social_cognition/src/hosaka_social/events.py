from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EventBase(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    sequence_number: int = 0
    wall_time: datetime | None = None
    monotonic_time: float | None = None


class AudioActivityStarted(EventBase):
    event_type: Literal["audio_activity_started"] = "audio_activity_started"
    speaker_hint: str | None = None
    confidence: float = 1.0


class AudioActivityEnded(EventBase):
    event_type: Literal["audio_activity_ended"] = "audio_activity_ended"
    duration_ms: int = 0


class TranscriptFinalized(EventBase):
    event_type: Literal["transcript_finalized"] = "transcript_finalized"
    utterance_id: UUID = Field(default_factory=uuid4)
    speaker_id: str
    text: str
    asr_confidence: float = 1.0
    started_at: datetime | None = None
    ended_at: datetime | None = None
    topic_ids: list[str] = Field(default_factory=list)
    addressed_agent_probability: float | None = None


class TranscriptPartial(EventBase):
    event_type: Literal["transcript_partial"] = "transcript_partial"
    utterance_id: UUID = Field(default_factory=uuid4)
    speaker_id: str | None = None
    text: str
    stability: float = 0.0


class SpeakerChanged(EventBase):
    event_type: Literal["speaker_changed"] = "speaker_changed"
    previous_speaker: str | None = None
    current_speaker: str | None = None


class AgentAddressed(EventBase):
    event_type: Literal["agent_addressed"] = "agent_addressed"
    utterance_id: UUID
    probability: float
    detection_method: Literal[
        "wake_name", "linguistic", "conversation_context", "external"
    ] = "wake_name"


class ThoughtCandidateCreated(EventBase):
    event_type: Literal["thought_candidate_created"] = "thought_candidate_created"
    candidate_id: UUID


class ThoughtCandidateUpdated(EventBase):
    event_type: Literal["thought_candidate_updated"] = "thought_candidate_updated"
    candidate_id: UUID


class ThoughtCandidateDiscarded(EventBase):
    event_type: Literal["thought_candidate_discarded"] = "thought_candidate_discarded"
    candidate_id: UUID
    reason: str


class SpeechOpportunityDetected(EventBase):
    event_type: Literal["speech_opportunity_detected"] = "speech_opportunity_detected"
    silence_ms: int
    confidence: float = 1.0


class SpeechAuthorized(EventBase):
    event_type: Literal["speech_authorized"] = "speech_authorized"
    candidate_id: UUID
    decision_score: float


class SpeechSuppressed(EventBase):
    event_type: Literal["speech_suppressed"] = "speech_suppressed"
    candidate_id: UUID | None = None
    reasons: list[str] = Field(default_factory=list)


class SpeechStarted(EventBase):
    event_type: Literal["speech_started"] = "speech_started"
    speech_id: UUID
    candidate_id: UUID | None = None


class SpeechInterrupted(EventBase):
    event_type: Literal["speech_interrupted"] = "speech_interrupted"
    speech_id: UUID
    interrupted_by: str | None = None
    spoken_fraction: float = 0.0


class SpeechCompleted(EventBase):
    event_type: Literal["speech_completed"] = "speech_completed"
    speech_id: UUID


class SpeechDucked(EventBase):
    event_type: Literal["speech_ducked"] = "speech_ducked"
    speech_id: UUID


class ProviderUnavailable(EventBase):
    event_type: Literal["provider_unavailable"] = "provider_unavailable"
    provider_id: str


class ProviderRecovered(EventBase):
    event_type: Literal["provider_recovered"] = "provider_recovered"
    provider_id: str


class FaceStateChanged(EventBase):
    event_type: Literal["face_state_changed"] = "face_state_changed"
    state: str


AnyEvent = Annotated[
    Union[
        AudioActivityStarted,
        AudioActivityEnded,
        TranscriptFinalized,
        TranscriptPartial,
        SpeakerChanged,
        AgentAddressed,
        ThoughtCandidateCreated,
        ThoughtCandidateUpdated,
        ThoughtCandidateDiscarded,
        SpeechOpportunityDetected,
        SpeechAuthorized,
        SpeechSuppressed,
        SpeechStarted,
        SpeechInterrupted,
        SpeechCompleted,
        SpeechDucked,
        ProviderUnavailable,
        ProviderRecovered,
        FaceStateChanged,
    ],
    Field(discriminator="event_type"),
]

CANCEL_EVENT_TYPES = frozenset(
    {"audio_activity_started", "speech_interrupted"}
)
