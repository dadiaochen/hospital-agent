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

  return (
    <section className="grid gap-4 rounded-2xl border border-[#cfe0db] bg-white p-5 shadow-sm sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge tone={statusTone(run.status)}>{formatStatus(run.status)}</StatusBadge>
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
            ? "该动作需要你明确确认后，才会创建本地草稿。"
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

function SourceId({ value }: { value: string }) {
  return <p className="mt-1 break-all font-mono text-[11px] text-[#71847f]">source_id: {value}</p>;
}

function statusTone(status: string): "neutral" | "success" | "warning" | "danger" {
  if (status === "completed") return "success";
  if (status === "failed" || status === "blocked") return "danger";
  if (status === "needs_confirmation") return "warning";
  return "neutral";
}
