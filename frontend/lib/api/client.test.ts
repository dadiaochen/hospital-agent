import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiClientError, api, apiPaths, assertMemberScoped } from "./client";
import { makeAgentExecution } from "../agentTestFixtures";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiPaths", () => {
  it("encodes member ids instead of interpolating unsafe path text", () => {
    expect(apiPaths.medicineBox("member/father 1")).toBe(
      "/api/family-members/member%2Ffather%201/medicine-box",
    );
  });

  it("builds optional inventory query parameters", () => {
    expect(apiPaths.pharmacyInventory(" 氨氯地平 ", " 上海 ")).toBe(
      "/api/pharmacy-inventory?medicine_name=%E6%B0%A8%E6%B0%AF%E5%9C%B0%E5%B9%B3&city=%E4%B8%8A%E6%B5%B7",
    );
  });

  it("matches the 2E-1 knowledge search contract", () => {
    expect(apiPaths.knowledgeSearch("续方 确认", "refill_sop")).toBe(
      "/api/knowledge/search?q=%E7%BB%AD%E6%96%B9+%E7%A1%AE%E8%AE%A4&category=refill_sop",
    );
  });

  it("encodes run ids for every audit endpoint", () => {
    expect(apiPaths.agentRunArtifacts("run/with space")).toBe(
      "/api/agent-runs/run%2Fwith%20space/artifacts",
    );
    expect(apiPaths.continueAgentRun("run/with space")).toBe(
      "/api/agent-runs/run%2Fwith%20space/continue",
    );
  });
});

describe("assertMemberScoped", () => {
  it("returns records when every member id matches", () => {
    const records = [{ id: "box-1", member_id: "member-father" }];
    expect(assertMemberScoped(records, "member-father", "家庭药箱")).toEqual(
      records,
    );
  });

  it("rejects a cross-member response before rendering", () => {
    expect(() =>
      assertMemberScoped(
        [{ id: "box-mother", member_id: "member-mother" }],
        "member-father",
        "家庭药箱",
      ),
    ).toThrowError(ApiClientError);

    try {
      assertMemberScoped(
        [{ id: "box-mother", member_id: "member-mother" }],
        "member-father",
        "家庭药箱",
      );
    } catch (error) {
      expect(error).toMatchObject({ code: "context_isolation_failed", status: 409 });
    }
  });

  it("rejects a cross-member medicine-box API response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          items: [{ id: "box-mother", member_id: "member-mother" }],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.listMedicineBox("member-father")).rejects.toMatchObject({
      code: "context_isolation_failed",
      status: 409,
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/family-members/member-father/medicine-box",
      expect.objectContaining({ cache: "no-store" }),
    );
  });
});

describe("agent runtime client", () => {
  it("starts a run with an explicit unconfirmed request", async () => {
    const execution = makeAgentExecution();
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(execution), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.createAgentRun({
      member_id: "member-father",
      idempotency_key: "ui-run-test",
      user_input: "帮我整理续方材料",
      human_confirmation_granted: false,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/agent-runs",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "Content-Type": "application/json" }),
      }),
    );
    const request = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(request.body))).toMatchObject({
      member_id: "member-father",
      human_confirmation_granted: false,
    });
  });

  it("continues a run only with explicit human confirmation", async () => {
    const execution = makeAgentExecution({ status: "completed", confirmationPresent: true });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(execution), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.continueAgentRun("run-3b-demo", "member-father", {
      idempotency_key: "ui-confirm-test",
      confirmation_message: "我确认只创建本地草稿",
      human_confirmation_granted: true,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/agent-runs/run-3b-demo/continue",
      expect.objectContaining({ method: "POST" }),
    );
    const request = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(request.body)).human_confirmation_granted).toBe(true);
  });

  it("rejects cross-member frozen artifacts before rendering", async () => {
    const execution = makeAgentExecution();
    execution.artifacts.run_trace.member_id = "member-mother";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(execution.artifacts), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(
      api.getAgentRunArtifacts("run-3b-demo", "member-father"),
    ).rejects.toMatchObject({
      code: "context_isolation_failed",
      status: 409,
    });
  });
});
