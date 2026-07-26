import pytest
from pydantic import ValidationError

from app.schemas.business import BusinessRequestContext, SourceRef
from app.tools.tool_registry import ToolRegistry
from app.tools.tool_schemas import ToolExecutionContext, ToolSpec
from app.tools.tool_schemas import ToolContractModel


class EchoInput(ToolContractModel):
    value: str


class EchoOutput(ToolContractModel):
    value: str
    evidence_present: bool = False


def test_business_request_context_supports_three_domains_and_provider_modes() -> None:
    context = BusinessRequestContext(
        business_domain="health_record",
        provider_mode="sandbox",
        user_id="user-1",
        member_id="member-1",
    )

    assert context.business_domain == "health_record"
    assert context.provider_mode == "sandbox"


def test_document_source_requires_traceable_document_metadata() -> None:
    with pytest.raises(ValidationError):
        SourceRef(
            source_id="source-1",
            source_type="knowledge_base",
            document_id="doc-1",
            verified=True,
        )

    source = SourceRef(
        source_id="source-1",
        source_type="knowledge_base",
        document_id="doc-1",
        document_version="2026-07-24",
        chunk_id="chunk-2",
        retrieval_mode="hybrid",
        verified=True,
    )

    assert source.document_version == "2026-07-24"


def test_agent_inference_cannot_be_promoted_to_verified_fact() -> None:
    with pytest.raises(ValidationError):
        SourceRef(
            source_id="source-1",
            source_type="agent_inference",
            verified=True,
        )


def test_tool_result_propagates_contract_version_and_provider_mode() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="echo",
            tool_version="v2",
            description="Echo a value.",
            input_schema=EchoInput,
            output_schema=EchoOutput,
            permission_scope="test:echo",
            allowed_agent_roles=["Planner"],
        ),
        lambda payload, _: EchoOutput(value=payload.value),
    )
    execution_context = ToolExecutionContext(
        run_id="run-1",
        task_id="task-1",
        member_id="member-1",
        agent_role="Planner",
        allowed_tools=["echo"],
        provider_mode="sandbox",
    )

    result = registry.call("echo", {"value": "ok"}, execution_context)

    assert result.success is True
    assert result.tool_version == "v2"
    assert result.provider_mode == "sandbox"
    assert result.retryable is False
    assert result.evidence_refs == []
