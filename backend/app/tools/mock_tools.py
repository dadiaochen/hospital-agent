from __future__ import annotations

from typing import Any

from pydantic import Field

from app.tools.tool_registry import ToolRegistry
from app.tools.tool_schemas import ToolContractModel, ToolSpec


class MockToolInput(ToolContractModel):
    member_id: str = Field(min_length=1)


class MockToolOutput(ToolContractModel):
    source_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    evidence_present: bool = True
    member_id: str = Field(min_length=1)
    payload: dict[str, Any]


def register_mock_read_tool(registry: ToolRegistry, name: str) -> None:
    registry.register(
        ToolSpec(
            name=name,
            description=f"Deterministic mock read tool for {name}.",
            input_schema=MockToolInput,
            output_schema=MockToolOutput,
            permission_scope="mock:read",
            read_only=True,
        ),
        lambda tool_input, _context: {
            "source_id": f"mock:{name}:{tool_input.member_id}",
            "source_name": name,
            "evidence_present": True,
            "member_id": tool_input.member_id,
            "payload": {},
        },
    )


__all__ = ["MockToolInput", "MockToolOutput", "register_mock_read_tool"]
