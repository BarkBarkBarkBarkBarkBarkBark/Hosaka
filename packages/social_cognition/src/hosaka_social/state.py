from __future__ import annotations

from datetime import timedelta

from hosaka_social.clock import Clock
from hosaka_social.config import MemoryConfig
from hosaka_social.models import ConversationState, InternalState, Utterance, WorkingMemoryItem


class ConversationStore:
    """Bounded conversation + working memory. Engine-owned."""

    def __init__(self, config: MemoryConfig, clock: Clock) -> None:
        self._config = config
        self._clock = clock
        self.conversation = ConversationState()
        self.internal = InternalState()

    def add_utterance(self, utterance: Utterance) -> None:
        state = self.conversation
        state.recent_utterances.append(utterance)
        state.human_turn_count += 1
        state.turns_since_agent_spoke += 1
        state.conversation_generation += 1
        self._trim_utterances()
        self._refresh_speakers(utterance)
        if utterance.topic_ids:
            state.current_topics = list(dict.fromkeys(utterance.topic_ids))[:8]

    def add_working_memory(self, item: WorkingMemoryItem) -> None:
        items = self.conversation.working_memory
        items.append(item)
        self._trim_memory()

    def record_agent_turn(self) -> None:
        self.conversation.agent_turn_count += 1
        self.conversation.turns_since_agent_spoke = 0
        self.conversation.last_agent_speech_at = self._clock.wall_time()
        self.conversation.last_agent_speech_mono = self._clock.monotonic()

    def _trim_utterances(self) -> None:
        cfg = self._config
        now = self._clock.wall_time()
        max_age = timedelta(minutes=cfg.conversation_max_age_minutes)
        kept = [
            u
            for u in self.conversation.recent_utterances
            if now - u.ended_at <= max_age
        ]
        if len(kept) > cfg.conversation_max_turns:
            kept = kept[-cfg.conversation_max_turns :]
        self.conversation.recent_utterances = kept

    def _trim_memory(self) -> None:
        cfg = self._config
        now = self._clock.wall_time()
        items = [
            i
            for i in self.conversation.working_memory
            if i.expires_at is None or i.expires_at > now
        ]
        if len(items) > cfg.working_memory_max_items:
            items = sorted(items, key=lambda x: x.salience, reverse=True)[
                : cfg.working_memory_max_items
            ]
        self.conversation.working_memory = items

    def _refresh_speakers(self, utterance: Utterance) -> None:
        state = self.conversation
        if utterance.speaker_id not in state.active_speakers:
            state.active_speakers.append(utterance.speaker_id)
            state.active_speakers = state.active_speakers[-8:]
        state.primary_speaker = utterance.speaker_id
