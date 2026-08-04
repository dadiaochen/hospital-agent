import { StatusBadge } from "@/components/StatusBadge";
import type { AgentRunExecution } from "@/lib/api/types";

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
  const resultStatus = getResultStatus({
    blocked: safety.blocked,
    continuationRun,
    waitingForConfirmation,
    status: run.status,
  });

  return (
    <section className="grid gap-5 rounded-3xl border border-[#d9e8e2] bg-white p-5 shadow-[0_16px_45px_rgba(21,69,62,0.07)] sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#0f766e]">
            咨询结果
          </p>
          <h2 className="mt-2 text-2xl font-black tracking-tight text-[#173c38]">
            {resultStatus.title}
          </h2>
        </div>
        <StatusBadge tone={resultStatus.tone}>{resultStatus.label}</StatusBadge>
      </div>

      <div className="rounded-2xl bg-[#f3f8f6] p-5">
        <p className="text-sm font-bold text-[#31534f]">整理结果</p>
        <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-[#243f3b]">
          {toUserFacingAnswer({
            answer: trace.final_answer.content || run.final_answer,
            intent: run.intent,
          })}
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ReferencePanel execution={execution} />
        <SafetyPanel execution={execution} />
      </div>

      {children}
    </section>
  );
}

function ReferencePanel({ execution }: { execution: AgentRunExecution }) {
  const { tool_evidence_refs: toolRefs, rag_source_refs: ragRefs } = execution.artifacts;
  const referenceCount = toolRefs.length + ragRefs.length;
  return (
    <div className="rounded-2xl border border-[#dbe7e3] p-4">
      <h3 className="font-bold text-[#31534f]">参考信息</h3>
      {referenceCount === 0 ? (
        <p className="mt-2 text-sm leading-6 text-[#7b8d89]">这次整理暂时没有可展示的参考资料。</p>
      ) : (
        <div className="mt-3 flex flex-wrap gap-2 text-sm text-[#475569]">
          {toolRefs.length > 0 ? (
            <span className="rounded-full bg-[#f0f8f5] px-3 py-1.5">家庭健康记录 · {toolRefs.length} 项</span>
          ) : null}
          {ragRefs.length > 0 ? (
            <span className="rounded-full bg-[#f0f8f5] px-3 py-1.5">健康知识资料 · {ragRefs.length} 项</span>
          ) : null}
        </div>
      )}
    </div>
  );
}

function SafetyPanel({ execution }: { execution: AgentRunExecution }) {
  const safety = execution.artifacts.safety_trace;
  const waitingForConfirmation =
    execution.run.status === "needs_confirmation" &&
    safety.requires_human_confirmation;
  return (
    <div className={`rounded-2xl border p-4 ${safety.blocked ? "border-[#fecaca] bg-[#fff8f7]" : "border-[#fde68a] bg-[#fffbeb]"}`}>
      <h3 className="font-bold text-[#713f12]">安全提示</h3>
      <p className="mt-2 text-sm leading-6 text-[#785a2f]">
        {safety.blocked
          ? "这条请求涉及需要专业人员确认的内容，我先暂停处理。建议联系医生或药师。"
          : waitingForConfirmation
            ? "相关信息已经整理好，下一步需要你确认后才能继续。"
            : execution.run.status === "completed"
              ? "这次整理已经完成，可以回看这次咨询结果。"
            : "本次整理没有发现需要额外确认的事项。"}
      </p>
    </div>
  );
}

export function toUserFacingAnswer({
  answer,
  intent,
}: {
  answer: string | null | undefined;
  intent: string | null | undefined;
}): string {
  const normalizedAnswer = answer?.trim();
  if (!normalizedAnswer) return "这次没有生成可展示的内容。";

  if (!containsInternalAnswerLanguage(normalizedAnswer)) {
    return normalizedAnswer;
  }

  switch (intent) {
    case "refill":
      return "我已经根据家庭健康记录整理了续方准备所需的信息。";
    case "reminder":
      return "我已经根据现有健康记录整理了用药提醒准备内容。";
    case "pharmacy":
      return "我已经根据现有信息整理了购药准备内容。";
    case "safety_check":
      return "我已经识别出需要专业人员确认的风险。";
    default:
      return "我已经根据现有家庭健康记录整理了这次咨询的相关信息。";
  }
}

function containsInternalAnswerLanguage(answer: string): boolean {
  return [
    /prepared a local .* result from sources:/i,
    /no hospital, purchase, payment, or reminder action was submitted\.?/i,
    /this request is blocked for safety/i,
    /no medication instruction or external action was generated/i,
    /\bsources?:\s*[a-z_]/i,
    /\b(?:source_id|tool_name|run_id|task_id|trace|continuation run)\b/i,
    /本地.*草稿|外部.*提交|外部系统|工具调用|执行记录|source_id|Trace/,
  ].some((pattern) => pattern.test(answer));
}

function getResultStatus({
  blocked,
  continuationRun,
  waitingForConfirmation,
  status,
}: {
  blocked: boolean;
  continuationRun: boolean;
  waitingForConfirmation: boolean;
  status: string;
}): {
  label: string;
  title: string;
  tone: "neutral" | "success" | "warning" | "danger";
} {
  if (blocked || status === "blocked") {
    return { label: "需要专业确认", title: "这件事需要专业人员确认", tone: "danger" };
  }
  if (waitingForConfirmation) {
    return { label: "等待你的确认", title: "信息已经整理好了", tone: "warning" };
  }
  if (continuationRun && status === "completed") {
    return { label: "已完成", title: "这次咨询已完成", tone: "success" };
  }
  if (status === "failed") {
    return { label: "需要重试", title: "这次没有完成整理", tone: "danger" };
  }
  return { label: "已整理", title: "我已经帮你整理好了", tone: "success" };
}
