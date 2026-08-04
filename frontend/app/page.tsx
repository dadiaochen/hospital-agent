"use client";

import Link from "next/link";

import { StatusBadge } from "@/components/StatusBadge";
import { useMember } from "@/components/providers/MemberProvider";

const publicServices = [
  {
    href: "/agent",
    eyebrow: "AI 健康助手",
    title: "开始一次健康咨询",
    description: "直接说说你或家人现在想整理的健康问题。",
    label: "开始咨询",
    tone: "teal",
  },
  {
    href: "/reports",
    eyebrow: "报告解读",
    title: "看看检查报告",
    description: "查看报告摘要、指标解释、趋势和来源。",
    label: "查看报告",
    tone: "blue",
  },
  {
    href: "/family",
    eyebrow: "家庭管理",
    title: "管理家庭健康记录",
    description: "集中查看成员档案、用药、处方和购药记录。",
    label: "查看家庭",
    tone: "rose",
  },
  {
    href: "/agent-runs",
    eyebrow: "历史咨询",
    title: "回看过去的咨询",
    description: "按家庭成员查看已经整理过的咨询内容。",
    label: "查看记录",
    tone: "amber",
  },
] as const;

const categoryLinks = [
  { href: "/agent", label: "AI 健康助手", detail: "从一句话开始" },
  { href: "/reports", label: "报告解读", detail: "查看报告和指标" },
  { href: "/family", label: "家庭管理", detail: "管理成员和健康记录" },
  { href: "/agent-runs", label: "历史咨询", detail: "回看过去的内容" },
] as const;

export default function HomePage() {
  const { selectedMember, members, loading } = useMember();

  return (
    <div className="grid gap-5">
      <section className="overflow-hidden rounded-[28px] border border-[#eadfca] bg-[#fff4d7] shadow-sm">
        <div className="grid gap-8 p-5 sm:p-7 lg:grid-cols-[1.35fr_0.65fr] lg:p-9">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-[#f7b928] px-3 py-1.5 text-xs font-black text-[#553507]">
                家庭健康助手
              </span>
              <span className="text-xs font-semibold text-[#936a2c]">
                先选择成员，再开始
              </span>
            </div>
            <h1 className="mt-5 max-w-2xl text-3xl font-black leading-tight tracking-tight text-[#173c38] sm:text-5xl">
              先说一件事，我们一起整理
            </h1>
            <p className="mt-4 max-w-2xl text-sm leading-7 text-[#6f6046] sm:text-base">
              从一次自然语言咨询开始，整理家人的健康问题、检查报告和用药记录。
            </p>

            <div className="mt-6 flex flex-wrap gap-3">
              <Link className="rounded-xl bg-[#173c38] px-5 py-3 text-sm font-bold text-white transition hover:bg-[#0f766e]" href="/agent">
                开始咨询
              </Link>
              <Link className="rounded-xl border border-[#d9bf82] bg-white/70 px-5 py-3 text-sm font-bold text-[#80530b] transition hover:bg-white" href="/family">
                查看家庭记录
              </Link>
            </div>
          </div>

          <div className="flex items-end">
            <div className="w-full rounded-3xl border border-white/80 bg-white/80 p-5 shadow-sm backdrop-blur">
              <div className="flex items-center justify-between gap-3">
                <p className="text-xs font-black uppercase tracking-[0.16em] text-[#b26c09]">
                  当前家庭成员
                </p>
                <StatusBadge tone="success">已选择</StatusBadge>
              </div>
              {loading ? (
                <div className="mt-5 h-16 animate-pulse rounded-2xl bg-[#f5ead0]" />
              ) : selectedMember ? (
                <>
                  <p className="mt-5 text-3xl font-black text-[#173c38]">{selectedMember.name}</p>
                  <p className="mt-2 text-sm text-[#6f6046]">
                    当前家庭共 {members.length} 位成员，咨询和记录都会围绕当前成员展示。
                  </p>
                  <Link className="mt-5 inline-flex rounded-xl border border-[#d9bf82] px-4 py-2.5 text-sm font-bold text-[#80530b] transition hover:bg-[#fff4d7]" href="/family">
                    管理家庭成员
                  </Link>
                </>
              ) : (
                <>
                  <p className="mt-5 text-xl font-black text-[#173c38]">暂未加载成员</p>
                  <p className="mt-2 text-sm text-[#6f6046]">暂时无法加载家庭成员，请稍后再试。</p>
                </>
              )}
            </div>
          </div>
        </div>
      </section>

      <section>
        <div className="mb-3 flex items-end justify-between gap-4">
          <div>
            <p className="text-xs font-black uppercase tracking-[0.16em] text-[#b26c09]">Start Here</p>
            <h2 className="mt-1 text-2xl font-black text-[#173c38]">你可以从这里开始</h2>
          </div>
          <Link className="text-sm font-bold text-[#0f766e] hover:underline" href="/agent">开始咨询</Link>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {publicServices.map((card, index) => (
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
              <p className="text-xs font-black uppercase tracking-[0.16em] text-[#0f766e]">Quick Access</p>
              <h2 className="mt-1 text-xl font-black text-[#173c38]">常用入口</h2>
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
          <p className="text-xs font-black uppercase tracking-[0.16em] text-[#0f766e]">Easy to Use</p>
          <h2 className="mt-2 text-xl font-black text-[#173c38]">把健康记录变得更容易回看</h2>
          <p className="mt-4 text-sm leading-6 text-[#52706b]">
            选择家庭成员后，你可以从咨询开始，也可以直接查看报告和过去的记录。
          </p>
          <Link className="mt-5 inline-flex rounded-xl bg-[#0f766e] px-4 py-2.5 text-sm font-bold text-white transition hover:bg-[#115e59]" href="/reports">
            查看报告
          </Link>
        </div>
      </section>

      <section>
        <div className="mb-3 flex items-end justify-between gap-4">
          <div>
            <p className="text-xs font-black uppercase tracking-[0.16em] text-[#b26c09]">How It Works</p>
            <h2 className="mt-1 text-xl font-black text-[#173c38]">三步开始使用</h2>
          </div>
          <span className="text-xs text-[#9aa69f]">简单、清楚、随时可回看</span>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          {[
            { title: "选择成员", description: "先选中要查看或咨询的家庭成员。" },
            { title: "说出问题", description: "用自然语言描述症状、报告或用药问题。" },
            { title: "查看结果", description: "回看整理后的内容和过去的咨询记录。" },
          ].map((step, index) => (
            <article className="rounded-2xl border border-[#eadfca] bg-white p-5 shadow-sm" key={step.title}>
              <div className="grid h-9 w-9 place-items-center rounded-xl bg-[#fff0c2] text-xs font-black text-[#9a670e]">0{index + 1}</div>
              <h3 className="mt-5 font-bold text-[#213f3b]">{step.title}</h3>
              <p className="mt-2 text-sm leading-6 text-[#64748b]">{step.description}</p>
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
