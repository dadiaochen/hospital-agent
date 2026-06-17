type AgentRunDetailPageProps = {
  params: {
    id: string;
  };
};

export default function AgentRunDetailPage({ params }: AgentRunDetailPageProps) {
  return (
    <section className="rounded-md border border-[#d9e5e1] bg-white p-6">
      <p className="text-sm font-medium text-clinic">Run ID</p>
      <h2 className="mt-2 text-2xl font-semibold tracking-normal">{params.id}</h2>
      <div className="mt-6 grid gap-4 md:grid-cols-2">
        {["工具调用链路", "输入输出", "耗时", "最终决策"].map((item) => (
          <div className="rounded-md border border-[#e2e8f0] bg-[#fbfdfc] p-4 text-sm text-[#334155]" key={item}>
            {item}
          </div>
        ))}
      </div>
    </section>
  );
}

