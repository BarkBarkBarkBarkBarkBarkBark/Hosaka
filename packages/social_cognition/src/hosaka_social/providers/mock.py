from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from hosaka_social.models import Message, ReflectionResult
from hosaka_social.providers.base import LLMProvider, ProviderHealth, StructuredOutputError

T = TypeVar("T", bound=BaseModel)

_MALFORMED = object()


class MockLLMProvider:
    provider_id = "mock"

    def __init__(self) -> None:
        self._structured: list[Any] = []
        self._text: list[str] = []
        self.status = ProviderHealth.HEALTHY
        self.calls_structured = 0
        self.calls_text = 0

    def enqueue_structured(self, payload: BaseModel | dict[str, Any]) -> None:
        self._structured.append(payload)

    def enqueue_malformed(self) -> None:
        self._structured.append(_MALFORMED)

    def enqueue_text(self, text: str) -> None:
        self._text.append(text)

    async def generate_text(
        self,
        messages: list[Message],
        *,
        temperature: float,
        max_tokens: int,
        timeout_seconds: float,
    ) -> str:
        self.calls_text += 1
        if self.status == ProviderHealth.UNAVAILABLE:
            raise TimeoutError("mock provider unavailable")
        if self._text:
            return self._text.pop(0)
        return ""

    async def generate_structured(
        self,
        messages: list[Message],
        response_model: type[T],
        *,
        temperature: float,
        timeout_seconds: float,
    ) -> T:
        self.calls_structured += 1
        if self.status == ProviderHealth.UNAVAILABLE:
            raise TimeoutError("mock provider unavailable")
        if not self._structured:
            if response_model is ReflectionResult:
                return ReflectionResult()  # type: ignore[return-value]
            raise StructuredOutputError("no structured payload queued")
        item = self._structured.pop(0)
        if item is _MALFORMED:
            raise StructuredOutputError("malformed structured output")
        if isinstance(item, response_model):
            return item
        try:
            return response_model.model_validate(item)
        except ValidationError as exc:
            raise StructuredOutputError(str(exc)) from exc

    async def health(self) -> ProviderHealth:
        return self.status


assert isinstance(MockLLMProvider(), LLMProvider)
