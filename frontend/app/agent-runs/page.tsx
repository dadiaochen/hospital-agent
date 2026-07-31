"use client";

import Link from "next/link";

import { AsyncContent } from "@/components/AsyncContent";
import { PageHeader } from "@/components/PageHeader";
import { useMember } from "@/components/providers/MemberProvider";
import { StatusBadge } from "@/components/StatusBadge";
import { api } from "@/lib/api/client";
import { formatDateTime, formatStatus } from "@/lib/format";
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
        description="按当前成员查询真实 agent_runs；可进入详情查看冻结答案、工具链、来源、安全、fallback 和评估结果。"
        eyebrow="Agent Runs"
        title="Agent 执行记录"
      >
        {selectedMember ? (
          <span className="text-sm font-semibold text-[#31534f]">
            当前：{selectedMember.name}
          </span>
        ) : null}
      </PageHeader>

      <AsyncContent
        empty={(runs.data?.length ?? 0) === 0}
        emptyDescription="当前成员还没有 Agent run；可先通过后端 API 创建一次运行。"
        emptyTitle="暂无执行记录"
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
                      tone={
                        run.status === "completed"
                          ? "success"
                          : run.status === "failed"
                            ? "danger"
                            : "warning"
                      }
                    >
                      {formatStatus(run.status)}
                    </StatusBadge>
                    {run.intent ? <StatusBadge>{run.intent}</StatusBadge> : null}
                    {run.need_human_confirmation ? (
                      <StatusBadge tone="warning">需要人工确认</StatusBadge>
                    ) : null}
                  </div>
                  <h3 className="mt-3 font-bold leading-6 text-[#173c38]">
                    {run.user_goal}
                  </h3>
                  <p className="mt-2 break-all font-mono text-[11px] text-[#94a3b8]">
                    run_id: {run.id}
                  </p>
                </div>
                <dl className="grid shrink-0 grid-cols-2 gap-x-6 gap-y-3 text-sm lg:min-w-72">
                  <RunField label="开始时间" value={formatDateTime(run.started_at)} />
                  <RunField
                    label="耗时"
                    value={run.duration_ms === null ? "未记录" : `${run.duration_ms} ms`}
                  />
                  <RunField label="步骤数" value={String(run.step_count)} />
                  <RunField
                    label="Groundedness"
                    value={
                      run.groundedness_score === null
                        ? "未评估"
                        : run.groundedness_score.toFixed(2)
                    }
                  />
                </dl>
              </div>
              {run.final_answer ? (
                <p className="mt-4 line-clamp-2 rounded-xl bg-[#f4f8f6] px-4 py-3 text-sm leading-6 text-[#475569]">
                  {run.final_answer}
                </p>
              ) : null}
              <div className="mt-4 flex justify-end">
                <Link
                  className="rounded-lg border border-[#bcd2cc] px-3 py-2 text-xs font-bold text-[#0f766e] hover:bg-[#edf7f3]"
                  href={`/agent-runs/${encodeURIComponent(run.id)}`}
                >
                  查看 Trace 与评估
                </Link>
              </div>
            </article>
          ))}
        </div>
      </AsyncContent>
    </div>
  );
}

function RunField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-semibold text-[#71847f]">{label}</dt>
      <dd className="mt-1 text-[#334155]">{value}</dd>
    </div>
  );
}
