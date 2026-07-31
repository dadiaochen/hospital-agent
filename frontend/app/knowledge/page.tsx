"use client";

import { FormEvent, useState } from "react";
import { useEffect } from "react";

import { PageHeader } from "@/components/PageHeader";
import { StatusBadge } from "@/components/StatusBadge";
import { api } from "@/lib/api/client";
import type { KnowledgeSearchItem } from "@/lib/api/types";

export default function KnowledgePage() {
  const [query, setQuery] = useState("续方需要哪些确认");
  const [category, setCategory] = useState("");
  const [items, setItems] = useState<KnowledgeSearchItem[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const presetQuery = new URLSearchParams(window.location.search).get("q");
    if (presetQuery?.trim()) setQuery(presetQuery.trim());
  }, []);

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      setItems(await api.searchKnowledge(query, category));
    } catch (caught) {
      setItems(null);
      setError(caught instanceof Error ? caught.message : "知识检索失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid gap-5">
      <PageHeader
        description="调用 2E-1 的 GET /api/knowledge/search 接口。结果必须展示 source_id，便于 Agent 和评估器追溯事实来源。"
        eyebrow="Knowledge Search"
        title="SOP 与安全知识检索"
      />

      <form
        className="rounded-2xl border border-[#dbe7e3] bg-white p-5 shadow-sm"
        onSubmit={handleSearch}
      >
        <div className="grid gap-3 lg:grid-cols-[1fr_240px_auto] lg:items-end">
          <label className="grid gap-1.5 text-sm font-semibold text-[#31534f]">
            检索问题
            <input
              className="rounded-lg border border-[#cdded8] px-3 py-2.5 font-normal outline-none focus:border-[#0f766e]"
              maxLength={200}
              onChange={(event) => setQuery(event.target.value)}
              value={query}
            />
          </label>
          <label className="grid gap-1.5 text-sm font-semibold text-[#31534f]">
            分类（可选）
            <input
              className="rounded-lg border border-[#cdded8] px-3 py-2.5 font-normal outline-none focus:border-[#0f766e]"
              maxLength={80}
              onChange={(event) => setCategory(event.target.value)}
              placeholder="例如：refill_sop"
              value={category}
            />
          </label>
          <button
            className="rounded-lg bg-[#0f766e] px-5 py-2.5 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-60"
            disabled={loading}
            type="submit"
          >
            {loading ? "检索中..." : "开始检索"}
          </button>
        </div>
      </form>

      {error ? (
        <section className="rounded-2xl border border-[#fecaca] bg-[#fff8f7] p-5" role="alert">
          <p className="font-semibold text-[#991b1b]">知识接口暂时不可用</p>
          <p className="mt-2 text-sm leading-6 text-[#7f1d1d]">{error}</p>
          <p className="mt-3 text-xs text-[#9f1d18]">
            若你正在 2E-1 分支练习接口，请先完成路由注册并启动后端；本页不会替你实现该练习。
          </p>
        </section>
      ) : items === null ? (
        <section className="rounded-2xl border border-dashed border-[#cdded8] bg-white p-7 text-center">
          <p className="font-semibold text-[#31534f]">输入问题后查看结构化来源</p>
          <p className="mt-2 text-sm text-[#71847f]">
            可尝试“续方需要哪些确认”或“为什么不能自行停药”。
          </p>
        </section>
      ) : items.length === 0 ? (
        <section className="rounded-2xl border border-dashed border-[#cdded8] bg-white p-7 text-center">
          <p className="font-semibold text-[#31534f]">没有检索到匹配内容</p>
          <p className="mt-2 text-sm text-[#71847f]">换一个关键词或清空分类后重试。</p>
        </section>
      ) : (
        <div className="grid gap-4">
          {items.map((item) => (
            <article
              className="rounded-2xl border border-[#dbe7e3] bg-white p-5 shadow-sm"
              key={item.source_id}
            >
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <h3 className="font-bold text-[#173c38]">{item.title}</h3>
                  <p className="mt-1 text-xs text-[#71847f]">来源：{item.source}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <StatusBadge>{item.category}</StatusBadge>
                  <StatusBadge tone={item.safety_level === "high" ? "warning" : "neutral"}>
                    {item.safety_level}
                  </StatusBadge>
                </div>
              </div>
              <p className="mt-4 whitespace-pre-wrap text-sm leading-7 text-[#475569]">
                {item.content}
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                {item.keywords.map((keyword) => (
                  <span
                    className="rounded-full bg-[#f1f5f4] px-2.5 py-1 text-xs text-[#52706b]"
                    key={keyword}
                  >
                    {keyword}
                  </span>
                ))}
              </div>
              <p className="mt-4 break-all font-mono text-[11px] text-[#94a3b8]">
                source_id: {item.source_id}
              </p>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
