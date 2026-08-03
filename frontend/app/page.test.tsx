import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import HomePage from "./page";

vi.mock("@/components/providers/MemberProvider", () => ({
  useMember: () => ({
    members: [
      {
        id: "member-father",
        name: "陈先生",
        relationship: "father",
        gender: "male",
        birthday: null,
        default_address: null,
      },
    ],
    selectedMember: {
      id: "member-father",
      name: "陈先生",
      relationship: "father",
      gender: "male",
      birthday: null,
      default_address: null,
    },
    selectedMemberId: "member-father",
    setSelectedMemberId: vi.fn(),
    loading: false,
    error: null,
    reload: vi.fn(),
  }),
}));

describe("patient portal home", () => {
  afterEach(() => {
    cleanup();
  });

  it("shows the four public health entry points", () => {
    render(<HomePage />);

    expect(screen.getByRole("heading", { name: "先说一件事，我们一起整理" })).toBeTruthy();
    expect(screen.getByText("陈先生")).toBeTruthy();
    const hrefs = screen.getAllByRole("link").map((link) => link.getAttribute("href"));
    expect(hrefs).toContain("/agent");
    expect(hrefs).toContain("/reports");
    expect(hrefs).toContain("/family");
    expect(hrefs).toContain("/agent-runs");
  });

  it("does not expose internal implementation language or routes", () => {
    render(<HomePage />);

    expect(screen.queryByText(/安全知识检索|附近药店库存|固定演示场景|可审计执行记录|DRAFT|Trace/)).toBeNull();
    const hrefs = screen.getAllByRole("link").map((link) => link.getAttribute("href"));
    expect(hrefs).not.toContain("/knowledge");
    expect(hrefs).not.toContain("/purchase-plans");
    expect(hrefs).not.toContain("/refill-plans");
    expect(hrefs).not.toContain("/medicine-box");
    expect(hrefs).not.toContain("/reminders");
  });
});
