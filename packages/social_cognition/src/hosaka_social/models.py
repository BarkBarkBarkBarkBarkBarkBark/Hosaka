from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class CandidateKind(str, Enum):
    DIRECT_RESPONSE = "direct_response"
    CHAMBERED_THOUGHT = "chambered_thought"
    INTERRUPTED_THOUGHT = "interrupted_thought"
    CLARIFICATION = "clarification"
    URGENT_CORRECTION = "urgent_correction"
    TOOL_RESULT = "tool_result"


class CandidateStatus(str, Enum):
    CANDIDATE = "candidate"
    CHAMBERED = "chambered"
    AUTHORIZED = "authorized"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    DISCARDED = "discarded"


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class SpeechRequest(BaseModel):
    speech_id: UUID = Field(default_factory=uuid4)
    candidate_id: UUID | None = None
    text: str
    duckable: bool = True


class Utterance(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    speaker_id: str
    text: str
    asr_confidence: float = 1.0
    started_at: datetime
    ended_at: datetime
    addressed_agent_probability: float = 0.0
    semantic_embedding: list[float] | None = None
    topic_ids: list[str] = Field(default_factory=list)


class SpeakerState(BaseModel):
    speaker_id: str
    display_name: str | None = None
    currently_speaking: bool = False
    last_spoke_at: datetime | None = None
    recent_topics: list[str] = Field(default_factory=list)
    session_observations: list[str] = Field(default_factory=list)


class WorkingMemoryItem(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    statement: str
    confidence: float = 0.5
    salience: float = 0.5
    source_utterance_ids: list[UUID] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None


class ThoughtCandidate(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    kind: CandidateKind = CandidateKind.CHAMBERED_THOUGHT
    content: str
    target_speaker_id: str | None = None
    source_utterance_ids: list[UUID] = Field(default_factory=list)
    topic_id: str | None = None
    confidence: float = 0.5
    relevance: float = 0.5
    importance: float = 0.5
    humor_value: float = 0.0
    urgency: float = 0.0
    novelty: float = 0.5
    social_risk: float = 0.0
    created_at: datetime
    expires_at: datetime
    attempts: int = 0
    status: CandidateStatus = CandidateStatus.CANDIDATE
    created_mono: float = 0.0
    expires_mono: float = 0.0
    conversation_generation: int = 0


class ConversationState(BaseModel):
    active_speakers: list[str] = Field(default_factory=list)
    primary_speaker: str | None = None
    human_speaking: bool = False
    overlapping_human_speech: bool = False
    agent_is_speaking: bool = False
    silence_duration_ms: int = 0
    rapid_exchange_score: float = 0.0
    current_topics: list[str] = Field(default_factory=list)
    last_agent_speech_at: datetime | None = None
    last_agent_speech_mono: float | None = None
    turns_since_agent_spoke: int = 0
    recent_utterances: list[Utterance] = Field(default_factory=list)
    working_memory: list[WorkingMemoryItem] = Field(default_factory=list)
    chamber: ThoughtCandidate | None = None
    muted: bool = False
    human_turn_count: int = 0
    agent_turn_count: int = 0
    conversation_generation: int = 0

    @property
    def agent_turn_share(self) -> float:
        total = self.human_turn_count + self.agent_turn_count
        if total <= 0:
            return 0.0
        return self.agent_turn_count / total


class InternalState(BaseModel):
    attention_target: str | None = None
    attention_strength: float = 0.0
    curiosity: float = 0.0
    social_energy: float = 0.5
    urge_to_speak: float = 0.0
    suppression: float = 0.2
    confidence: float = 0.5
    current_goal: str | None = None
    unresolved_items: list[str] = Field(default_factory=list)
    chamber_candidate_id: UUID | None = None


class ReflectionResult(BaseModel):
    interesting: bool = False
    observations: list[str] = Field(default_factory=list)
    unresolved_items: list[str] = Field(default_factory=list)
    candidate_worth_generating: bool = False
    candidate_kind: str | None = None
    relevance: float = 0.0
    content: str | None = None
