"use client";

import { AsyncContent } from "@/components/AsyncContent";
import { PageHeader } from "@/components/PageHeader";
import { useMember } from "@/components/providers/MemberProvider";
import { RunTraceDetails } from "@/components/RunTraceDetails";
import { api } from "@/lib/api/client";
import { useApiResource } from "@/lib/useApiResource";

type AgentRunDetailPageProps = {
  params: { id: string };
};

export default function AgentRunDetailPage({ params }: AgentRunDetailPageProps) {
  const {
    selectedMemberId,
    selectedMember,
    loading: membersLoading,
    error: membersError,
    reload: reloadMembers,
  } = useMember();
  const memberId = selectedMemberId;
  const details = useApiResource(
    memberId ? `agent-run:${params.id}:${memberId}` : null,
    async (signal) => {
      if (!memberId) throw new Error("请先选择家庭成员");
      const [run, artifacts, toolCalls] = await Promise.all([
        api.getAgentRun(params.id, memberId, signal),
        api.getAgentRunArtifacts(params.id, memberId, signal),
        api.listAgentToolCalls(params.id, signal),
      ]);
      if (artifacts.run_id !== run.id || toolCalls.some((call) => call.run_id !== run.id)) {
        throw new Error("Trace 产物与当前 run_id 不一致，页面已停止展示");
      }
      return { run, artifacts, toolCalls };
    },
  );

  return (
    <div className="grid gap-5">
      <PageHeader
        description="只读展示冻结 RunTrace、角色工具调用、来源、安全结果、模型 fallback 与 EvaluationResult。Evaluator 不会修改答案或业务状态。"
        eyebrow="Agent Audit"
        title="Agent Run 详情"
      >
        {selectedMember ? <span className="text-sm font-semibold text-[#31534f]">当前成员：{selectedMember.name}</span> : null}
      </PageHeader>

      <AsyncContent
        empty={false}
        error={membersError ?? details.error}
        loading={membersLoading || (Boolean(memberId) && details.loading)}
        onRetry={membersError ? reloadMembers : details.reload}
      >
        {details.data ? <RunTraceDetails {...details.data} /> : null}
      </AsyncContent>
    </div>
  );
}
