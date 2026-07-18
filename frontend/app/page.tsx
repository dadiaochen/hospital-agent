import Link from "next/link";

import { mvpScenarios } from "@/lib/navigation";

const quickLinks = [
  { href: "/family", label: "查看健康档案", detail: "成员与安全备注" },
  { href: "/medicine-box", label: "检查家庭药箱", detail: "库存与剩余天数" },
  { href: "/refill-plans", label: "整理续方材料", detail: "处方与确认草稿" },
  { href: "/reminders", label: "查看提醒草稿", detail: "确认状态与边界" },
];

export default function HomePage() {
  return (
    <div className="grid gap-5">
      <section className="overflow-hidden rounded-2xl border border-[#cfe0da] bg-[#173c38] p-6 text-white shadow-sm sm:p-8">
        <div className="grid gap-7 lg:grid-cols-[1.25fr_0.75fr] lg:items-end">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-[#9fddd1]">
              Internet Hospital Agent
            </p>
            <h2 className="mt-3 max-w-3xl text-3xl font-bold leading-tight tracking-tight sm:text-4xl">
              用来源、确认和审计，把家庭健康事务做成可追踪流程
            </h2>
            <p className="mt-4 max-w-3xl text-sm leading-7 text-[#d5e8e3]">
              当前页面读取真实后端 API。先在顶部选择本人、父亲或母亲，再查看该成员的档案、药箱、处方和草稿，页面不会混合不同成员的数据。
            </p>
          </div>
          <div className="rounded-xl border border-white/15 bg-white/10 p-4 text-sm leading-6 text-[#e5f2ef]">
            医疗安全边界：系统不诊断、不开方、不改剂量；续方、购药和提醒等关键动作只生成本地草稿并等待人工确认。
          </div>
        </div>
      </section>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {quickLinks.map((item) => (
          <Link
            className="group rounded-2xl border border-[#dbe7e3] bg-white p-4 shadow-sm transition hover:-translate-y-0.5 hover:border-[#9bc7bd]"
            href={item.href}
            key={item.href}
          >
            <p className="font-semibold text-[#173c38] group-hover:text-[#0f766e]">
              {item.label}
            </p>
            <p className="mt-2 text-xs text-[#71847f]">{item.detail}</p>
          </Link>
        ))}
      </section>

      <section>
        <div className="mb-3 flex items-end justify-between gap-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#0f766e]">
              MVP Scenarios
            </p>
            <h3 className="mt-1 text-xl font-bold text-[#173c38]">核心演示场景</h3>
          </div>
          <span className="text-xs text-[#71847f]">所有外部动作均未接入</span>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          {mvpScenarios.map((scenario) => (
            <article
              className="rounded-2xl border border-[#dbe7e3] bg-white p-5 shadow-sm"
              key={scenario.title}
            >
              <div className="flex items-start justify-between gap-4">
                <h4 className="font-bold text-[#213f3b]">{scenario.title}</h4>
                <span className="rounded-full bg-[#e4f4ef] px-2.5 py-1 text-xs font-semibold text-[#0f766e]">
                  {scenario.status}
                </span>
              </div>
              <p className="mt-3 text-sm leading-6 text-[#64748b]">
                {scenario.boundary}
              </p>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
