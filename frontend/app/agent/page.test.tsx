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
  it("starts with an empty state and submits a natural-language question", async () => {
    const userInput = "我爸的降压药快吃完了，帮我看看能不能续方。";
    const fetchMock = runtimeFetch(makeAgentExecution());
    vi.stubGlobal("fetch", fetchMock);
    renderPage();

    expect(await screen.findByText("你好，想从哪件事开始？")).toBeTruthy();
    await screen.findByText("正在为：陈父");
    const submitButton = await screen.findByRole("button", { name: "开始咨询" });
    const input = screen.getByRole("textbox", { name: "输入你的问题" });
    expect(submitButton).toHaveProperty("disabled", true);

    await userEvent.click(screen.getByRole("button", { name: "用药与续方" }));
    expect(input).toHaveProperty("value", "家人的药快吃完了，帮我整理续方需要准备的信息。");
    await userEvent.clear(input);
    await userEvent.type(input, userInput);
    expect(submitButton).toHaveProperty("disabled", false);
    await userEvent.click(submitButton);

    await screen.findByText("整理结果");
    expect(screen.getAllByText(userInput).length).toBeGreaterThan(0);
    const postCall = fetchMock.mock.calls.find(
      ([, init]) => (init as RequestInit | undefined)?.method === "POST",
    );
    const body = JSON.parse(String((postCall?.[1] as RequestInit).body));
    expect(body).toMatchObject({
      member_id: "member-father",
      user_input: userInput,
      human_confirmation_granted: false,
    });
    expect(body.medication_name).toBeUndefined();
    expect(body.city).toBeUndefined();
  });

  it("renders a grounded answer and sends the initial unconfirmed contract", async () => {
    const execution = makeAgentExecution();
    const fetchMock = runtimeFetch(execution);
    vi.stubGlobal("fetch", fetchMock);
    renderPage();

    await submitPrompt("我爸的降压药快吃完了，帮我看看能不能续方。");

    expect(await screen.findByText("整理结果")).toBeTruthy();
    expect(screen.getByText("信息已经整理好了")).toBeTruthy();
    expect(screen.getByText(execution.artifacts.run_trace.final_answer.content)).toBeTruthy();
    expect(screen.getByText("参考信息")).toBeTruthy();
    expect(screen.getByText("安全提示")).toBeTruthy();
    expect(screen.queryByText("DRAFT")).toBeNull();
    expect(screen.queryByText("task-3b-demo")).toBeNull();
    expect(screen.queryByText(/source_id:/)).toBeNull();
    expect(screen.getByText("请确认是否继续")).toBeTruthy();
    expect(screen.getByRole("button", { name: "确认并继续" })).toBeTruthy();
    expect(screen.queryByText(/本地草稿|外部提交|continuation run/)).toBeNull();

    const postCall = fetchMock.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "POST");
    const body = JSON.parse(String((postCall?.[1] as RequestInit).body));
    expect(body).toMatchObject({
      member_id: "member-father",
      human_confirmation_granted: false,
      user_input: "我爸的降压药快吃完了，帮我看看能不能续方。",
    });
  });

  it("continues only after the user-readable acknowledgement", async () => {
    const initial = makeAgentExecution({ intent: "reminder" });
    const continued = makeAgentExecution({
      runId: "run-3b-continued",
      status: "completed",
      confirmationPresent: true,
      intent: "reminder",
      finalAnswer: "本地提醒草稿已创建，尚未提交到外部系统。",
    });
    const fetchMock = runtimeFetch(initial, continued);
    vi.stubGlobal("fetch", fetchMock);
    renderPage();

    await submitPrompt("帮我给妈妈设置每天早晚的用药提醒。");
    const confirmButton = await screen.findByRole("button", { name: "确认并继续" });
    expect(confirmButton).toHaveProperty("disabled", true);

    await userEvent.click(screen.getByRole("checkbox", { name: "确认继续" }));
    await userEvent.click(confirmButton);

    expect(await screen.findByText("我已经根据现有健康记录整理了用药提醒准备内容。")).toBeTruthy();
    expect(screen.getByText("这次咨询已完成")).toBeTruthy();
    expect(screen.getByText("这次整理已经完成，可以回看这次咨询结果。")).toBeTruthy();
    expect(screen.queryByText("相关信息已经整理好，下一步需要你确认后才能继续。")).toBeNull();
    expect(screen.queryByRole("button", { name: "确认并继续" })).toBeNull();
    expect(screen.queryByText(/外部提交状态：/)).toBeNull();
    expect(screen.queryByText(/本地提醒草稿|外部系统/)).toBeNull();

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

    await submitPrompt("我爸的降压药快吃完了，帮我看看能不能续方。");
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

    await submitPrompt("我爸的降压药快吃完了，帮我看看能不能续方。");
    await userEvent.selectOptions(screen.getByLabelText("当前家庭成员"), "member-mother");

    await act(async () => {
      resolveRun?.(jsonResponse(execution, 201));
      await pendingRun;
    });

    expect(screen.queryByText(execution.artifacts.run_trace.final_answer.content)).toBeNull();
    expect(screen.getByText("正在为：陈母")).toBeTruthy();
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

    await submitPrompt("我爸这个降压药能不能加量？");

    expect(await screen.findByText("安全提示")).toBeTruthy();
    expect(screen.getByText("这件事需要专业人员确认")).toBeTruthy();
    expect(screen.queryByText("dosage_change_request")).toBeNull();
    expect(screen.queryByRole("button", { name: "确认并继续" })).toBeNull();
  });

  it("projects internal backend answer language into a user-readable result", async () => {
    const internalAnswer = "Prepared a local refill result from sources: health_profiles, prescriptions, medicine_box_items. No hospital, purchase, payment, or reminder action was submitted.";
    vi.stubGlobal("fetch", runtimeFetch(makeAgentExecution({ finalAnswer: internalAnswer })));
    renderPage();

    await submitPrompt("请帮我整理父亲最近的用药记录");

    expect(await screen.findByText("我已经根据家庭健康记录整理了续方准备所需的信息。")).toBeTruthy();
    expect(screen.queryByText(internalAnswer)).toBeNull();
    expect(screen.queryByText(/Prepared a local|No hospital, purchase/)).toBeNull();
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

async function submitPrompt(userInput: string) {
  await screen.findByText("正在为：陈父");
  await userEvent.type(screen.getByRole("textbox", { name: "输入你的问题" }), userInput);
  await userEvent.click(screen.getByRole("button", { name: "开始咨询" }));
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
