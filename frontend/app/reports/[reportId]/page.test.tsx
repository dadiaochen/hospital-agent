import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import ReportDetailPage from "@/app/reports/[reportId]/page";
import { MemberSwitcher } from "@/components/MemberSwitcher";
import { MemberProvider } from "@/components/providers/MemberProvider";

vi.mock("next/navigation", () => ({
  useParams: () => ({ reportId: "report-1" }),
}));

const members = [
  {
    id: "member-father",
    name: "陈父",
    relationship: "father",
    gender: "male",
    birthday: null,
    default_address: "上海",
  },
  {
    id: "member-mother",
    name: "陈母",
    relationship: "mother",
    gender: "female",
    birthday: null,
    default_address: "上海",
  },
];

const detail = {
  report: {
    id: "report-1",
    member_id: "member-father",
    title: "Annual Checkup Report",
    document_type: "checkup_report",
    status: "ready" as const,
    reported_at: "2026-07-01T08:00:00Z",
    updated_at: "2026-07-02T08:00:00Z",
    document_version: "1.0",
    source_name: "Annual Checkup Report",
    metric_count: 1,
  },
  summary: {
    text: "报告中整理出 1 项指标，建议结合来源内容阅读。",
    disclaimer: "以下内容是报告信息整理，不替代医生判断。",
  },
  metrics: [
    {
      id: "metric-glucose",
      name: "空腹血糖",
      value: 5.6,
      unit: "mmol/L",
      reference_range: {
        low: 3.9,
        high: 6.1,
        display_text: "3.9–6.1 mmol/L",
      },
      interpretation_status: "within_range" as const,
      trend: "stable" as const,
      measured_at: "2026-07-01T08:00:00Z",
      explanation: "该数值在报告提供的参考范围内。",
      source_ref: "source-report-1",
    },
  ],
  sections: [
    {
      id: "section-summary",
      title: "检查摘要",
      content: "本次检查包含常规实验室指标。",
      source_ref: "source-report-1",
    },
  ],
  sources: [
    {
      id: "source-report-1",
      source_type: "medical_report" as const,
      display_name: "Annual Checkup Report",
      document_version: "1.0",
      page_number: 1,
      excerpt: "空腹血糖 5.6 mmol/L",
      verified: true,
    },
  ],
  safety: {
    requires_professional_review: true,
    notice: "如对指标含义或后续安排有疑问，请带上原始报告咨询专业人员。",
  },
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ReportDetailPage", () => {
  it("shows readable metrics and source information without internal identifiers", async () => {
    stubReportApi();
    renderPage();

    expect(await screen.findByText("空腹血糖")).toBeTruthy();
    expect(screen.getByText("5.6")).toBeTruthy();
    expect(screen.getByText("参考范围：3.9–6.1 mmol/L")).toBeTruthy();
    expect(screen.getAllByText("Annual Checkup Report").length).toBeGreaterThan(0);
    expect(screen.getByText("如对指标含义或后续安排有疑问，请带上原始报告咨询专业人员。")).toBeTruthy();
    expect(screen.queryByText("source-report-1")).toBeNull();
  });

  it("clears the previous report when the selected member changes", async () => {
    stubReportApi();
    renderPage();

    expect(await screen.findByText("空腹血糖")).toBeTruthy();
    await userEvent.selectOptions(
      screen.getByLabelText("当前家庭成员"),
      "member-mother",
    );

    await waitFor(() => {
      expect(screen.queryByText("空腹血糖")).toBeNull();
    });
    expect(await screen.findByText("数据暂时无法加载")).toBeTruthy();
  });
});

function renderPage() {
  render(
    <MemberProvider>
      <MemberSwitcher />
      <ReportDetailPage />
    </MemberProvider>,
  );
}

function stubReportApi() {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = requestUrl(input);
      if (url.endsWith("/api/family-members")) {
        return Promise.resolve(jsonResponse({ items: members }));
      }
      if (url.endsWith("/api/family-members/member-father/reports/report-1")) {
        return Promise.resolve(jsonResponse(detail));
      }
      if (url.endsWith("/api/family-members/member-mother/reports/report-1")) {
        return Promise.resolve(
          jsonResponse({
            ...detail,
            report: { ...detail.report, member_id: "member-father" },
          }),
        );
      }
      throw new Error(`unexpected request: ${url}`);
    }),
  );
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.toString();
  return input.url;
}

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}
