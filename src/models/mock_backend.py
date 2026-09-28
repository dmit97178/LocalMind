"""P0 mock implementation of ModelBackend."""

from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy
from dataclasses import dataclass, field

from src.core.interfaces import ModelBackend
from src.core.schemas import ModelCapabilities, ModelError


@dataclass
class MockModelBackend(ModelBackend):
    """Deterministic model backend for local core-loop tests."""

    text_response: str | None = None
    structured_response: dict = field(default_factory=dict)
    _loaded: bool = False

    def generate(
        self,
        prompt: str,
        response_schema: dict | None = None,
    ) -> dict:
        self._ensure_loaded("generate")
        if response_schema is not None:
            return deepcopy(self.structured_response)

        if self.text_response is not None:
            return {"text": self.text_response}
        return {"text": f"Mock response: {prompt}"}

    def stream(self, prompt: str) -> Iterator[str]:
        self._ensure_loaded("stream")
        text = self.text_response if self.text_response is not None else f"Mock response: {prompt}"
        for index, chunk in enumerate(text.split(" ")):
            if index:
                yield " "
            yield chunk

    def get_capabilities(self) -> ModelCapabilities:
        self._ensure_loaded("get_capabilities")
        return ModelCapabilities(
            supports_structured_output=True,
            max_context_tokens=4096,
            local_only=True,
        )

    def load(self) -> None:
        self._loaded = True

    def unload(self) -> None:
        self._loaded = False

    def health_check(self) -> bool:
        return self._loaded

    def _ensure_loaded(self, operation: str) -> None:
        if self._loaded:
            return
        raise ModelError(
            code="MODEL_UNAVAILABLE",
            message=f"Mock model must be loaded before {operation}",
            user_message="本地模型尚未就绪，请稍候。",
            recoverable=True,
            details={"operation": operation},
        )
