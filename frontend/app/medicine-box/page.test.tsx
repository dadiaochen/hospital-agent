import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import MedicineBoxPage from "@/app/medicine-box/page";
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

describe("MedicineBoxPage member isolation", () => {
  it("clears the previous member while switching and renders the new response", async () => {
    let resolveMother: ((response: Response) => void) | undefined;
    const motherResponse = new Promise<Response>((resolve) => {
      resolveMother = resolve;
    });
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = requestUrl(input);
      if (url.endsWith("/api/family-members")) {
        return Promise.resolve(jsonResponse({ items: members }));
      }
      if (url.endsWith("/member-father/medicine-box")) {
        return Promise.resolve(
          jsonResponse({ items: [medicine("box-father", "member-father", "父亲用药")] }),
        );
      }
      if (url.endsWith("/member-mother/medicine-box")) {
        return motherResponse;
      }
      throw new Error(`unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();
    expect(await screen.findByText("父亲用药")).toBeTruthy();

    await userEvent.selectOptions(
      screen.getByLabelText("当前家庭成员"),
      "member-mother",
    );

    await waitFor(() => expect(screen.queryByText("父亲用药")).toBeNull());
    expect(screen.getByText("数据加载中")).toBeTruthy();

    resolveMother?.(
      jsonResponse({ items: [medicine("box-mother", "member-mother", "母亲用药")] }),
    );
    expect(await screen.findByText("母亲用药")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/family-members/member-mother/medicine-box",
      expect.objectContaining({ cache: "no-store" }),
    );
  });

  it("shows a real empty state for a successful empty response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = requestUrl(input);
        if (url.endsWith("/api/family-members")) {
          return Promise.resolve(jsonResponse({ items: [members[0]] }));
        }
        if (url.endsWith("/member-father/medicine-box")) {
          return Promise.resolve(jsonResponse({ items: [] }));
        }
        throw new Error(`unexpected request: ${url}`);
      }),
    );

    renderPage();

    expect(await screen.findByText("药箱暂时是空的")).toBeTruthy();
    expect(screen.getByText(/当前成员没有药箱记录/)).toBeTruthy();
  });

  it("renders an error instead of cross-member medicine data", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = requestUrl(input);
        if (url.endsWith("/api/family-members")) {
          return Promise.resolve(jsonResponse({ items: [members[0]] }));
        }
        if (url.endsWith("/member-father/medicine-box")) {
          return Promise.resolve(
            jsonResponse({ items: [medicine("box-mother", "member-mother", "不应展示")] }),
          );
        }
        throw new Error(`unexpected request: ${url}`);
      }),
    );

    renderPage();

    expect(
      await screen.findByText("家庭药箱 返回了其他家庭成员的数据，页面已停止展示"),
    ).toBeTruthy();
    expect(screen.queryByText("不应展示")).toBeNull();
  });
});

function renderPage() {
  render(
    <MemberProvider>
      <MemberSwitcher />
      <MedicineBoxPage />
    </MemberProvider>,
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

function medicine(id: string, memberId: string, name: string) {
  return {
    id,
    member_id: memberId,
    medicine_name: name,
    specification: "5mg",
    total_quantity: 30,
    remaining_quantity: 10,
    dosage: "每次一片",
    frequency: "每日一次",
    purchased_at: "2026-07-01",
    estimated_remaining_days: 10,
    safety_note: null,
  };
}
