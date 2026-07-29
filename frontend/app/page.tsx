"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { useMember } from "@/components/providers/MemberProvider";
import { mvpScenarios } from "@/lib/navigation";

const serviceCards = [
  {
    href: "/agent",
    eyebrow: "慢病续方",
    title: "整理续方材料",
    description: "汇总处方、药箱和购药记录，生成待确认草稿。",
    label: "开始整理",
    tone: "teal",
  },
  {
    href: "/agent",
    eyebrow: "用药提醒",
    title: "准备提醒草稿",
    description: "根据已有药箱信息整理提醒内容，不直接推送。",
    label: "设置提醒",
    tone: "amber",
  },
  {
    href: "/refill-plans",
    eyebrow: "复诊材料",
    title: "查看历史处方",
    description: "查看医生记录与可追溯来源，准备复诊沟通材料。",
    label: "查看材料",
    tone: "blue",
  },
  {
    href: "/medicine-box",
    eyebrow: "家庭药箱",
    title: "检查剩余药量",
    description: "查看库存、预计剩余天数和安全备注。",
    label: "打开药箱",
    tone: "rose",
  },
] as const;

const categoryLinks = [
  { href: "/purchase-plans", label: "附近药店库存", detail: "配送 / 自提候选" },
  { href: "/knowledge", label: "安全知识检索", detail: "查看来源和版本" },
  { href: "/family", label: "家庭成员", detail: "切换任务作用域" },
  { href: "/agent-runs", label: "执行记录", detail: "查看冻结 Trace" },
] as const;

export default function HomePage() {
  const router = useRouter();
  const { selectedMember, members, loading } = useMember();
  const [query, setQuery] = useState("");

  function submitSearch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedQuery = query.trim();
    if (trimmedQuery) {
      router.push(`/knowledge?q=${encodeURIComponent(trimmedQuery)}`);
    } else {
      router.push("/knowledge");
    }
  }

  return (
    <div className="grid gap-5">
      <section className="overflow-hidden rounded-[28px] border border-[#eadfca] bg-[#fff4d7] shadow-sm">
        <div className="grid gap-8 p-5 sm:p-7 lg:grid-cols-[1.35fr_0.65fr] lg:p-9">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-[#f7b928] px-3 py-1.5 text-xs font-black text-[#553507]">
                患者端健康服务
              </span>
              <span className="text-xs font-semibold text-[#936a2c]">
                先选成员，再处理一件事
              </span>
            </div>
            <h1 className="mt-5 max-w-2xl text-3xl font-black leading-tight tracking-tight text-[#173c38] sm:text-5xl">
              家庭用药事务，清楚地整理，安心地确认
            </h1>
            <p className="mt-4 max-w-2xl text-sm leading-7 text-[#6f6046] sm:text-base">
              从药箱、处方和来源开始，把续方、复诊材料和提醒变成可追踪的本地草稿。系统不诊断、不开方，也不会替你向医院或药店提交动作。
            </p>

            <form className="mt-6 flex max-w-2xl flex-col gap-2 rounded-2xl bg-white p-2 shadow-sm sm:flex-row" onSubmit={submitSearch}>
              <label className="sr-only" htmlFor="portal-search">
                搜索健康事务或知识
              </label>
              <input
                aria-label="搜索健康事务或知识"
                className="min-w-0 flex-1 rounded-xl px-4 py-3 text-sm text-[#334155] outline-none placeholder:text-[#9aa69f] focus:ring-2 focus:ring-[#f7b928]/50"
                id="portal-search"
                maxLength={200}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索：续方需要哪些确认？为什么不能自行加量？"
                value={query}
              />
              <button className="rounded-xl bg-[#173c38] px-5 py-3 text-sm font-bold text-white transition hover:bg-[#0f766e]" type="submit">
                搜索
              </button>
            </form>
            <div className="mt-3 flex flex-wrap gap-2 text-xs text-[#80602b]">
              <span>热门事务：</span>
              {["续方材料", "用药提醒", "停药风险"].map((item) => (
                <button className="font-semibold underline decoration-[#d7ad5b] underline-offset-4 hover:text-[#173c38]" key={item} onClick={() => setQuery(item)} type="button">
                  {item}
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-end">
            <div className="w-full rounded-3xl border border-white/80 bg-white/80 p-5 shadow-sm backdrop-blur">
              <div className="flex items-center justify-between gap-3">
                <p className="text-xs font-black uppercase tracking-[0.16em] text-[#b26c09]">
                  当前任务成员
                </p>
                <StatusBadge tone="success">已隔离</StatusBadge>
              </div>
              {loading ? (
                <div className="mt-5 h-16 animate-pulse rounded-2xl bg-[#f5ead0]" />
              ) : selectedMember ? (
                <>
                  <p className="mt-5 text-3xl font-black text-[#173c38]">{selectedMember.name}</p>
                  <p className="mt-2 text-sm text-[#6f6046]">
                    当前家庭共 {members.length} 位成员，所有查询和 Agent 运行都绑定当前成员。
                  </p>
                  <Link className="mt-5 inline-flex rounded-xl border border-[#d9bf82] px-4 py-2.5 text-sm font-bold text-[#80530b] transition hover:bg-[#fff4d7]" href="/family">
                    查看健康档案
                  </Link>
                </>
              ) : (
                <>
                  <p className="mt-5 text-xl font-black text-[#173c38]">暂未加载成员</p>
                  <p className="mt-2 text-sm text-[#6f6046]">请检查后端服务和 seed 数据。</p>
                </>
              )}
            </div>
          </div>
        </div>
      </section>

      <section>
        <div className="mb-3 flex items-end justify-between gap-4">
          <div>
            <p className="text-xs font-black uppercase tracking-[0.16em] text-[#b26c09]">Health Services</p>
            <h2 className="mt-1 text-2xl font-black text-[#173c38]">你可以先处理这些事务</h2>
          </div>
          <Link className="text-sm font-bold text-[#0f766e] hover:underline" href="/agent">进入 Agent</Link>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {serviceCards.map((card, index) => (
            <Link className="group rounded-2xl border border-[#eadfca] bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:border-[#d4b56c]" href={card.href} key={card.title}>
              <div className="flex items-start justify-between gap-3">
                <span className={`grid h-9 w-9 place-items-center rounded-xl text-xs font-black ${toneClasses[card.tone]}`}>
                  0{index + 1}
                </span>
                <span className="text-xs font-semibold text-[#9aa69f] transition group-hover:text-[#0f766e]">{card.label} →</span>
              </div>
              <p className="mt-5 text-xs font-bold uppercase tracking-[0.12em] text-[#b26c09]">{card.eyebrow}</p>
              <h3 className="mt-2 text-lg font-black text-[#173c38]">{card.title}</h3>
              <p className="mt-2 text-sm leading-6 text-[#64748b]">{card.description}</p>
            </Link>
          ))}
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="rounded-2xl border border-[#eadfca] bg-white p-5 shadow-sm sm:p-6">
          <div className="flex items-end justify-between gap-3">
            <div>
              <p className="text-xs font-black uppercase tracking-[0.16em] text-[#0f766e]">Shortcuts</p>
              <h2 className="mt-1 text-xl font-black text-[#173c38]">健康服务分类</h2>
            </div>
            <span className="text-xs text-[#9aa69f]">当前成员：{selectedMember?.name ?? "未选择"}</span>
          </div>
          <div className="mt-5 grid gap-2 sm:grid-cols-2">
            {categoryLinks.map((item) => (
              <Link className="flex items-center justify-between rounded-xl bg-[#fffaf0] px-4 py-3 transition hover:bg-[#fff4d7]" href={item.href} key={item.href}>
                <span>
                  <span className="block text-sm font-bold text-[#31534f]">{item.label}</span>
                  <span className="mt-1 block text-xs text-[#8b9b95]">{item.detail}</span>
                </span>
                <span className="text-lg text-[#c38a20]">›</span>
              </Link>
            ))}
          </div>
        </div>

        <div className="rounded-2xl border border-[#cfe2dc] bg-[#edf8f4] p-5 shadow-sm sm:p-6">
          <p className="text-xs font-black uppercase tracking-[0.16em] text-[#0f766e]">Safety First</p>
          <h2 className="mt-2 text-xl font-black text-[#173c38]">每一步都能看见边界</h2>
          <ul className="mt-4 grid gap-3 text-sm leading-6 text-[#52706b]">
            <li><strong className="text-[#31534f]">来源：</strong>事实来自业务工具或知识检索，不用模型记忆补全。</li>
            <li><strong className="text-[#31534f]">确认：</strong>续方、购药和提醒先形成草稿，用户确认后才推进本地状态。</li>
            <li><strong className="text-[#31534f]">隔离：</strong>切换成员会重新加载上下文，页面拒绝展示跨成员数据。</li>
          </ul>
          <Link className="mt-5 inline-flex rounded-xl bg-[#0f766e] px-4 py-2.5 text-sm font-bold text-white transition hover:bg-[#115e59]" href="/agent-runs">
            查看可审计执行记录
          </Link>
        </div>
      </section>

      <section>
        <div className="mb-3 flex items-end justify-between gap-4">
          <div>
            <p className="text-xs font-black uppercase tracking-[0.16em] text-[#b26c09]">Demo Scenarios</p>
            <h2 className="mt-1 text-xl font-black text-[#173c38]">固定演示场景</h2>
          </div>
          <span className="text-xs text-[#9aa69f]">所有外部动作均未接入</span>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          {mvpScenarios.map((scenario) => (
            <article className="rounded-2xl border border-[#eadfca] bg-white p-5 shadow-sm" key={scenario.title}>
              <div className="flex items-start justify-between gap-4">
                <h3 className="font-bold text-[#213f3b]">{scenario.title}</h3>
                <StatusBadge tone={scenario.title.includes("高风险") ? "danger" : "neutral"}>{scenario.status}</StatusBadge>
              </div>
              <p className="mt-3 text-sm leading-6 text-[#64748b]">{scenario.boundary}</p>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

const toneClasses = {
  teal: "bg-[#dff3ed] text-[#0f766e]",
  amber: "bg-[#fff0c2] text-[#9a670e]",
  blue: "bg-[#e2efff] text-[#2563a8]",
  rose: "bg-[#fde7e7] text-[#b42318]",
} as const;
