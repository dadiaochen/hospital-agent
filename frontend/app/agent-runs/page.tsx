import Link from "next/link";

export default function AgentRunsPage() {
  const demoRunId = "phase-1-demo";

  return (
    <section className="rounded-md border border-[#d9e5e1] bg-white p-6">
      <p className="text-sm font-medium text-clinic">Agent Runs</p>
      <h2 className="mt-2 text-2xl font-semibold tracking-normal">执行记录</h2>
      <div className="mt-6 rounded-md border border-[#e2e8f0] bg-[#fbfdfc] p-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h3 className="font-semibold tracking-normal">Phase 1 Demo Run</h3>
            <p className="mt-1 text-sm text-[#475569]">后续展示 intent、final_answer、safety_result 和 raw_state。</p>
          </div>
          <Link className="rounded-md bg-clinic px-4 py-2 text-sm font-semibold text-white" href={`/agent-runs/${demoRunId}`}>
            查看详情
          </Link>
        </div>
      </div>
    </section>
  );
}

