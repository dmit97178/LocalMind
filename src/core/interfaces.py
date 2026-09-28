"""Abstract interfaces that isolate core logic from replaceable backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping, Sequence
from typing import Protocol

from src.core.risk_vocabulary import read_approval_profile
from src.core.schemas import (
    AdvisoryResult,
    CloudRequestPackage,
    Experience,
    MemoryChunk,
    ModelCapabilities,
    PreflightReport,
    ProviderSnapshot,
    Result,
    RuntimeEvent,
    SafetyVerdict,
    Skill,
    ToolCapability,
    ToolDef,
    ToolError,
)


class CloudGrant(Protocol):
    """Minimal Core view of a locally-issued cloud authorization boundary."""

    @property
    def grant_id(self) -> str: ...

    @property
    def task_id(self) -> str: ...

    @property
    def session_id(self) -> str: ...

    @property
    def provider(self) -> str: ...

    @property
    def purpose(self) -> str: ...


class ModelBackend(ABC):
    """Language model adapter boundary."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        response_schema: dict | None = None,
    ) -> dict:
        """Generate a complete response."""

    @abstractmethod
    def stream(self, prompt: str) -> Iterator[str]:
        """Generate response chunks for realtime CLI output."""

    @abstractmethod
    def get_capabilities(self) -> ModelCapabilities:
        """Return capabilities for the currently loaded model."""

    @abstractmethod
    def load(self) -> None:
        """Load the model into its ready state."""

    @abstractmethod
    def unload(self) -> None:
        """Release model resources."""

    @abstractmethod
    def health_check(self) -> bool:
        """Return whether the model is available without raising."""


class MemoryBackend(ABC):
    """Memory storage and retrieval boundary."""

    @abstractmethod
    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        *,
        max_bytes: int | None = None,
        topic_hints: Sequence[str] = (),
        project_id: str | None = None,
    ) -> Result[list[MemoryChunk]]:
        """Retrieve relevant memory chunks."""

    @abstractmethod
    def store_episode(self, content: str, metadata: dict) -> str:
        """Store one conversation episode and return its chunk id."""

    @abstractmethod
    def get_summary(self, scope: str, scope_id: str) -> dict | None:
        """Return a stored summary for a conversation or project scope."""

    @abstractmethod
    def save_summary(self, scope: str, scope_id: str, summary: dict) -> None:
        """Store or overwrite a summary for a conversation or project scope."""

    @abstractmethod
    def detect_topic_relation(self, current_input: str, current_topic: str) -> str:
        """Classify how the input relates to the current topic.

        Returns one of same_topic, new_topic, shift_with_reference, or ambiguous.
        """


class ProjectRecordStore(Protocol):
    """Low-level project-record persistence used by ProjectStore."""

    def get_project_record(self, project_id: str) -> dict | None: ...

    def put_project_record(self, record: dict) -> None: ...

    def list_project_ids(self) -> list[str]: ...


class EmbeddingBackend(ABC):
    """Local text-vectorization boundary."""

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> Result[list[list[float]]]: ...

    @abstractmethod
    def embed_query(self, text: str) -> Result[list[float]]: ...

    @abstractmethod
    def dimensions(self) -> int: ...

    @abstractmethod
    def model_id(self) -> str: ...

    @abstractmethod
    def health_check(self) -> bool: ...


class ToolBackend(ABC):
    """Tool registry and execution boundary, used behind GuardedToolExecutor."""

    @abstractmethod
    def list_tools(self) -> list[ToolDef]:
        """Return registered tool definitions."""

    def list_capabilities(self) -> list[ToolCapability]:
        """Return active capability declarations, or none for legacy backends."""

        return []

    @abstractmethod
    def execute(self, tool_name: str, params: dict) -> Result[dict]:
        """Execute a registered tool."""

    def preflight(self, tool_name: str, params: dict) -> PreflightReport:
        """Return a side-effect-free risk assessment for one registered tool."""

        registered = {tool.name: tool for tool in self.list_tools()}
        tool = registered.get(tool_name)
        if tool is None:
            raise ToolError(
                code="TOOL_NOT_FOUND",
                message=f"Tool is not registered: {tool_name}",
                user_message="所需工具不可用。",
                recoverable=True,
                details={"tool_name": tool_name},
            )
        return PreflightReport(
            effective_risk=tool.risk_level,
            requires_confirmation=tool.risk_level in {"sensitive", "dangerous"},
            approval_profile=read_approval_profile(tool.approval_profile),
        )

    def close(self) -> None:
        """Release process-level resources; resource-free backends need no work."""

        return None


class ToolProvider(ABC):
    """Dynamic tool source with no authority over local capabilities or risk."""

    provider_id: str

    @abstractmethod
    def handshake(self) -> ProviderSnapshot:
        """Start the provider and return its candidate tools once."""

    @abstractmethod
    def execute(self, raw_name: str, params: Mapping[str, object]) -> Result[dict]:
        """Execute an already admitted provider tool by its raw name."""

    @abstractmethod
    def close(self) -> None:
        """Idempotently terminate and reap provider resources without raising."""


class SafetyBackend(ABC):
    """Safety decision boundary for potentially dangerous operations."""

    @abstractmethod
    def check_dangerous(self, operation: dict) -> SafetyVerdict:
        """Check whether a single operation is allowed."""


class CloudAdvisoryBackend(ABC):
    """Cloud model advisory boundary."""

    @abstractmethod
    def advise(self, request: CloudRequestPackage) -> AdvisoryResult:
        """Return non-authoritative cloud advice."""


class CloudTurnGateway(Protocol):
    """Protected single-turn cloud advisory outlet."""

    def execute_cloud_turn(
        self,
        package: CloudRequestPackage,
        grant: CloudGrant,
        task_id: str,
        intent_id: str,
        turn: int,
    ) -> AdvisoryResult:
        """Run one checked and audited cloud advisory turn."""

    def record_denial(self, task_id: str, session_id: str, reason: str) -> None:
        """Record one minimal preflight cloud denial without a network turn."""


class EvolutionBackend(ABC):
    """Experience and skill lifecycle boundary."""

    @abstractmethod
    def reflect(self, task_context: dict) -> list[Experience]:
        """Extract candidate experiences from task context."""

    @abstractmethod
    def get_skills(self, intent: str) -> list[Skill]:
        """Return active skills relevant to an intent."""

    @abstractmethod
    def collect_experience(self, task: dict, outcome: str) -> None:
        """Record a task outcome for future reflection."""


class RuntimeEventSink(ABC):
    """Replaceable outlet for sanitized runtime events."""

    @abstractmethod
    def emit(self, event: RuntimeEvent) -> None:
        """Consume an event without affecting the application flow."""
