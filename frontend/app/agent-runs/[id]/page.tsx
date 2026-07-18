import { PageHeader } from "@/components/PageHeader";

type AgentRunDetailPageProps = {
  params: {
    id: string;
  };
};

export default function AgentRunDetailPage({ params }: AgentRunDetailPageProps) {
  return (
    <div className="grid gap-5">
      <PageHeader
        description="3B 将在这里加载冻结 RunTrace、工具调用、来源引用、安全结果和 EvaluationResult。"
        eyebrow="Phase 3B Preview"
        title="Agent Run 详情"
      />
      <section className="rounded-2xl border border-dashed border-[#cdded8] bg-white p-6">
        <p className="text-xs font-semibold text-[#71847f]">待接入的 run_id</p>
        <p className="mt-2 break-all font-mono text-sm text-[#31534f]">{params.id}</p>
      </section>
    </div>
  );
}
