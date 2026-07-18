import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiClientError, api, apiPaths, assertMemberScoped } from "./client";

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
