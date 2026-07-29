"""Tool registry contracts with side-effect-free package imports."""

from app.tools.tool_registry import ToolExecutionError, ToolHandler, ToolRegistry
from app.tools.tool_schemas import (
    RetryPolicy,
    ToolAttemptTrace,
    ToolExecutionContext,
    ToolPermissionScope,
    ToolResult,
    ToolSpec,
)


ToolDefinition = ToolSpec


__all__ = [
    "RetryPolicy",
    "ToolAttemptTrace",
    "ToolDefinition",
    "ToolExecutionContext",
    "ToolExecutionError",
    "ToolHandler",
    "ToolPermissionScope",
    "ToolRegistry",
    "ToolResult",
    "ToolSpec",
]
