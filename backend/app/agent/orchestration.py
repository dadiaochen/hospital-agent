"""One-shot planning and bounded DAG supervision for 4D-B2.2.

This module is intentionally a small deterministic orchestration kernel.  It
does not call an LLM, database, HTTP API, Tool Registry, or LangGraph.  Those
integrations belong to the business graph; this layer proves route, dependency,
bounded fan-out/fan-in, retry, degradation, and termination contracts.
"""

from __future__ import annotations

from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor

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
    ContextMode,
    DependencyEdge,
    DomainAgentRole,
    EvalRuntimeOptions,
    ExecutionMode,
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
_READ_ONLY_TOOLS = frozenset(
    {
        "query_health_profile",
        "query_prescriptions",
        "query_medicine_box",
        "check_pharmacy_inventory",
        "search_safety_knowledge",
    }
)


class DeterministicTaskPlanner:
    """Create one bounded plan and never mutate it during execution."""

    def __init__(self, *, max_steps: int = 3, max_parallelism: int = 3) -> None:
        if not 1 <= max_steps <= 3:
            raise ValueError("max_steps must be between 1 and 3")
        if not 1 <= max_parallelism <= 3:
            raise ValueError("max_parallelism must be between 1 and 3")
        self.max_steps = max_steps
        self.max_parallelism = max_parallelism

    def plan(self, route: ComplexityRoute) -> TaskPlan:
        if route.route_mode != "complex_cross_domain" or not route.requires_planner:
            raise ValueError("TaskPlanner only accepts complex routes")
        if len(route.target_roles) > self.max_steps:
            raise ValueError("route contains more roles than the planner bound")

        ordered_roles = _topological_roles(route)
        role_to_step_id = {
            role: f"step_{index}"
            for index, role in enumerate(ordered_roles, start=1)
        }
        dependencies_by_role: dict[DomainAgentRole, tuple[str, ...]] = {
            role: tuple(
                role_to_step_id[hint.upstream_role]
                for hint in route.dependency_hints
                if hint.downstream_role == role
            )
            for role in ordered_roles
        }

        steps: list[PlanStep] = []
        for index, role in enumerate(ordered_roles, start=1):
            allowed_tools = tuple(allowed_tools_for_role(role))
            steps.append(
                PlanStep(
                    step_id=f"step_{index}",
                    role=role,
                    objective=_OBJECTIVES[role],
                    dependencies=dependencies_by_role[role],
                    # A full role allowlist can include a draft/write tool.
                    # Marking that step read-only would allow unsafe fan-out;
                    # explicit read-only plans can still be constructed for
                    # offline DAG tests with a narrower allowlist.
                    read_only=all(tool in _READ_ONLY_TOOLS for tool in allowed_tools),
                    allowed_tools=allowed_tools,
                    required_source_types=("tool_evidence",),
                )
            )

        return TaskPlan(
            task_id=route.task_id,
            user_id=route.user_id,
            member_id=route.member_id,
            intent=route.intent,
            steps=tuple(steps),
            max_steps=self.max_steps,
            dependency_edges=tuple(
                DependencyEdge(
                    upstream_step_id=dependency,
                    downstream_step_id=step.step_id,
                )
                for step in steps
                for dependency in step.dependencies
            ),
            max_parallelism=min(self.max_parallelism, len(steps)),
        )


def _topological_roles(route: ComplexityRoute) -> tuple[DomainAgentRole, ...]:
    """Order hinted roles before their dependants without changing the route.

    The route preserves the Router's signal order for auditability.  The
    Planner is the first component allowed to turn that set into execution
    order.  A cycle is intentionally left for ``TaskPlan`` to reject with its
    normal acyclic-DAG validation error.
    """

    roles = list(route.target_roles)
    dependencies = {role: set() for role in roles}
    for hint in route.dependency_hints:
        dependencies[hint.downstream_role].add(hint.upstream_role)

    ordered: list[DomainAgentRole] = []
    remaining = set(roles)
    while remaining:
        ready = [
            role
            for role in roles
            if role in remaining and dependencies[role].issubset(ordered)
        ]
        if not ready:
            return tuple(roles)
        ordered.extend(ready)
        remaining.difference_update(ready)
    return tuple(ordered)


class DeterministicBoundedSupervisor:
    """Execute a frozen plan with bounded, deterministic fan-out/fan-in.

    The parallel branch only invokes domain agents whose plan steps are both
    dependency-ready and marked ``read_only``. Results are collected in plan
    order, so completion timing cannot change the reducer output.
    """

    def __init__(
        self,
        *,
        router: DeterministicComplexityRouter | None = None,
        planner: DeterministicTaskPlanner | None = None,
        agents: Mapping[DomainAgentRole, DomainAgent] | None = None,
        max_supervisor_steps: int = 3,
        max_role_calls: int = 2,
        max_parallelism: int = 3,
        execution_mode: ExecutionMode = "parallel",
        context_mode: ContextMode = "dependency_only",
    ) -> None:
        if not 1 <= max_supervisor_steps <= 3:
            raise ValueError("max_supervisor_steps must be between 1 and 3")
        if not 1 <= max_role_calls <= 3:
            raise ValueError("max_role_calls must be between 1 and 3")
        if not 1 <= max_parallelism <= 3:
            raise ValueError("max_parallelism must be between 1 and 3")

        self.router = router or DeterministicComplexityRouter()
        self.planner = planner or DeterministicTaskPlanner()
        self.agents = dict(agents or build_domain_agent_registry())
        self.max_supervisor_steps = max_supervisor_steps
        self.max_role_calls = max_role_calls
        self.max_parallelism = max_parallelism
        self.execution_mode = execution_mode
        self.context_mode = context_mode

        expected_roles = {"TriageAgent", "MedicationAgent", "ReportAgent"}
        if set(self.agents) != expected_roles:
            raise ValueError("Supervisor registry must contain exactly three domain roles")

    def run(
        self,
        request: ComplexityRoutingRequest,
        *,
        runtime_options: EvalRuntimeOptions | None = None,
        execution_mode: ExecutionMode | None = None,
        context_mode: ContextMode | None = None,
    ) -> OrchestrationRunResult:
        """Route and execute one request within server-owned bounds."""

        if runtime_options is not None and (
            execution_mode is not None or context_mode is not None
        ):
            raise ValueError("runtime_options cannot be combined with mode overrides")
        if runtime_options is None:
            effective_context_mode = context_mode or self.context_mode
            runtime_options = EvalRuntimeOptions(
                execution_mode=execution_mode or self.execution_mode,
                context_mode=effective_context_mode,
            )

        route = self.router.route(request)
        if route.route_mode == "simple_single_domain":
            return self._run_simple(request, route, runtime_options)

        plan = self.planner.plan(route)
        return self._run_complex(request, route, plan, runtime_options)

    def _run_simple(
        self,
        request: ComplexityRoutingRequest,
        route: ComplexityRoute,
        runtime_options: EvalRuntimeOptions,
    ) -> OrchestrationRunResult:
        assert route.target_role is not None
        step = PlanStep(
            step_id="direct",
            role=route.target_role,
            objective=_OBJECTIVES[route.target_role],
            read_only=all(
                tool in _READ_ONLY_TOOLS
                for tool in allowed_tools_for_role(route.target_role)
            ),
            allowed_tools=tuple(allowed_tools_for_role(route.target_role)),
        )
        result = self._execute_step(
            request=request,
            route=route,
            step=step,
            prior_results=(),
            attempt=1,
            context_mode=runtime_options.context_mode,
        )
        return OrchestrationRunResult(
            request=request,
            route=route,
            results=(result,),
            completed=result.status in {"completed", "degraded"},
            termination_reason=_termination_for_result(result, prefix="direct"),
            steps_executed=1,
            execution_mode=runtime_options.execution_mode,
            context_mode=runtime_options.context_mode,
        )

    def _run_complex(
        self,
        request: ComplexityRoutingRequest,
        route: ComplexityRoute,
        plan: TaskPlan,
        runtime_options: EvalRuntimeOptions,
    ) -> OrchestrationRunResult:
        results: list[AgentTaskResult] = []
        decisions: list[SupervisorDecision] = []
        completed_steps: set[str] = set()
        results_by_step: dict[str, AgentTaskResult] = {}
        role_calls: dict[DomainAgentRole, int] = {}
        pending_steps = {step.step_id: step for step in plan.steps}
        parallel_batches: list[tuple[str, ...]] = []
        degraded = False
        terminal_failure = False

        while pending_steps:
            ready_steps = tuple(
                step
                for step in plan.steps
                if step.step_id in pending_steps
                and set(step.dependencies).issubset(completed_steps)
            )
            if not ready_steps:
                return self._stopped_run(
                    request,
                    route,
                    plan,
                    results,
                    decisions,
                    "step_dependency_not_satisfied",
                    runtime_options=runtime_options,
                    parallel_batches=parallel_batches,
                )

            remaining_capacity = self.max_supervisor_steps - len(results)
            if remaining_capacity <= 0:
                return self._stopped_run(
                    request,
                    route,
                    plan,
                    results,
                    decisions,
                    "max_supervisor_steps_exceeded",
                    step=ready_steps[0],
                    runtime_options=runtime_options,
                    parallel_batches=parallel_batches,
                )

            batch = self._select_batch(
                ready_steps,
                plan=plan,
                runtime_options=runtime_options,
                capacity=remaining_capacity,
            )
            if runtime_options.execution_mode == "parallel" and len(batch) > 1:
                parallel_batches.append(tuple(step.step_id for step in batch))

            for step in batch:
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
                        runtime_options=runtime_options,
                        parallel_batches=parallel_batches,
                    )

                decisions.append(
                    SupervisorDecision(
                        action="call_role",
                        step_id=step.step_id,
                        role=step.role,
                        reason=(
                            "dependency_satisfied_parallel_batch"
                            if len(batch) > 1
                            else "dependency_satisfied"
                        ),
                        max_steps=self.max_supervisor_steps,
                    )
                )

            batch_results = self._execute_batch(
                request=request,
                route=route,
                batch=batch,
                results=results,
                results_by_step=results_by_step,
                runtime_options=runtime_options,
            )

            # Results are already returned in frozen plan order, regardless of
            # which worker finished first. This is the deterministic reducer.
            for step, result in zip(batch, batch_results, strict=True):
                results.append(result)
                role_calls[step.role] = role_calls.get(step.role, 0) + 1

            for step, result in zip(batch, batch_results, strict=True):
                if result.status in {"blocked", "failed"}:
                    attempt = result.attempt
                    can_retry = (
                        result.retryable
                        and attempt < 3
                        and len(results) < self.max_supervisor_steps
                        and role_calls[step.role] < self.max_role_calls
                    )
                    while can_retry:
                        attempt += 1
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
                            prior_results=self._context_for_step(
                                step,
                                results=results,
                                results_by_step=results_by_step,
                                runtime_options=runtime_options,
                            ),
                            attempt=attempt,
                            context_mode=runtime_options.context_mode,
                        )
                        results.append(result)
                        role_calls[step.role] = role_calls.get(step.role, 0) + 1
                        can_retry = (
                            result.status in {"blocked", "failed"}
                            and result.retryable
                            and attempt < 3
                            and len(results) < self.max_supervisor_steps
                            and role_calls[step.role] < self.max_role_calls
                        )

                    if result.status in {"blocked", "failed"}:
                        decisions.append(
                            SupervisorDecision(
                                action="degrade",
                                step_id=step.step_id,
                                role=step.role,
                                reason=(
                                    "agent returned a terminal failure; continue only "
                                    "with dependency-independent pending steps"
                                ),
                                termination_reason=(
                                    result.failure_reason or "agent_failed"
                                ),
                                max_steps=self.max_supervisor_steps,
                            )
                        )
                        # Preserve the failure in the reducer, but release
                        # this step from the pending set.  A sibling step with
                        # satisfied dependencies may still provide the
                        # read-only evidence required to finish a bounded
                        # cross-domain run.  Dependent steps remain blocked by
                        # the unchanged ``completed_steps`` set.
                        terminal_failure = True
                        pending_steps.pop(step.step_id, None)
                        continue

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
                        runtime_options=runtime_options,
                        parallel_batches=parallel_batches,
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

                results_by_step[step.step_id] = result
                completed_steps.add(step.step_id)
                pending_steps.pop(step.step_id, None)

        termination_reason = (
            "completed_with_partial_failure"
            if terminal_failure
            else "completed_with_degradation"
            if degraded
            else "all_plan_steps_completed"
        )
        decisions.append(
            SupervisorDecision(
                action="finish",
                reason=(
                    "independent steps completed after a bounded terminal failure"
                    if terminal_failure
                    else "all frozen plan steps completed"
                ),
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
            completed=not terminal_failure,
            termination_reason=termination_reason,
            runtime_options=runtime_options,
            parallel_batches=parallel_batches,
        )

    def _select_batch(
        self,
        ready_steps: tuple[PlanStep, ...],
        *,
        plan: TaskPlan,
        runtime_options: EvalRuntimeOptions,
        capacity: int,
    ) -> tuple[PlanStep, ...]:
        """Select one safe batch without changing the frozen plan."""

        if runtime_options.execution_mode == "serial":
            return (ready_steps[0],)

        parallel_limit = min(
            self.max_parallelism,
            plan.max_parallelism,
            capacity,
        )
        if parallel_limit <= 1:
            return (ready_steps[0],)

        # A write-capable step is deliberately isolated. In this phase the
        # planner emits read-only steps, but the rule is enforced for custom
        # plans and future business write steps too.
        if not self._is_parallel_safe(ready_steps[0]):
            return (ready_steps[0],)

        batch: list[PlanStep] = []
        roles: set[DomainAgentRole] = set()
        for step in ready_steps:
            if not self._is_parallel_safe(step) or step.role in roles:
                continue
            batch.append(step)
            roles.add(step.role)
            if len(batch) == parallel_limit:
                break
        return tuple(batch) or (ready_steps[0],)

    @staticmethod
    def _is_parallel_safe(step: PlanStep) -> bool:
        declared_tools = set(step.allowed_tools or allowed_tools_for_role(step.role))
        return step.read_only and declared_tools.issubset(_READ_ONLY_TOOLS)

    def _execute_batch(
        self,
        *,
        request: ComplexityRoutingRequest,
        route: ComplexityRoute,
        batch: tuple[PlanStep, ...],
        results: list[AgentTaskResult],
        results_by_step: Mapping[str, AgentTaskResult],
        runtime_options: EvalRuntimeOptions,
    ) -> tuple[AgentTaskResult, ...]:
        def execute(step: PlanStep) -> AgentTaskResult:
            return self._execute_step(
                request=request,
                route=route,
                step=step,
                prior_results=self._context_for_step(
                    step,
                    results=results,
                    results_by_step=results_by_step,
                    runtime_options=runtime_options,
                ),
                attempt=1,
                context_mode=runtime_options.context_mode,
            )

        if len(batch) == 1:
            return (execute(batch[0]),)

        with ThreadPoolExecutor(
            max_workers=len(batch),
            thread_name_prefix="bounded-agent",
        ) as pool:
            futures = {step.step_id: pool.submit(execute, step) for step in batch}
            return tuple(futures[step.step_id].result() for step in batch)

    @staticmethod
    def _context_for_step(
        step: PlanStep,
        *,
        results: list[AgentTaskResult],
        results_by_step: Mapping[str, AgentTaskResult],
        runtime_options: EvalRuntimeOptions,
    ) -> tuple[AgentTaskResult, ...]:
        if runtime_options.context_mode == "all_history":
            # This is structured synthetic history, never raw conversation.
            return tuple(results)
        return tuple(
            results_by_step[dependency]
            for dependency in step.dependencies
            if dependency in results_by_step
        )

    def _execute_step(
        self,
        *,
        request: ComplexityRoutingRequest,
        route: ComplexityRoute,
        step: PlanStep,
        prior_results: tuple[AgentTaskResult, ...],
        attempt: int,
        context_mode: ContextMode,
    ) -> AgentTaskResult:
        agent = self.agents[step.role]
        allowed_tools = step.allowed_tools or allowed_tools_for_role(step.role)
        agent_input = DomainAgentInput(
            route=route,
            step=step,
            user_input_summary=request.user_input,
            allowed_tools=allowed_tools,
            prior_results=prior_results,
            context_mode=context_mode,
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
        runtime_options: EvalRuntimeOptions,
        parallel_batches: list[tuple[str, ...]],
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
            runtime_options=runtime_options,
            parallel_batches=parallel_batches,
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
        runtime_options: EvalRuntimeOptions,
        parallel_batches: list[tuple[str, ...]],
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
            execution_mode=runtime_options.execution_mode,
            context_mode=runtime_options.context_mode,
            parallel_batches=tuple(tuple(batch) for batch in parallel_batches),
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
