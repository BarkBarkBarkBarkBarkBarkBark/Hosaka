from __future__ import annotations

from pydantic import BaseModel, Field


class PositiveWeights(BaseModel):
    direct_address: float = 1.00
    explicit_question: float = 0.65
    unresolved_question: float = 0.50
    candidate_relevance: float = 0.45
    candidate_importance: float = 0.35
    urgency: float = 0.60
    confidence: float = 0.25
    long_pause: float = 0.20
    turns_since_agent_spoke: float = 0.15
    humor_value: float = 0.10


class NegativeWeights(BaseModel):
    human_currently_speaking: float = 1.00
    overlapping_human_speech: float = 1.00
    recent_agent_speech: float = 0.70
    rapid_exchange: float = 0.45
    low_asr_confidence: float = 0.50
    topic_drift: float = 0.60
    candidate_social_risk: float = 0.50
    candidate_staleness: float = 0.70


class GovernorThresholds(BaseModel):
    discard_below: float = 0.30
    hold_below: float = 0.68
    speak_at_gap: float = 0.68
    interrupt: float = 0.94


class TurnShareTargets(BaseModel):
    minimum: float = 0.03
    preferred: float = 0.10
    maximum_soft_limit: float = 0.20


class SilenceBiasConfig(BaseModel):
    enabled: bool = True
    baseline_suppression: float = 0.20
    target_agent_share_of_turns: TurnShareTargets = Field(
        default_factory=TurnShareTargets
    )


class GovernorConfig(BaseModel):
    weights_positive: PositiveWeights = Field(default_factory=PositiveWeights)
    weights_negative: NegativeWeights = Field(default_factory=NegativeWeights)
    thresholds: GovernorThresholds = Field(default_factory=GovernorThresholds)
    silence_bias: SilenceBiasConfig = Field(default_factory=SilenceBiasConfig)
    asr_confidence_floor: float = 0.35
    long_pause_ms: int = 900
    turns_since_spoke_full: int = 8


class ChamberDecayConfig(BaseModel):
    interval_seconds: float = 5.0
    relevance_multiplier: float = 0.94
    importance_multiplier: float = 0.98


class ChamberExpirationConfig(BaseModel):
    default_seconds: float = 45.0
    direct_response_seconds: float = 12.0
    humor_seconds: float = 20.0
    factual_callback_seconds: float = 60.0
    urgent_correction_seconds: float = 15.0


class InterruptedConfig(BaseModel):
    priority_multiplier: float = 0.75
    max_retries: int = 1


class ChamberConfig(BaseModel):
    replacement_margin: float = 0.15
    decay: ChamberDecayConfig = Field(default_factory=ChamberDecayConfig)
    expiration: ChamberExpirationConfig = Field(default_factory=ChamberExpirationConfig)
    interrupted: InterruptedConfig = Field(default_factory=InterruptedConfig)


class SilenceWindows(BaseModel):
    minimal_gap: int = 350
    normal_response_gap: int = 600
    chambered_thought_gap: int = 900
    unsolicited_initiative_gap: int = 1400


class TurnTakingConfig(BaseModel):
    silence_windows_ms: SilenceWindows = Field(default_factory=SilenceWindows)


class BargeInConfig(BaseModel):
    duck_after_ms: int = 120
    cancel_after_ms: int = 250


class CooldownConfig(BaseModel):
    recent_speech_seconds: float = 8.0


class MemoryConfig(BaseModel):
    conversation_max_turns: int = 40
    conversation_max_age_minutes: float = 20.0
    working_memory_max_items: int = 20
    working_memory_ttl_minutes: float = 30.0


class SocialConfig(BaseModel):
    agent_name: str = "hosaka"
    governor: GovernorConfig = Field(default_factory=GovernorConfig)
    chamber: ChamberConfig = Field(default_factory=ChamberConfig)
    turn_taking: TurnTakingConfig = Field(default_factory=TurnTakingConfig)
    barge_in: BargeInConfig = Field(default_factory=BargeInConfig)
    cooldown: CooldownConfig = Field(default_factory=CooldownConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    direct_address_probability: float = 0.75
