import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import ReportsPage from "@/app/reports/page";
import { MemberSwitcher } from "@/components/MemberSwitcher";
import { MemberProvider } from "@/components/providers/MemberProvider";

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

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ReportsPage", () => {
  it("shows an empty recent reports state for the selected member", async () => {
    stubFamilyMembers([members[0]]);

    renderPage();

    expect(await screen.findByText("暂无报告")).toBeTruthy();
    expect(
      await screen.findByText("选择 PDF 或图片后，待处理文件会显示在这里。"),
    ).toBeTruthy();
    expect(screen.queryByText("Upload a report")).toBeNull();
    expect(screen.queryByText("Recent reports")).toBeNull();
    expect(screen.queryByText("member-father")).toBeNull();
  });

  it("shows a selected PDF as a pending local report", async () => {
    stubFamilyMembers([members[0]]);

    renderPage();

    await screen.findByText("暂无报告");
    const file = new File(["report"], "年度检查报告.pdf", {
      type: "application/pdf",
    });

    await userEvent.upload(screen.getByLabelText("选择报告文件"), file);

    expect((await screen.findAllByText("年度检查报告.pdf")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("待处理").length).toBeGreaterThan(0);
    expect(screen.getByText("文件目前仅保留在本页，尚未上传或解析。")).toBeTruthy();
  });

  it("shows a ready report from the report detail contract", async () => {
    stubFamilyMembers([members[0]], {
      "member-father": [
        {
          id: "report-1",
          member_id: "member-father",
          title: "Annual Checkup Report",
          document_type: "checkup_report",
          status: "ready",
          reported_at: "2026-07-01T08:00:00Z",
          updated_at: "2026-07-02T08:00:00Z",
          document_version: "1.0",
          source_name: "Annual Checkup Report",
          metric_count: 2,
        },
      ],
    });

    renderPage();

    expect(await screen.findByText("Annual Checkup Report")).toBeTruthy();
    expect(screen.getByText("可查看")).toBeTruthy();
    expect(screen.getByRole("link", { name: "查看报告" }).getAttribute("href")).toBe(
      "/reports/report-1",
    );
  });

  it("keeps selected files isolated when the current member changes", async () => {
    stubFamilyMembers(members);

    renderPage();

    await screen.findByText("暂无报告");
    await userEvent.upload(
      screen.getByLabelText("选择报告文件"),
      new File(["father"], "父亲检查报告.pdf", { type: "application/pdf" }),
    );
    expect((await screen.findAllByText("父亲检查报告.pdf")).length).toBeGreaterThan(0);

    await userEvent.selectOptions(
      screen.getByLabelText("当前家庭成员"),
      "member-mother",
    );

    expect(screen.queryByText("父亲检查报告.pdf")).toBeNull();
    expect(screen.getByText("暂无报告")).toBeTruthy();

    await userEvent.upload(
      screen.getByLabelText("选择报告文件"),
      new File(["mother"], "母亲检查报告.png", { type: "image/png" }),
    );
    expect((await screen.findAllByText("母亲检查报告.png")).length).toBeGreaterThan(0);
    expect(screen.queryByText("父亲检查报告.pdf")).toBeNull();
  });
});

function renderPage() {
  render(
    <MemberProvider>
      <MemberSwitcher />
      <ReportsPage />
    </MemberProvider>,
  );
}

function stubFamilyMembers(items: typeof members, reports: Record<string, unknown[]> = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = requestUrl(input);
      if (url.endsWith("/api/family-members")) {
        return Promise.resolve(jsonResponse({ items }));
      }
      if (url.includes("/api/family-members/") && url.endsWith("/reports")) {
        const memberId = url.split("/api/family-members/")[1].split("/")[0];
        return Promise.resolve(jsonResponse({ items: reports[memberId] ?? [] }));
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
