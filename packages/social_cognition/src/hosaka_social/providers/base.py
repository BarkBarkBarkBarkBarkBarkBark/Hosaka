from __future__ import annotations

from enum import Enum
from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from hosaka_social.models import Message

T = TypeVar("T", bound=BaseModel)


class ProviderHealth(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class StructuredOutputError(ValueError):
    """Malformed structured LLM output. Callers must fail closed."""


@runtime_checkable
class LLMProvider(Protocol):
    provider_id: str

    async def generate_text(
        self,
        messages: list[Message],
        *,
        temperature: float,
        max_tokens: int,
        timeout_seconds: float,
    ) -> str:
        ...

    async def generate_structured(
        self,
        messages: list[Message],
        response_model: type[T],
        *,
        temperature: float,
        timeout_seconds: float,
    ) -> T:
        ...

    async def health(self) -> ProviderHealth:
        ...
