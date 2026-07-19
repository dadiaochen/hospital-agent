import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentPage from "@/app/agent/page";
import { MemberSwitcher } from "@/components/MemberSwitcher";
import { MemberProvider } from "@/components/providers/MemberProvider";
import { makeAgentExecution, testMembers } from "@/lib/agentTestFixtures";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AgentPage", () => {
  it("renders a grounded answer and sends the initial unconfirmed contract", async () => {
    const execution = makeAgentExecution();
    const fetchMock = runtimeFetch(execution);
    vi.stubGlobal("fetch", fetchMock);
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: "正常续方" }));
    await userEvent.click(screen.getByRole("button", { name: "运行 Agent" }));

    expect(await screen.findByText("结构化答案")).toBeTruthy();
    expect(screen.getByText(execution.artifacts.run_trace.final_answer.content)).toBeTruthy();
    expect(screen.getByText(/source_id: source-tool-1/)).toBeTruthy();
    expect(screen.getByText("human_confirmation_required")).toBeTruthy();
    expect(screen.getByRole("button", { name: "确认并创建本地草稿" })).toBeTruthy();

    const postCall = fetchMock.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "POST");
    const body = JSON.parse(String((postCall?.[1] as RequestInit).body));
    expect(body).toMatchObject({
      member_id: "member-father",
      human_confirmation_granted: false,
      medication_name: "苯磺酸氨氯地平片",
    });
  });

  it("continues only after the local-draft acknowledgement", async () => {
    const initial = makeAgentExecution();
    const continued = makeAgentExecution({
      runId: "run-3b-continued",
      status: "completed",
      confirmationPresent: true,
      finalAnswer: "本地提醒草稿已创建，尚未提交到外部系统。",
    });
    const fetchMock = runtimeFetch(initial, continued);
    vi.stubGlobal("fetch", fetchMock);
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: "用药提醒" }));
    await userEvent.click(screen.getByRole("button", { name: "运行 Agent" }));
    const confirmButton = await screen.findByRole("button", { name: "确认并创建本地草稿" });
    expect(confirmButton).toHaveProperty("disabled", true);

    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(confirmButton);

    expect(await screen.findByText("本地提醒草稿已创建，尚未提交到外部系统。")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "确认并创建本地草稿" })).toBeNull();
    expect(screen.getByText(/外部提交状态：/)).toBeTruthy();

    const postBodies = fetchMock.mock.calls
      .filter(([, init]) => (init as RequestInit | undefined)?.method === "POST")
      .map(([, init]) => JSON.parse(String((init as RequestInit).body)));
    expect(postBodies).toHaveLength(2);
    expect(postBodies[1].human_confirmation_granted).toBe(true);
  });

  it("clears the previous result when the selected member changes", async () => {
    const execution = makeAgentExecution();
    vi.stubGlobal("fetch", runtimeFetch(execution));
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: "正常续方" }));
    await userEvent.click(screen.getByRole("button", { name: "运行 Agent" }));
    expect(await screen.findByText(execution.artifacts.run_trace.final_answer.content)).toBeTruthy();

    await userEvent.selectOptions(screen.getByLabelText("当前家庭成员"), "member-mother");
    await waitFor(() => expect(screen.queryByText(execution.artifacts.run_trace.final_answer.content)).toBeNull());
  });

  it("ignores an in-flight response after the member changes", async () => {
    const execution = makeAgentExecution();
    let resolveRun: ((response: Response) => void) | undefined;
    const pendingRun = new Promise<Response>((resolve) => { resolveRun = resolve; });
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input);
      if (url.endsWith("/api/family-members")) {
        return Promise.resolve(jsonResponse({ items: testMembers }));
      }
      if (url.endsWith("/api/agent-runs") && init?.method === "POST") {
        return pendingRun;
      }
      throw new Error(`unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: "正常续方" }));
    await userEvent.click(screen.getByRole("button", { name: "运行 Agent" }));
    await userEvent.selectOptions(screen.getByLabelText("当前家庭成员"), "member-mother");

    await act(async () => {
      resolveRun?.(jsonResponse(execution, 201));
      await pendingRun;
    });

    expect(screen.queryByText(execution.artifacts.run_trace.final_answer.content)).toBeNull();
    expect(screen.getByText("当前成员：陈母")).toBeTruthy();
  });

  it("does not offer a business confirmation after a safety block", async () => {
    const blocked = makeAgentExecution({
      status: "blocked",
      blocked: true,
      waitingForConfirmation: false,
      finalAnswer: "该请求涉及自行加量，已停止业务执行，请联系医生。",
    });
    vi.stubGlobal("fetch", runtimeFetch(blocked));
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: "高风险拦截" }));
    await userEvent.click(screen.getByRole("button", { name: "运行 Agent" }));

    expect(await screen.findByText("安全拦截")).toBeTruthy();
    expect(screen.getByText("dosage_change_request")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "确认并创建本地草稿" })).toBeNull();
  });
});

function renderPage() {
  render(
    <MemberProvider>
      <MemberSwitcher />
      <AgentPage />
    </MemberProvider>,
  );
}

function runtimeFetch(initial: ReturnType<typeof makeAgentExecution>, continued?: ReturnType<typeof makeAgentExecution>) {
  let postCount = 0;
  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = requestUrl(input);
    if (url.endsWith("/api/family-members")) {
      return Promise.resolve(jsonResponse({ items: testMembers }));
    }
    if (url.endsWith("/api/agent-runs") && init?.method === "POST") {
      postCount += 1;
      return Promise.resolve(jsonResponse(initial, 201));
    }
    if (url.endsWith("/continue") && init?.method === "POST" && continued) {
      postCount += 1;
      return Promise.resolve(jsonResponse(continued, 201));
    }
    throw new Error(`unexpected request ${postCount}: ${url}`);
  });
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
