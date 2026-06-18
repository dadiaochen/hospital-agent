"""Backward-compatible exports for the tool registry package."""

from app.tools.tool_registry import ToolExecutionError, ToolRegistry
from app.tools.tool_schemas import (
    RetryPolicy,
    ToolExecutionContext,
    ToolResult,
    ToolSpec,
)

ToolDefinition = ToolSpec
tool_registry = ToolRegistry()

__all__ = [
    "RetryPolicy",
    "ToolDefinition",
    "ToolExecutionContext",
    "ToolExecutionError",
    "ToolRegistry",
    "ToolResult",
    "ToolSpec",
    "tool_registry",
]

