"use client";

import { AsyncContent } from "@/components/AsyncContent";
import { toUserFacingAnswer } from "@/components/AgentRunResult";
import { PageHeader } from "@/components/PageHeader";
import { useMember } from "@/components/providers/MemberProvider";
import { StatusBadge } from "@/components/StatusBadge";
import { api } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";
import { useApiResource } from "@/lib/useApiResource";

export default function AgentRunsPage() {
  const {
    selectedMemberId,
    selectedMember,
    loading: membersLoading,
    error: membersError,
    reload: reloadMembers,
  } = useMember();
  const memberId = selectedMemberId;
  const runs = useApiResource(memberId ? `agent-runs:${memberId}` : null, (signal) => {
    if (!memberId) throw new Error("请先选择家庭成员");
    return api.listAgentRuns(memberId, signal);
  });

  return (
    <div className="grid gap-5">
      <PageHeader
        description="查看当前家庭成员过去的咨询内容和整理结果。切换成员后，只显示该成员的记录。"
        eyebrow="历史咨询"
        title="历史咨询"
      >
        {selectedMember ? (
          <span className="text-sm font-semibold text-[#31534f]">
            当前：{selectedMember.name}
          </span>
        ) : null}
      </PageHeader>

      <AsyncContent
        empty={(runs.data?.length ?? 0) === 0}
        emptyDescription="完成一次咨询后，记录会出现在这里。"
        emptyTitle="还没有咨询记录"
        error={membersError ?? runs.error}
        loading={membersLoading || (Boolean(memberId) && runs.loading)}
        onRetry={membersError ? reloadMembers : runs.reload}
      >
        <div className="grid gap-3">
          {runs.data?.map((run) => (
            <article
              className="rounded-2xl border border-[#dbe7e3] bg-white p-5 shadow-sm"
              key={run.id}
            >
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge
                      tone={runStatusTone(run.status)}
                    >
                      {readableRunStatus(run.status)}
                    </StatusBadge>
                    {run.intent ? <StatusBadge>{readableIntent(run.intent)}</StatusBadge> : null}
                    {run.need_human_confirmation ? (
                      <StatusBadge tone="warning">需要你确认</StatusBadge>
                    ) : null}
                  </div>
                  <h3 className="mt-3 font-bold leading-6 text-[#173c38]">
                    {run.user_goal}
                  </h3>
                </div>
                <p className="shrink-0 text-sm text-[#71847f]">{formatDateTime(run.started_at)}</p>
              </div>
              {run.final_answer ? (
                <div className="mt-4 rounded-xl bg-[#f4f8f6] px-4 py-3">
                  <p className="text-xs font-bold text-[#53726b]">整理结果</p>
                  <p className="mt-1 line-clamp-3 text-sm leading-6 text-[#475569]">
                    {toUserFacingAnswer({ answer: run.final_answer, intent: run.intent })}
                  </p>
                </div>
              ) : null}
            </article>
          ))}
        </div>
      </AsyncContent>
    </div>
  );
}

function readableRunStatus(status: string) {
  switch (status) {
    case "completed":
      return "已完成";
    case "needs_confirmation":
      return "待确认";
    case "blocked":
      return "已暂停";
    case "failed":
      return "未完成";
    case "running":
      return "处理中";
    default:
      return "已记录";
  }
}

function runStatusTone(status: string): "neutral" | "success" | "warning" | "danger" {
  if (status === "completed") return "success";
  if (status === "failed" || status === "blocked") return "danger";
  if (status === "needs_confirmation" || status === "running") return "warning";
  return "neutral";
}

function readableIntent(intent: string) {
  switch (intent) {
    case "refill":
      return "续方准备";
    case "reminder":
      return "用药提醒";
    case "pharmacy":
      return "购药准备";
    case "safety_check":
      return "用药安全";
    default:
      return "健康咨询";
  }
}
