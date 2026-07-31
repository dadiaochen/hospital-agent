import Link from "next/link";

import { StatusBadge } from "@/components/StatusBadge";
import type { AgentRunExecution } from "@/lib/api/types";
import { formatStatus } from "@/lib/format";

type AgentRunResultProps = {
  execution: AgentRunExecution;
  children?: React.ReactNode;
};

export function AgentRunResult({ execution, children }: AgentRunResultProps) {
  const { run, artifacts } = execution;
  const { run_trace: trace, safety_trace: safety } = artifacts;
  const waitingForConfirmation =
    run.status === "needs_confirmation" &&
    trace.final_answer.waiting_for_user_confirmation &&
    !safety.blocked;
  const continuationRun = Boolean(artifacts.resumed_from_run_id);
  const workflowState = getWorkflowState({
    blocked: safety.blocked,
    continuationRun,
    waitingForConfirmation,
    status: run.status,
  });

  return (
    <section className="grid gap-5 rounded-2xl border border-[#eadfca] bg-white p-5 shadow-sm sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge tone={statusTone(run.status)}>{formatStatus(run.status)}</StatusBadge>
          <StatusBadge tone={workflowState.tone}>{workflowState.code}</StatusBadge>
          <StatusBadge>{trace.intent}</StatusBadge>
          {execution.idempotent_replay ? <StatusBadge>幂等重放</StatusBadge> : null}
          {safety.blocked ? <StatusBadge tone="danger">安全拦截</StatusBadge> : null}
        </div>
        <Link
          className="text-sm font-semibold text-[#0f766e] hover:underline"
          href={`/agent-runs/${encodeURIComponent(run.id)}`}
        >
          查看完整 Trace
        </Link>
      </div>

      <WorkflowTimeline
        blocked={safety.blocked}
        continuationRun={continuationRun}
        waitingForConfirmation={waitingForConfirmation}
      />

      <div className="grid gap-3 rounded-xl border border-[#eadfca] bg-[#fffaf0] p-4 sm:grid-cols-3">
        <TraceIdentity label="task_id" value={artifacts.task_id} />
        <TraceIdentity label="本次 run_id" value={run.id} />
        <TraceIdentity
          label="续跑来源"
          value={artifacts.resumed_from_run_id ?? "尚未发生 continuation run"}
        />
      </div>

      <div className="rounded-xl bg-[#f3f8f6] p-4">
        <p className="text-xs font-bold uppercase tracking-[0.14em] text-[#52706b]">
          结构化答案
        </p>
        <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-[#243f3b]">
          {trace.final_answer.content || run.final_answer || "本次运行没有生成答案。"}
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ReferencePanel execution={execution} />
        <SafetyPanel execution={execution} />
      </div>

      {children}

      <div className="rounded-xl border border-[#dbe7e3] px-4 py-3 text-xs leading-5 text-[#64748b]">
        当前动作状态：<strong>{formatStatus(trace.final_answer.action_status)}</strong>。
        外部提交状态：<strong>{artifacts.external_action_status}</strong>。确认只记录本地草稿，
        不会自动购药、预约复诊或向外部系统发送提醒。
      </div>
    </section>
  );
}

function ReferencePanel({ execution }: { execution: AgentRunExecution }) {
  const { tool_evidence_refs: toolRefs, rag_source_refs: ragRefs } = execution.artifacts;
  return (
    <div className="rounded-xl border border-[#dbe7e3] p-4">
      <h3 className="font-bold text-[#31534f]">事实与规则来源</h3>
      {toolRefs.length === 0 && ragRefs.length === 0 ? (
        <p className="mt-2 text-sm text-[#7b8d89]">本次答案没有可展示的来源引用。</p>
      ) : (
        <ul className="mt-3 grid gap-2 text-sm text-[#475569]">
          {toolRefs.map((reference) => (
            <li className="rounded-lg bg-[#f7faf9] p-3" key={reference.source_id}>
              <strong>工具：</strong>{reference.tool_name}
              <SourceId value={reference.source_id} />
            </li>
          ))}
          {ragRefs.map((reference) => (
            <li className="rounded-lg bg-[#f7faf9] p-3" key={reference.source_id}>
              <strong>RAG：</strong>{reference.purpose}
              <SourceId value={reference.source_id} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SafetyPanel({ execution }: { execution: AgentRunExecution }) {
  const safety = execution.artifacts.safety_trace;
  return (
    <div className={`rounded-xl border p-4 ${safety.blocked ? "border-[#fecaca] bg-[#fff8f7]" : "border-[#fde68a] bg-[#fffbeb]"}`}>
      <h3 className="font-bold text-[#713f12]">安全与人工确认</h3>
      <p className="mt-2 text-sm leading-6 text-[#785a2f]">
        {safety.blocked
          ? "该请求已在执行前被 SafetyAgent 拦截，不会继续业务动作。"
          : safety.requires_human_confirmation
            ? "当前处于 DRAFT 待确认阶段。确认只会推进本地草稿流程，不会向医院、药店或通知服务提交动作。"
            : "本次运行未要求额外人工确认。"}
      </p>
      {safety.flags.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {safety.flags.map((flag) => (
            <StatusBadge key={flag} tone="warning">{flag}</StatusBadge>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function WorkflowTimeline({
  blocked,
  continuationRun,
  waitingForConfirmation,
}: {
  blocked: boolean;
  continuationRun: boolean;
  waitingForConfirmation: boolean;
}) {
  const steps = [
    { label: "首次 run", complete: true, current: false },
    { label: "生成 DRAFT", complete: !blocked, current: waitingForConfirmation },
    { label: "用户确认", complete: continuationRun, current: waitingForConfirmation },
    { label: "continuation run", complete: continuationRun, current: false },
    { label: "本地记录完成", complete: continuationRun, current: false },
  ];

  return (
    <section aria-label="Agent 任务生命周期" className="rounded-2xl border border-[#dbe7e3] bg-[#fbfdfc] p-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <p className="text-xs font-black uppercase tracking-[0.14em] text-[#0f766e]">Task Lifecycle</p>
          <h3 className="mt-1 font-bold text-[#173c38]">首次运行到本地完成</h3>
        </div>
        <p className="text-xs text-[#71847f]">
          {blocked ? "流程在安全门禁处停止" : waitingForConfirmation ? "等待你的明确确认" : continuationRun ? "确认已产生新的 run" : "运行状态已冻结"}
        </p>
      </div>
      <ol className="mt-4 grid gap-2 sm:grid-cols-5">
        {steps.map((step, index) => (
          <li className="flex items-center gap-2 sm:block" key={step.label}>
            <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-full text-xs font-black ${step.complete ? "bg-[#dff3ed] text-[#0f766e]" : step.current ? "bg-[#fff0c2] text-[#9a670e]" : "bg-[#eef3f2] text-[#8b9b95]"}`}>
              {step.complete ? "完成" : step.current ? "当前" : String(index + 1)}
            </span>
            <span className={`text-xs font-semibold sm:mt-2 sm:block ${step.complete ? "text-[#31534f]" : step.current ? "text-[#9a670e]" : "text-[#8b9b95]"}`}>
              {step.label}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function TraceIdentity({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs font-semibold text-[#71847f]">{label}</p>
      <p className="mt-1 break-all font-mono text-xs text-[#334155]">{value}</p>
    </div>
  );
}

function getWorkflowState({
  blocked,
  continuationRun,
  waitingForConfirmation,
  status,
}: {
  blocked: boolean;
  continuationRun: boolean;
  waitingForConfirmation: boolean;
  status: string;
}): { code: string; tone: "neutral" | "success" | "warning" | "danger" } {
  if (blocked || status === "blocked") return { code: "BLOCKED", tone: "danger" };
  if (waitingForConfirmation) return { code: "DRAFT", tone: "warning" };
  if (continuationRun && status === "completed") return { code: "LOCAL_COMPLETED", tone: "success" };
  return { code: status.toUpperCase(), tone: "neutral" };
}

function SourceId({ value }: { value: string }) {
  return <p className="mt-1 break-all font-mono text-[11px] text-[#71847f]">source_id: {value}</p>;
}

function statusTone(status: string): "neutral" | "success" | "warning" | "danger" {
  if (status === "completed") return "success";
  if (status === "failed" || status === "blocked") return "danger";
  if (status === "needs_confirmation") return "warning";
  return "neutral";
}
