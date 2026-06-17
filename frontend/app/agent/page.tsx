export default function AgentPage() {
  return (
    <section className="rounded-md border border-[#d9e5e1] bg-white">
      <div className="border-b border-[#e2e8f0] p-5">
        <p className="text-sm font-medium text-clinic">FamilyHealthAgent</p>
        <h2 className="mt-2 text-2xl font-semibold tracking-normal">Agent 对话</h2>
      </div>
      <div className="grid gap-4 p-5">
        <div className="rounded-md border border-[#e2e8f0] bg-[#fbfdfc] p-4 text-sm leading-6 text-[#334155]">
          示例输入：我爸的降压药快吃完了，帮我看看能不能续方。
        </div>
        <textarea
          className="min-h-32 rounded-md border border-[#cbd5e1] p-3 text-sm outline-none focus:border-clinic"
          placeholder="Phase 3 接入 /api/agent/chat 后启用"
        />
        <div className="flex justify-end">
          <button className="rounded-md bg-clinic px-4 py-2 text-sm font-semibold text-white" type="button">
            等待 API 接入
          </button>
        </div>
      </div>
    </section>
  );
}

