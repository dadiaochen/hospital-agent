"use client";

import { useEffect, useRef, useState } from "react";
import type { ChangeEvent } from "react";
import Link from "next/link";

import { AsyncContent } from "@/components/AsyncContent";
import { PageHeader } from "@/components/PageHeader";
import { useMember } from "@/components/providers/MemberProvider";
import { StatusBadge } from "@/components/StatusBadge";
import { api } from "@/lib/api/client";
import type { ReportSummary } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";
import { useApiResource } from "@/lib/useApiResource";

type LocalReport = {
  id: string;
  fileName: string;
  fileType: "PDF" | "图片";
  fileSize: number;
  selectedAt: number;
};

const acceptedFileDescription = "支持 PDF、JPG、PNG 等常见图片格式";

export default function ReportsPage() {
  const {
    selectedMemberId,
    selectedMember,
    loading: membersLoading,
    error: membersError,
    reload: reloadMembers,
  } = useMember();
  const [reportsByMember, setReportsByMember] = useState<
    Record<string, LocalReport[]>
  >({});
  const [fileError, setFileError] = useState<string | null>(null);
  const reportSequence = useRef(0);

  const localReports = selectedMemberId
    ? reportsByMember[selectedMemberId] ?? []
    : [];
  const remoteReports = useApiResource(
    selectedMemberId ? `reports:${selectedMemberId}` : null,
    (signal) => {
      if (!selectedMemberId) throw new Error("请先选择家庭成员");
      return api.listReports(selectedMemberId, signal);
    },
  );

  useEffect(() => {
    setFileError(null);
  }, [selectedMemberId]);

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    setFileError(null);

    if (!file) return;

    if (!isSupportedFile(file)) {
      setFileError("请选择 PDF 或图片文件。暂不支持其他文件格式。");
      return;
    }

    if (!selectedMemberId) {
      setFileError("请先选择家庭成员，再选择报告文件。");
      return;
    }

    const report: LocalReport = {
      id: `${selectedMemberId}-${reportSequence.current++}`,
      fileName: file.name,
      fileType:
        file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf")
          ? "PDF"
          : "图片",
      fileSize: file.size,
      selectedAt: Date.now(),
    };

    setReportsByMember((currentReports) => ({
      ...currentReports,
      [selectedMemberId]: [report, ...(currentReports[selectedMemberId] ?? [])],
    }));
  }

  return (
    <div className="grid gap-5">
      <PageHeader
        description="查看已整理报告，或先选择一份 PDF / 图片作为待处理文件。"
        eyebrow="报告解读"
        title="报告解读"
      >
        {selectedMember ? (
          <span className="text-sm font-semibold text-[#31534f]">
            当前：{selectedMember.name}
          </span>
        ) : null}
      </PageHeader>

      <section
        aria-labelledby="report-upload-title"
        className="grid gap-5 rounded-2xl border border-[#dbe7e3] bg-white p-5 shadow-sm sm:p-6 lg:grid-cols-[0.9fr_1.1fr] lg:items-stretch"
      >
        <div className="flex flex-col justify-between gap-5">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#0f766e]">
              选择报告
            </p>
            <h2 id="report-upload-title" className="mt-2 text-xl font-bold text-[#173c38]">
              先选择一份报告
            </h2>
            <p className="mt-3 text-sm leading-6 text-[#64748b]">
              选择后会显示在“最近报告”中，状态会保持为待处理。你可以继续切换家庭成员，文件不会混到其他成员的记录里。
            </p>
          </div>

          <div className="rounded-2xl bg-[#f0f8f5] px-4 py-3 text-sm leading-6 text-[#52706b]">
            {selectedMemberId
              ? "文件仅暂存在当前页面，离开页面后不会保留。"
              : "请先在页面顶部选择家庭成员。"}
          </div>
        </div>

        <div className="grid gap-3">
          <label
            className={`group flex min-h-52 flex-col items-center justify-center rounded-2xl border border-dashed px-5 py-8 text-center transition focus-within:ring-4 focus-within:ring-[#dff3ee] ${
              selectedMemberId
                ? "cursor-pointer border-[#9dcfc2] bg-[#fbfefd] hover:border-[#0f766e] hover:bg-[#f5fbf9]"
                : "cursor-not-allowed border-[#d7e5e0] bg-[#f7faf9]"
            }`}
            htmlFor="report-file-input"
          >
            <input
              accept="application/pdf,image/*,.pdf"
              aria-describedby="report-file-help"
              aria-label="选择报告文件"
              className="sr-only"
              disabled={!selectedMemberId}
              id="report-file-input"
              onChange={handleFileChange}
              type="file"
            />
            <span
              aria-hidden="true"
              className="grid h-12 w-12 place-items-center rounded-2xl bg-[#e2f3ef] text-2xl font-bold text-[#0f766e]"
            >
              ↑
            </span>
            <span className="mt-4 text-sm font-bold text-[#31534f]">
              {selectedMemberId ? "选择报告文件" : "请先选择家庭成员"}
            </span>
            <span id="report-file-help" className="mt-2 text-xs leading-5 text-[#71847f]">
              {acceptedFileDescription}
            </span>
          </label>

          {fileError ? (
            <p className="text-sm leading-6 text-[#b42318]" role="alert">
              {fileError}
            </p>
          ) : null}
        </div>
      </section>

      {localReports[0] ? <PendingFileNotice report={localReports[0]} /> : null}

      <section aria-labelledby="recent-reports-title" className="grid gap-4">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#0f766e]">
              最近报告
            </p>
            <h2 id="recent-reports-title" className="mt-1 text-xl font-bold text-[#173c38]">
              最近报告
            </h2>
          </div>
          <span className="text-xs font-semibold text-[#71847f]">
            {localReports.length + (remoteReports.data?.length ?? 0)} 份
          </span>
        </div>

        <AsyncContent
          empty={
            !membersLoading &&
            !remoteReports.loading &&
            localReports.length === 0 &&
            (remoteReports.data?.length ?? 0) === 0
          }
          emptyDescription="选择 PDF 或图片后，待处理文件会显示在这里。"
          emptyTitle="暂无报告"
          error={membersError ?? remoteReports.error}
          loading={membersLoading || (Boolean(selectedMemberId) && remoteReports.loading)}
          onRetry={membersError ? reloadMembers : remoteReports.reload}
        >
          <div className="grid gap-3">
            {localReports.map((report) => (
              <LocalReportCard key={report.id} report={report} />
            ))}
            {remoteReports.data?.map((report) => (
              <RemoteReportCard key={report.id} report={report} />
            ))}
          </div>
        </AsyncContent>
      </section>
    </div>
  );
}

function PendingFileNotice({ report }: { report: LocalReport }) {
  return (
    <section
      aria-live="polite"
      aria-labelledby="pending-file-title"
      className="rounded-2xl border border-[#f2d58a] bg-[#fffbeb] p-5 shadow-sm sm:p-6"
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#b26c09]">
            已选择的文件
          </p>
          <h2 id="pending-file-title" className="mt-1 text-lg font-bold text-[#713f12]">
            已选择待处理文件
          </h2>
          <p className="mt-2 break-all text-sm font-semibold text-[#854d0e]">
            {report.fileName}
          </p>
          <p className="mt-2 text-xs leading-5 text-[#9a670e]">
            文件目前仅保留在本页，尚未上传或解析。
          </p>
        </div>
        <StatusBadge tone="warning">待处理</StatusBadge>
      </div>
    </section>
  );
}

function LocalReportCard({ report }: { report: LocalReport }) {
  return (
    <article className="rounded-2xl border border-[#dbe7e3] bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#71847f]">
            {report.fileType} · {formatFileSize(report.fileSize)}
          </p>
          <h3 className="mt-2 break-all font-bold text-[#173c38]">{report.fileName}</h3>
          <p className="mt-2 text-xs text-[#71847f]">
            选择时间：{formatSelectedAt(report.selectedAt)}
          </p>
        </div>
        <StatusBadge tone="warning">待处理</StatusBadge>
      </div>
    </article>
  );
}

function RemoteReportCard({ report }: { report: ReportSummary }) {
  return (
    <article className="rounded-2xl border border-[#dbe7e3] bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#71847f]">
            {readableReportType(report.document_type)}
          </p>
          <h3 className="mt-2 break-all font-bold text-[#173c38]">{report.title}</h3>
          <p className="mt-2 text-xs text-[#71847f]">
            更新时间：{formatDateTime(report.updated_at)} · {report.metric_count} 项指标
          </p>
        </div>
        <StatusBadge tone={report.status === "ready" ? "success" : "warning"}>
          {readableReportStatus(report.status)}
        </StatusBadge>
      </div>
      <div className="mt-4 flex justify-end">
        <Link
          className="rounded-lg border border-[#bcd2cc] px-3 py-2 text-xs font-bold text-[#0f766e] hover:bg-[#edf7f3]"
          href={`/reports/${encodeURIComponent(report.id)}`}
        >
          查看报告
        </Link>
      </div>
    </article>
  );
}

function readableReportType(documentType: string) {
  switch (documentType) {
    case "checkup_report":
      return "检查报告";
    case "lab_report":
      return "检验报告";
    case "imaging_report":
      return "影像报告";
    default:
      return "健康报告";
  }
}

function readableReportStatus(status: ReportSummary["status"]) {
  switch (status) {
    case "ready":
      return "可查看";
    case "processing":
      return "处理中";
    case "needs_review":
      return "待人工核对";
    case "failed":
      return "处理失败";
    default:
      return "待处理";
  }
}

function isSupportedFile(file: File) {
  return (
    file.type === "application/pdf" ||
    file.type.startsWith("image/") ||
    /\.(pdf|gif|jpe?g|png|webp|heic|heif)$/i.test(file.name)
  );
}

function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatSelectedAt(timestamp: number) {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    month: "numeric",
    day: "numeric",
  }).format(new Date(timestamp));
}
