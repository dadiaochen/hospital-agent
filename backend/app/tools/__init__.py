"""Tool registry contracts and deterministic mock tools."""

from app.tools.mock_tools import build_mock_tool_registry, register_mock_tools
from app.tools.tool_registry import ToolHandler, ToolRegistry
from app.tools.tool_schemas import (
    RetryPolicy,
    ToolExecutionContext,
    ToolPermissionScope,
    ToolResult,
    ToolSpec,
)


ToolDefinition = ToolSpec


__all__ = [
    "RetryPolicy",
    "ToolDefinition",
    "ToolExecutionContext",
    "ToolHandler",
    "ToolPermissionScope",
    "ToolRegistry",
    "ToolResult",
    "ToolSpec",
    "build_mock_tool_registry",
    "register_mock_tools",
]
