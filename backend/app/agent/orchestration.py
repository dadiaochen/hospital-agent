"""One-shot planning and serial bounded supervision for 4B task six.

This module is intentionally a small deterministic orchestration kernel.  It
does not call an LLM, database, HTTP API, Tool Registry, or LangGraph.  Those
integrations belong to later roadmap tasks; this layer proves the route,
dependency, retry, degradation, and termination contracts first.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.agent.complexity_router import DeterministicComplexityRouter
from app.agent.domain_agents import (
    DomainAgent,
    DomainAgentInput,
    allowed_tools_for_role,
    build_domain_agent_registry,
)
from app.agent.orchestration_schemas import (
    AgentTaskResult,
    ComplexityRoute,
    ComplexityRoutingRequest,
    DomainAgentRole,
    OrchestrationRunResult,
    PlanStep,
    SupervisorDecision,
    TaskPlan,
)


_OBJECTIVES: dict[DomainAgentRole, str] = {
    "TriageAgent": "Structure triage information and identify missing request slots.",
    "MedicationAgent": "Prepare medication workflow facts and draft requirements.",
    "ReportAgent": "Structure report work and identify source-backed explanation needs.",
}


class DeterministicTaskPlanner:
    """Create one bounded plan and never mutate it during execution."""

    def __init__(self, *, max_steps: int = 3) -> None:
        if not 1 <= max_steps <= 3:
            raise ValueError("max_steps must be between 1 and 3")
        self.max_steps = max_steps

    def plan(self, route: ComplexityRoute) -> TaskPlan:
        if route.route_mode != "complex_cross_domain" or not route.requires_planner:
            raise ValueError("TaskPlanner only accepts complex routes")
        if len(route.target_roles) > self.max_steps:
            raise ValueError("route contains more roles than the planner bound")

        steps: list[PlanStep] = []
        for index, role in enumerate(route.target_roles, start=1):
            dependencies = (steps[-1].step_id,) if steps else ()
            steps.append(
                PlanStep(
                    step_id=f"step_{index}",
                    role=role,
                    objective=_OBJECTIVES[role],
                    dependencies=dependencies,
                )
            )

        return TaskPlan(
            task_id=route.task_id,
            user_id=route.user_id,
            member_id=route.member_id,
            intent=route.intent,
            steps=tuple(steps),
            max_steps=self.max_steps,
        )


class DeterministicBoundedSupervisor:
    """Execute a frozen plan serially with a hard invocation limit."""

    def __init__(
        self,
        *,
        router: DeterministicComplexityRouter | None = None,
        planner: DeterministicTaskPlanner | None = None,
        agents: Mapping[DomainAgentRole, DomainAgent] | None = None,
        max_supervisor_steps: int = 3,
        max_role_calls: int = 2,
    ) -> None:
        if not 1 <= max_supervisor_steps <= 3:
            raise ValueError("max_supervisor_steps must be between 1 and 3")
        if not 1 <= max_role_calls <= 3:
            raise ValueError("max_role_calls must be between 1 and 3")

        self.router = router or DeterministicComplexityRouter()
        self.planner = planner or DeterministicTaskPlanner()
        self.agents = dict(agents or build_domain_agent_registry())
        self.max_supervisor_steps = max_supervisor_steps
        self.max_role_calls = max_role_calls

        expected_roles = {"TriageAgent", "MedicationAgent", "ReportAgent"}
        if set(self.agents) != expected_roles:
            raise ValueError("Supervisor registry must contain exactly three domain roles")

    def run(self, request: ComplexityRoutingRequest) -> OrchestrationRunResult:
        """Route and execute exactly one request within the configured bound."""

        route = self.router.route(request)
        if route.route_mode == "simple_single_domain":
            return self._run_simple(request, route)

        plan = self.planner.plan(route)
        return self._run_complex(request, route, plan)

    def _run_simple(
        self,
        request: ComplexityRoutingRequest,
        route: ComplexityRoute,
    ) -> OrchestrationRunResult:
        assert route.target_role is not None
        step = PlanStep(
            step_id="direct",
            role=route.target_role,
            objective=_OBJECTIVES[route.target_role],
        )
        result = self._execute_step(
            request=request,
            route=route,
            step=step,
            prior_results=(),
            attempt=1,
        )
        return OrchestrationRunResult(
            request=request,
            route=route,
            results=(result,),
            completed=result.status in {"completed", "degraded"},
            termination_reason=_termination_for_result(result, prefix="direct"),
            steps_executed=1,
        )

    def _run_complex(
        self,
        request: ComplexityRoutingRequest,
        route: ComplexityRoute,
        plan: TaskPlan,
    ) -> OrchestrationRunResult:
        results: list[AgentTaskResult] = []
        decisions: list[SupervisorDecision] = []
        completed_steps: set[str] = set()
        role_calls: dict[DomainAgentRole, int] = {}
        degraded = False

        for step in plan.steps:
            if not set(step.dependencies).issubset(completed_steps):
                return self._stopped_run(
                    request,
                    route,
                    plan,
                    results,
                    decisions,
                    "step_dependency_not_satisfied",
                )

            attempt = 1
            while True:
                if len(results) >= self.max_supervisor_steps:
                    return self._stopped_run(
                        request,
                        route,
                        plan,
                        results,
                        decisions,
                        "max_supervisor_steps_exceeded",
                        step=step,
                    )

                calls_for_role = role_calls.get(step.role, 0)
                if calls_for_role >= self.max_role_calls:
                    return self._stopped_run(
                        request,
                        route,
                        plan,
                        results,
                        decisions,
                        "max_role_calls_exceeded",
                        step=step,
                    )

                if attempt == 1:
                    decisions.append(
                        SupervisorDecision(
                            action="call_role",
                            step_id=step.step_id,
                            role=step.role,
                            reason="dependency_satisfied",
                            max_steps=self.max_supervisor_steps,
                        )
                    )
                else:
                    decisions.append(
                        SupervisorDecision(
                            action="retry",
                            step_id=step.step_id,
                            role=step.role,
                            reason="retryable_agent_failure",
                            retry_count=attempt - 1,
                            max_steps=self.max_supervisor_steps,
                        )
                    )

                result = self._execute_step(
                    request=request,
                    route=route,
                    step=step,
                    prior_results=tuple(results),
                    attempt=attempt,
                )
                results.append(result)
                role_calls[step.role] = calls_for_role + 1

                if result.status in {"blocked", "failed"}:
                    can_retry = (
                        result.retryable
                        and attempt < 3
                        and len(results) < self.max_supervisor_steps
                        and role_calls[step.role] < self.max_role_calls
                    )
                    if can_retry:
                        attempt += 1
                        continue
                    decisions.append(
                        SupervisorDecision(
                            action="stop",
                            step_id=step.step_id,
                            role=step.role,
                            reason="agent returned a terminal failure",
                            termination_reason=result.failure_reason or "agent_failed",
                            max_steps=self.max_supervisor_steps,
                        )
                    )
                    return self._result(
                        request,
                        route,
                        plan,
                        results,
                        decisions,
                        completed=False,
                        termination_reason=result.failure_reason or "agent_failed",
                    )

                if result.status == "needs_clarification":
                    decisions.append(
                        SupervisorDecision(
                            action="stop",
                            step_id=step.step_id,
                            role=step.role,
                            reason="agent requires user clarification",
                            termination_reason="needs_clarification",
                            max_steps=self.max_supervisor_steps,
                        )
                    )
                    return self._result(
                        request,
                        route,
                        plan,
                        results,
                        decisions,
                        completed=False,
                        termination_reason="needs_clarification",
                    )

                if result.status == "degraded":
                    degraded = True
                    decisions.append(
                        SupervisorDecision(
                            action="degrade",
                            step_id=step.step_id,
                            role=step.role,
                            reason="continue with the agent fallback result",
                            termination_reason="continue_with_fallback",
                            max_steps=self.max_supervisor_steps,
                        )
                    )

                completed_steps.add(step.step_id)
                break

        termination_reason = (
            "completed_with_degradation" if degraded else "all_plan_steps_completed"
        )
        decisions.append(
            SupervisorDecision(
                action="finish",
                reason="all frozen plan steps completed",
                termination_reason=termination_reason,
                max_steps=self.max_supervisor_steps,
            )
        )
        return self._result(
            request,
            route,
            plan,
            results,
            decisions,
            completed=True,
            termination_reason=termination_reason,
        )

    def _execute_step(
        self,
        *,
        request: ComplexityRoutingRequest,
        route: ComplexityRoute,
        step: PlanStep,
        prior_results: tuple[AgentTaskResult, ...],
        attempt: int,
    ) -> AgentTaskResult:
        agent = self.agents[step.role]
        agent_input = DomainAgentInput(
            route=route,
            step=step,
            user_input_summary=request.user_input,
            allowed_tools=allowed_tools_for_role(step.role),
            prior_results=prior_results,
        )
        result = agent.execute(agent_input)
        if result.task_id != request.task_id:
            raise ValueError("domain Agent returned a different task_id")
        if result.member_id != request.member_id:
            raise ValueError("domain Agent returned a different member_id")
        if result.agent_role != step.role:
            raise ValueError("domain Agent returned a different role")
        if result.step_id != step.step_id:
            raise ValueError("domain Agent returned a different step_id")
        if result.attempt != attempt:
            result = result.model_copy(update={"attempt": attempt})
        return result

    def _stopped_run(
        self,
        request: ComplexityRoutingRequest,
        route: ComplexityRoute,
        plan: TaskPlan,
        results: list[AgentTaskResult],
        decisions: list[SupervisorDecision],
        termination_reason: str,
        *,
        step: PlanStep | None = None,
    ) -> OrchestrationRunResult:
        if step is not None:
            decisions.append(
                SupervisorDecision(
                    action="stop",
                    step_id=step.step_id,
                    role=step.role,
                    reason="bounded Supervisor cannot continue",
                    termination_reason=termination_reason,
                    max_steps=self.max_supervisor_steps,
                )
            )
        else:
            decisions.append(
                SupervisorDecision(
                    action="stop",
                    reason="bounded Supervisor cannot continue",
                    termination_reason=termination_reason,
                    max_steps=self.max_supervisor_steps,
                )
            )
        return self._result(
            request,
            route,
            plan,
            results,
            decisions,
            completed=False,
            termination_reason=termination_reason,
        )

    @staticmethod
    def _result(
        request: ComplexityRoutingRequest,
        route: ComplexityRoute,
        plan: TaskPlan,
        results: list[AgentTaskResult],
        decisions: list[SupervisorDecision],
        *,
        completed: bool,
        termination_reason: str,
    ) -> OrchestrationRunResult:
        return OrchestrationRunResult(
            request=request,
            route=route,
            plan=plan,
            results=tuple(results),
            decisions=tuple(decisions),
            completed=completed,
            termination_reason=termination_reason,
            steps_executed=len(results),
            used_planner=True,
            used_supervisor=True,
        )


def _termination_for_result(result: AgentTaskResult, *, prefix: str) -> str:
    if result.status == "completed":
        return f"{prefix}_completed"
    if result.status == "degraded":
        return f"{prefix}_degraded"
    if result.status == "needs_clarification":
        return "needs_clarification"
    return result.failure_reason or f"{prefix}_{result.status}"


# Public names used in the architecture documents.  The deterministic class
# names remain available so tests and future model-assisted implementations can
# distinguish policy from provider-backed behavior.
TaskPlanner = DeterministicTaskPlanner
BoundedSupervisor = DeterministicBoundedSupervisor


__all__ = [
    "BoundedSupervisor",
    "DeterministicBoundedSupervisor",
    "DeterministicTaskPlanner",
    "TaskPlanner",
]
