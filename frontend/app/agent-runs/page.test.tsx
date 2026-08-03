import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentRunsPage from "@/app/agent-runs/page";
import { MemberSwitcher } from "@/components/MemberSwitcher";
import { MemberProvider } from "@/components/providers/MemberProvider";
import type { AgentRun } from "@/lib/api/types";

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

describe("AgentRunsPage", () => {
  it("shows user-readable consultation history without internal identifiers", async () => {
    stubHistoryApi();
    renderPage();

    expect((await screen.findAllByText("历史咨询")).length).toBeGreaterThan(0);
    expect(await screen.findByText("帮我看看爸爸的续方准备")).toBeTruthy();
    expect(screen.getByText("待确认")).toBeTruthy();
    expect(screen.getByText("续方准备")).toBeTruthy();
    expect(screen.getByText("需要你确认")).toBeTruthy();
    expect(screen.getByText("整理结果")).toBeTruthy();
    expect(await screen.findByText("我已经根据家庭健康记录整理了续方准备所需的信息。")).toBeTruthy();
    expect(screen.queryByText(/Prepared a local|No hospital, purchase/)).toBeNull();
    expect(screen.queryByText("run_id: run-father")).toBeNull();
    expect(screen.queryByText("Groundedness")).toBeNull();
    expect(screen.queryByText(/Trace|工具链|fallback/)).toBeNull();
  });

  it("shows only the selected member's consultation history", async () => {
    stubHistoryApi();
    renderPage();

    expect(await screen.findByText("帮我看看爸爸的续方准备")).toBeTruthy();
    await userEvent.selectOptions(
      screen.getByLabelText("当前家庭成员"),
      "member-mother",
    );

    await waitFor(() => {
      expect(screen.queryByText("帮我看看爸爸的续方准备")).toBeNull();
    });
    expect(await screen.findByText("帮我看看妈妈的报告准备")).toBeTruthy();
    expect(screen.queryByText("爸爸的整理结果")).toBeNull();
  });
});

function renderPage() {
  render(
    <MemberProvider>
      <MemberSwitcher />
      <AgentRunsPage />
    </MemberProvider>,
  );
}

function stubHistoryApi() {
  const runsByMember: Record<string, AgentRun[]> = {
    "member-father": [
      makeRun(
        "run-father",
        "member-father",
        "帮我看看爸爸的续方准备",
        "refill",
        "needs_confirmation",
        "Prepared a local refill result from sources: health_profiles, prescriptions, medicine_box_items. No hospital, purchase, payment, or reminder action was submitted.",
      ),
    ],
    "member-mother": [
      makeRun(
        "run-mother",
        "member-mother",
        "帮我看看妈妈的报告准备",
        "report",
        "completed",
        "妈妈的整理结果：已记录报告准备事项。",
      ),
    ],
  };

  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = new URL(requestUrl(input), "http://localhost");
      if (url.pathname === "/api/family-members") {
        return Promise.resolve(jsonResponse({ items: members }));
      }
      if (url.pathname === "/api/agent-runs") {
        const memberId = url.searchParams.get("member_id") ?? "";
        return Promise.resolve(jsonResponse({ items: runsByMember[memberId] ?? [] }));
      }
      throw new Error(`unexpected request: ${url.toString()}`);
    }),
  );
}

function makeRun(
  id: string,
  memberId: string,
  userGoal: string,
  intent: string,
  status: string,
  finalAnswer: string,
): AgentRun {
  return {
    id,
    user_id: "user-demo",
    member_id: memberId,
    user_goal: userGoal,
    intent,
    status,
    final_answer: finalAnswer,
    need_human_confirmation: status === "needs_confirmation",
    safety_result: {},
    started_at: "2026-08-02T08:00:00Z",
    ended_at: "2026-08-02T08:01:00Z",
    duration_ms: 1000,
    step_count: 3,
    task_success: status === "completed",
    groundedness_score: 1,
    hallucination_flag: false,
    human_confirmation_rate: status === "completed" ? 1 : 0,
  };
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
