"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { AsyncContent } from "@/components/AsyncContent";
import { PageHeader } from "@/components/PageHeader";
import { useMember } from "@/components/providers/MemberProvider";
import { StatusBadge } from "@/components/StatusBadge";
import { api } from "@/lib/api/client";
import type {
  ReportDetail,
  ReportMetric,
  ReportStatus,
} from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";
import { useApiResource } from "@/lib/useApiResource";

export default function ReportDetailPage() {
  const params = useParams<{ reportId: string | string[] }>();
  const reportId = Array.isArray(params.reportId)
    ? params.reportId[0]
    : params.reportId;
  const {
    selectedMemberId,
    selectedMember,
    loading: membersLoading,
    error: membersError,
    reload: reloadMembers,
  } = useMember();

  const detailResource = useApiResource(
    selectedMemberId && reportId
      ? `report:${selectedMemberId}:${reportId}`
      : null,
    (signal) => {
      if (!selectedMemberId || !reportId) {
        throw new Error("请先选择家庭成员");
      }
      return api.getReportDetail(selectedMemberId, reportId, signal);
    },
  );

  const detail = detailResource.data;

  return (
    <div className="grid gap-5">
      <PageHeader
        description="这里展示报告中已经整理出的信息、指标解释和来源。内容用于帮助你读懂报告，不替代医生判断。"
        eyebrow="报告解读"
        title={detail?.report.title ?? "报告详情"}
      >
        <div className="flex flex-wrap items-center justify-end gap-3">
          <Link
            className="rounded-lg border border-[#bcd2cc] px-3 py-2 text-sm font-bold text-[#0f766e] hover:bg-[#edf7f3]"
            href="/reports"
          >
            返回报告列表
          </Link>
          {selectedMember ? (
            <span className="text-sm font-semibold text-[#31534f]">
              当前：{selectedMember.name}
            </span>
          ) : null}
        </div>
      </PageHeader>

      <AsyncContent
        empty={!membersLoading && !detailResource.loading && !detail}
        emptyDescription="选择家庭成员后，这里会显示对应的报告内容。"
        emptyTitle="暂时没有报告详情"
        error={membersError ?? detailResource.error}
        loading={membersLoading || detailResource.loading}
        onRetry={membersError ? reloadMembers : detailResource.reload}
      >
        {detail ? <ReportDetailContent detail={detail} /> : null}
      </AsyncContent>
    </div>
  );
}

function ReportDetailContent({ detail }: { detail: ReportDetail }) {
  return (
    <div className="grid gap-5">
      <section
        aria-labelledby="report-summary-title"
        className="rounded-2xl border border-[#dbe7e3] bg-white p-5 shadow-sm sm:p-6"
      >
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="max-w-3xl">
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#0f766e]">
              先看整理结果
            </p>
            <h2
              id="report-summary-title"
              className="mt-2 text-xl font-bold text-[#173c38]"
            >
              {detail.summary.text}
            </h2>
            <p className="mt-3 text-sm leading-6 text-[#64748b]">
              {detail.summary.disclaimer}
            </p>
          </div>
          <div className="shrink-0 text-left sm:text-right">
            <StatusBadge tone={statusTone(detail.report.status)}>
              {readableReportStatus(detail.report.status)}
            </StatusBadge>
            <p className="mt-3 text-xs text-[#71847f]">
              更新于 {formatDateTime(detail.report.updated_at)}
            </p>
          </div>
        </div>
      </section>

      <section aria-labelledby="report-metrics-title" className="grid gap-4">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#0f766e]">
            指标概览
          </p>
          <h2 id="report-metrics-title" className="mt-1 text-xl font-bold text-[#173c38]">
            报告中的指标
          </h2>
        </div>
        {detail.metrics.length > 0 ? (
          <div className="grid gap-3 lg:grid-cols-2">
            {detail.metrics.map((metric) => (
              <MetricCard key={metric.id} metric={metric} sources={detail.sources} />
            ))}
          </div>
        ) : (
          <div className="rounded-2xl border border-dashed border-[#cdded8] bg-white p-6 text-sm leading-6 text-[#64748b]">
            这份报告暂时没有可展示的结构化指标，可以结合原始报告与专业人员进一步核对。
          </div>
        )}
      </section>

      {detail.sections.length > 0 ? (
        <section aria-labelledby="report-sections-title" className="grid gap-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#0f766e]">
              内容摘录
            </p>
            <h2 id="report-sections-title" className="mt-1 text-xl font-bold text-[#173c38]">
              报告内容
            </h2>
          </div>
          <div className="grid gap-3">
            {detail.sections.map((section) => {
              const source = findSource(detail, section.source_ref);
              return (
                <article
                  className="rounded-2xl border border-[#dbe7e3] bg-white p-5 shadow-sm"
                  key={section.id}
                >
                  <h3 className="font-bold text-[#173c38]">{section.title}</h3>
                  <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-[#526b66]">
                    {section.content}
                  </p>
                  {source ? <SourceHint source={source} /> : null}
                </article>
              );
            })}
          </div>
        </section>
      ) : null}

      <section aria-labelledby="report-sources-title" className="grid gap-4">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#0f766e]">
            来源说明
          </p>
          <h2 id="report-sources-title" className="mt-1 text-xl font-bold text-[#173c38]">
            这份解读来自哪里
          </h2>
        </div>
        <div className="grid gap-3">
          {detail.sources.map((source) => (
            <article
              className="rounded-2xl border border-[#dbe7e3] bg-white p-5 shadow-sm"
              key={source.id}
            >
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <h3 className="font-bold text-[#173c38]">{source.display_name}</h3>
                  <p className="mt-2 text-xs text-[#71847f]">
                    版本 {source.document_version}
                    {source.page_number ? ` · 第 ${source.page_number} 页` : ""}
                  </p>
                </div>
                <StatusBadge tone={source.verified ? "success" : "warning"}>
                  {source.verified ? "已核对" : "待进一步核对"}
                </StatusBadge>
              </div>
              {source.excerpt ? (
                <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-[#64748b]">
                  “{source.excerpt}”
                </p>
              ) : null}
            </article>
          ))}
        </div>
      </section>

      <section
        aria-labelledby="report-safety-title"
        className={`rounded-2xl border p-5 shadow-sm sm:p-6 ${
          detail.safety.requires_professional_review
            ? "border-[#f2d58a] bg-[#fffbeb]"
            : "border-[#cfe4dd] bg-[#f3faf7]"
        }`}
      >
        <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#0f766e]">
          阅读提示
        </p>
        <h2 id="report-safety-title" className="mt-2 text-lg font-bold text-[#173c38]">
          重要提醒
        </h2>
        <p className="mt-3 text-sm leading-6 text-[#526b66]">{detail.safety.notice}</p>
      </section>
    </div>
  );
}

function MetricCard({
  metric,
  sources,
}: {
  metric: ReportMetric;
  sources: ReportDetail["sources"];
}) {
  const source = sources.find((item) => item.id === metric.source_ref);
  return (
    <article className="rounded-2xl border border-[#dbe7e3] bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-bold text-[#173c38]">{metric.name}</h3>
          {metric.measured_at ? (
            <p className="mt-1 text-xs text-[#71847f]">
              检测时间：{formatDateTime(metric.measured_at)}
            </p>
          ) : null}
        </div>
        <StatusBadge tone={metricTone(metric.interpretation_status)}>
          {readableInterpretationStatus(metric.interpretation_status)}
        </StatusBadge>
      </div>

      <div className="mt-5 flex items-baseline gap-2">
        <span className="text-3xl font-bold tracking-tight text-[#173c38]">
          {metric.value === null ? "暂无" : String(metric.value)}
        </span>
        {metric.unit ? <span className="text-sm font-semibold text-[#71847f]">{metric.unit}</span> : null}
      </div>

      {metric.reference_range ? (
        <p className="mt-3 rounded-xl bg-[#f5faf8] px-3 py-2 text-xs leading-5 text-[#52706b]">
          参考范围：{metric.reference_range.display_text}
        </p>
      ) : null}
      <p className="mt-3 text-sm leading-6 text-[#526b66]">{metric.explanation}</p>
      {metric.trend !== "unknown" ? (
        <p className="mt-3 text-xs font-semibold text-[#64748b]">
          趋势：{readableTrend(metric.trend)}
        </p>
      ) : null}
      {source ? <SourceHint source={source} /> : null}
    </article>
  );
}

function SourceHint({ source }: { source: ReportDetail["sources"][number] }) {
  return (
    <p className="mt-4 border-t border-[#edf2f0] pt-3 text-xs leading-5 text-[#71847f]">
      来源：{source.display_name}
      {source.page_number ? ` · 第 ${source.page_number} 页` : ""}
    </p>
  );
}

function findSource(detail: ReportDetail, sourceRef: string) {
  return detail.sources.find((source) => source.id === sourceRef);
}

function statusTone(status: ReportStatus): "neutral" | "success" | "warning" | "danger" {
  if (status === "ready") return "success";
  if (status === "failed") return "danger";
  if (status === "needs_review") return "warning";
  return "neutral";
}

function readableReportStatus(status: ReportStatus): string {
  const labels: Record<ReportStatus, string> = {
    uploaded: "已收到",
    processing: "整理中",
    ready: "可查看",
    needs_review: "待核对",
    failed: "暂不可用",
  };
  return labels[status];
}

function readableInterpretationStatus(
  status: ReportMetric["interpretation_status"],
): string {
  const labels: Record<ReportMetric["interpretation_status"], string> = {
    within_range: "在参考范围内",
    above_range: "高于参考范围",
    below_range: "低于参考范围",
    not_available: "暂无法判断",
  };
  return labels[status];
}

function metricTone(
  status: ReportMetric["interpretation_status"],
): "neutral" | "success" | "warning" {
  if (status === "within_range") return "success";
  if (status === "not_available") return "neutral";
  return "warning";
}

function readableTrend(trend: ReportMetric["trend"]): string {
  const labels: Record<ReportMetric["trend"], string> = {
    up: "较前次上升",
    down: "较前次下降",
    stable: "与前次相近",
    unknown: "暂无对比",
  };
  return labels[trend];
}
