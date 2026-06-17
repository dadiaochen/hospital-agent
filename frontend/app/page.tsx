import { mvpScenarios } from "@/lib/navigation";

export default function HomePage() {
  return (
    <div className="grid gap-6">
      <section className="rounded-md border border-[#d9e5e1] bg-white p-6">
        <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
          <div>
            <p className="text-sm font-medium text-clinic">互联网医院慢病续方与家庭用药管理</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-normal">一个强调确认、审计和安全边界的家庭健康 Agent 系统</h2>
            <p className="mt-4 max-w-3xl text-sm leading-6 text-[#475569]">
              当前阶段已完成工程骨架。后续会逐步接入数据库、业务 API、MCP-like 工具注册表、LangGraph 工作流和可回放的 Agent 执行日志。
            </p>
          </div>
          <div className="grid gap-3">
            {["不诊断", "不自动开方", "不修改医生处方", "关键动作人工确认"].map((item) => (
              <div className="rounded-md border border-[#e2e8f0] bg-[#fbfdfc] px-4 py-3 text-sm font-medium text-[#334155]" key={item}>
                {item}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2">
        {mvpScenarios.map((scenario) => (
          <article className="rounded-md border border-[#d9e5e1] bg-white p-5" key={scenario.title}>
            <div className="flex items-start justify-between gap-4">
              <h3 className="text-lg font-semibold tracking-normal">{scenario.title}</h3>
              <span className="rounded-md bg-mist px-2 py-1 text-xs font-medium text-clinic">{scenario.status}</span>
            </div>
            <p className="mt-3 text-sm leading-6 text-[#475569]">{scenario.boundary}</p>
          </article>
        ))}
      </section>
    </div>
  );
}

