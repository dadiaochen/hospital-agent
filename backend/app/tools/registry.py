"""Backward-compatible imports for the tool registry contract layer."""

from app.tools.tool_registry import ToolExecutionError, ToolHandler, ToolRegistry
from app.tools.tool_schemas import RetryPolicy, ToolExecutionContext, ToolResult, ToolSpec


ToolDefinition = ToolSpec
tool_registry = ToolRegistry()


__all__ = [
    "RetryPolicy",
    "ToolDefinition",
    "ToolExecutionContext",
    "ToolExecutionError",
    "ToolHandler",
    "ToolRegistry",
    "ToolResult",
    "ToolSpec",
    "tool_registry",
]
