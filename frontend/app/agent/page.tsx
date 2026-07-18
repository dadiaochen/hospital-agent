import { PageHeader } from "@/components/PageHeader";

export default function AgentPage() {
  return (
    <div className="grid gap-5">
      <PageHeader
        description="3A 先完成核心数据页面；3B 再接入 Agent 输入、结构化答案、确认动作和 Trace 详情。"
        eyebrow="Phase 3B Preview"
        title="Agent 对话"
      />
      <section className="rounded-2xl border border-dashed border-[#cdded8] bg-white p-8 text-center">
        <p className="font-semibold text-[#31534f]">对话入口将在 3B 启用</p>
        <p className="mt-2 text-sm leading-6 text-[#71847f]">
          当前可先在“执行记录”查看真实 Agent run 列表，避免把尚未接入的按钮伪装成可用功能。
        </p>
      </section>
    </div>
  );
}
