import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import FamilyPage from "@/app/family/page";
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

describe("FamilyPage", () => {
  it("renders a user-readable health overview without internal identifiers", async () => {
    stubFamilyApi();
    renderPage();

    expect(await screen.findByText("把家人的健康记录放在一起")).toBeTruthy();
    expect(await screen.findByText("父亲常用药")).toBeTruthy();
    expect(screen.getByText("当前用药与药箱余量")).toBeTruthy();
    expect(screen.getByText("处方、复诊与购药记录")).toBeTruthy();
    expect(await screen.findByText("已整理续方准备材料，等待你的确认。")).toBeTruthy();
    expect(screen.queryByText(/Local refill draft|run-father/)).toBeNull();
    expect(screen.queryByText("member-father")).toBeNull();
    expect(screen.queryByText(/\/api\//)).toBeNull();
  });

  it("clears the previous member overview before showing the next member", async () => {
    stubFamilyApi();
    renderPage();

    expect(await screen.findByText("父亲常用药")).toBeTruthy();
    await userEvent.selectOptions(
      screen.getByLabelText("当前家庭成员"),
      "member-mother",
    );

    await waitFor(() => {
      expect(screen.queryByText("父亲常用药")).toBeNull();
    });
    expect(await screen.findByText("母亲常用药")).toBeTruthy();
    expect(screen.queryByText("父亲检查医院")).toBeNull();
  });
});

function renderPage() {
  render(
    <MemberProvider>
      <MemberSwitcher />
      <FamilyPage />
    </MemberProvider>,
  );
}

function stubFamilyApi() {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = requestUrl(input);
      if (url.endsWith("/api/family-members")) {
        return Promise.resolve(jsonResponse({ items: members }));
      }

      for (const member of members) {
        if (url.endsWith(`/${member.id}/health-profile`)) {
          return Promise.resolve(
            jsonResponse({
              member,
              profile: {
                member_id: member.id,
                chronic_disease_tags: [member.id === "member-father" ? "血压记录" : "血糖记录"],
                allergies: [],
                current_medications: [
                  { medicine_name: member.id === "member-father" ? "父亲常用药" : "母亲常用药" },
                ],
                health_notes: null,
                safety_notes: [],
              },
            }),
          );
        }
        if (url.endsWith(`/${member.id}/medicine-box`)) {
          return Promise.resolve(
            jsonResponse({
              items: [
                {
                  id: `${member.id}-medicine-box`,
                  member_id: member.id,
                  medicine_name: member.id === "member-father" ? "父亲药箱药品" : "母亲药箱药品",
                  specification: null,
                  total_quantity: 10,
                  remaining_quantity: 5,
                  dosage: "按记录使用",
                  frequency: "每日",
                  purchased_at: null,
                  estimated_remaining_days: 5,
                  safety_note: null,
                },
              ],
            }),
          );
        }
        if (url.endsWith(`/${member.id}/prescriptions`)) {
          return Promise.resolve(
            jsonResponse({
              items: [
                {
                  id: `${member.id}-prescription`,
                  member_id: member.id,
                  prescription_no: null,
                  doctor_name: "记录医生",
                  hospital_name: member.id === "member-father" ? "父亲检查医院" : "母亲检查医院",
                  doctor_diagnosis_summary: null,
                  medicine_items: [],
                  issued_at: null,
                  expires_at: null,
                  status: "active",
                  doctor_confirmation_required: false,
                  safety_note: null,
                },
              ],
            }),
          );
        }
        if (url.endsWith(`/${member.id}/purchase-records`)) {
          return Promise.resolve(jsonResponse({ items: [] }));
        }
        if (url.includes(`/api/confirmation-drafts?member_id=${member.id}`)) {
          return Promise.resolve(
            jsonResponse({
              items:
                member.id === "member-father"
                  ? [
                      {
                        draft_id: "draft-father",
                        member_id: member.id,
                        draft_type: "refill_request",
                        status: "draft",
                        summary: "Local refill draft for run run-father.",
                        created_at: "2026-08-02T08:01:00Z",
                      },
                    ]
                  : [],
            }),
          );
        }
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
