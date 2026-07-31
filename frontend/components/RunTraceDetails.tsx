import { StatusBadge } from "@/components/StatusBadge";
import type { AgentRun, AgentRunArtifacts, AgentToolCall } from "@/lib/api/types";
import { formatDateTime, formatStatus } from "@/lib/format";

type RunTraceDetailsProps = {
  run: AgentRun;
  artifacts: AgentRunArtifacts;
  toolCalls: AgentToolCall[];
};

export function RunTraceDetails({ run, artifacts, toolCalls }: RunTraceDetailsProps) {
  const evaluation = artifacts.evaluation_result;
  const modelTrace = artifacts.model_call_trace;

  return (
    <div className="grid gap-5">
      <section className="rounded-2xl border border-[#dbe7e3] bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge tone={run.status === "completed" ? "success" : run.status === "failed" ? "danger" : "warning"}>
            {formatStatus(run.status)}
          </StatusBadge>
          <StatusBadge>{artifacts.run_trace.intent}</StatusBadge>
          <StatusBadge>{artifacts.run_trace.latency_ms} ms</StatusBadge>
        </div>
        <h3 className="mt-4 text-lg font-bold text-[#173c38]">冻结最终答案</h3>
        <p className="mt-2 whitespace-pre-wrap rounded-xl bg-[#f3f8f6] p-4 text-sm leading-7 text-[#334155]">
          {artifacts.run_trace.final_answer.content}
        </p>
        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <TraceField label="run_id" value={run.id} mono />
          <TraceField label="task_id" value={artifacts.task_id} mono />
          <TraceField label="开始时间" value={formatDateTime(run.started_at)} />
          <TraceField label="步骤数" value={String(run.step_count)} />
        </dl>
      </section>

      <section className="rounded-2xl border border-[#dbe7e3] bg-white p-5 shadow-sm">
        <h3 className="text-lg font-bold text-[#173c38]">角色与工具调用</h3>
        {toolCalls.length === 0 ? (
          <p className="mt-3 text-sm text-[#71847f]">本次运行没有工具调用。</p>
        ) : (
          <div className="mt-4 grid gap-3">
            {toolCalls.map((call) => (
              <article className="rounded-xl border border-[#e1ebe7] p-4" key={call.id}>
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge>{call.agent_role}</StatusBadge>
                  <strong className="text-sm text-[#31534f]">{call.tool_name}</strong>
                  <StatusBadge tone={call.success ? "success" : "danger"}>{call.success ? "成功" : "失败"}</StatusBadge>
                  <StatusBadge tone={call.schema_valid ? "success" : "danger"}>Schema {call.schema_valid ? "有效" : "无效"}</StatusBadge>
                  <span className="text-xs text-[#71847f]">{call.latency_ms === null ? "未记录耗时" : `${call.latency_ms} ms`}</span>
                </div>
                {call.error_type || call.error_message || call.fallback_action ? (
                  <div className="mt-3 rounded-lg bg-[#fff8f7] p-3 text-sm leading-6 text-[#7f1d1d]">
                    {call.error_type ? <p>错误类型：{call.error_type}</p> : null}
                    {call.error_message ? <p>错误信息：{call.error_message}</p> : null}
                    {call.fallback_action ? <p>Fallback：{call.fallback_action}</p> : null}
                  </div>
                ) : null}
                <details className="mt-3 text-xs text-[#64748b]">
                  <summary className="cursor-pointer font-semibold">查看脱敏输入/输出</summary>
                  <pre className="mt-2 overflow-x-auto rounded-lg bg-[#f7faf9] p-3">{JSON.stringify({ input: call.tool_input, output: call.tool_output }, null, 2)}</pre>
                </details>
              </article>
            ))}
          </div>
        )}
      </section>

      <div className="grid gap-5 xl:grid-cols-2">
        <section className="rounded-2xl border border-[#dbe7e3] bg-white p-5 shadow-sm">
          <h3 className="text-lg font-bold text-[#173c38]">来源与安全</h3>
          <TraceList empty="无工具证据引用" items={artifacts.tool_evidence_refs.map((item) => `${item.tool_name} · ${item.source_id}`)} title="Tool Evidence" />
          <TraceList empty="无 RAG 来源引用" items={artifacts.rag_source_refs.map((item) => `${item.purpose} · ${item.source_id}`)} title="RAG Sources" />
          <TraceList empty="无安全标记" items={artifacts.safety_trace.flags} title={`SafetyAgent · ${artifacts.safety_trace.blocked ? "已拦截" : "未拦截"}`} />
        </section>

        <section className="rounded-2xl border border-[#dbe7e3] bg-white p-5 shadow-sm">
          <h3 className="text-lg font-bold text-[#173c38]">EvaluationResult</h3>
          <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
            <Metric label="Task success" value={yesNo(evaluation.task_success)} />
            <Metric label="Tool accuracy" value={score(evaluation.tool_call_accuracy)} />
            <Metric label="Groundedness" value={score(evaluation.groundedness)} />
            <Metric label="Schema valid" value={yesNo(evaluation.schema_valid)} />
            <Metric bad={evaluation.hallucination_detected} label="Hallucination" value={yesNo(evaluation.hallucination_detected)} />
            <Metric label="Safety recall" value={score(evaluation.safety_recall)} />
            <Metric label="Confirmation required" value={yesNo(evaluation.human_confirmation_required)} />
            <Metric label="Confirmation present" value={yesNo(evaluation.human_confirmation_present)} />
            <Metric label="Context isolation" value={yesNo(evaluation.context_isolation_passed)} />
          </dl>
          {evaluation.failure_reasons.length > 0 ? <TraceList empty="" items={evaluation.failure_reasons} title="Failure reasons" /> : <p className="mt-4 text-sm text-[#166534]">未记录评估失败原因。</p>}
        </section>
      </div>

      <section className="rounded-2xl border border-[#dbe7e3] bg-white p-5 shadow-sm">
        <h3 className="text-lg font-bold text-[#173c38]">模型网关 Trace</h3>
        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <TraceField label="请求 Provider" value={modelTrace.requested_provider} />
          <TraceField label="实际 Provider" value={modelTrace.effective_provider ?? "无"} />
          <TraceField label="Fallback" value={modelTrace.fallback_used ? modelTrace.fallback_reason ?? "是" : "否"} />
          <TraceField label="耗时" value={`${modelTrace.latency_ms} ms`} />
        </dl>
        <p className="mt-4 rounded-xl border border-[#dbe7e3] px-4 py-3 text-xs leading-5 text-[#64748b]">
          外部动作状态：<strong>{artifacts.external_action_status}</strong>。该 Trace 只读，Evaluator 不会修改最终答案或业务状态。
        </p>
      </section>
    </div>
  );
}

function TraceField({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return <div><dt className="text-xs font-semibold text-[#71847f]">{label}</dt><dd className={`mt-1 break-all text-[#334155] ${mono ? "font-mono text-[11px]" : ""}`}>{value}</dd></div>;
}

function TraceList({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return <div className="mt-4"><h4 className="text-sm font-bold text-[#45615d]">{title}</h4>{items.length > 0 ? <ul className="mt-2 grid gap-2">{items.map((item, index) => <li className="break-all rounded-lg bg-[#f7faf9] p-3 font-mono text-xs text-[#52706b]" key={`${item}-${index}`}>{item}</li>)}</ul> : <p className="mt-2 text-sm text-[#94a3b8]">{empty}</p>}</div>;
}

function Metric({ label, value, bad = false }: { label: string; value: string; bad?: boolean }) {
  return <div className={`rounded-xl p-3 ${bad ? "bg-[#fff1f2]" : "bg-[#f7faf9]"}`}><dt className="text-xs font-semibold text-[#71847f]">{label}</dt><dd className="mt-1 font-bold text-[#31534f]">{value}</dd></div>;
}

function score(value: number | null): string {
  return value === null ? "N/A" : value.toFixed(2);
}

function yesNo(value: boolean): string {
  return value ? "是" : "否";
}
