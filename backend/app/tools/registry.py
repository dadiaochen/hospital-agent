from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field


class RetryPolicy(BaseModel):
    max_attempts: int = 1
    backoff_seconds: float = 0.0


class ToolDefinition(BaseModel):
    name: str
    description: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    permission_scope: str
    timeout: float = 10.0
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    requires_human_confirmation: bool = False

    model_config = {"arbitrary_types_allowed": True}


class ToolRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, ToolDefinition] = {}
        self._handlers: dict[str, Callable[..., Any]] = {}

    def register(self, definition: ToolDefinition, handler: Callable[..., Any]) -> None:
        self._definitions[definition.name] = definition
        self._handlers[definition.name] = handler

    def get_definition(self, name: str) -> ToolDefinition:
        return self._definitions[name]

    def list_definitions(self) -> list[ToolDefinition]:
        return list(self._definitions.values())


tool_registry = ToolRegistry()

