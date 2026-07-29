import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import HomePage from "./page";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

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
  beforeEach(() => {
    push.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it("shows member-scoped health services and safety boundaries", () => {
    render(<HomePage />);

    expect(screen.getByRole("heading", { name: "家庭用药事务，清楚地整理，安心地确认" })).toBeTruthy();
    expect(screen.getByText("陈先生")).toBeTruthy();
    expect(screen.getByRole("link", { name: /整理续方材料/ }).getAttribute("href")).toBe("/agent");
    expect(screen.getByText(/系统不诊断、不开方/)).toBeTruthy();
    expect(screen.getByText(/页面拒绝展示跨成员数据/)).toBeTruthy();
  });

  it("routes the portal search to the knowledge API page", () => {
    render(<HomePage />);
    fireEvent.change(screen.getByRole("textbox", { name: "搜索健康事务或知识" }), {
      target: { value: "续方需要哪些确认" },
    });
    const searchInput = screen.getByRole("textbox", { name: "搜索健康事务或知识" });
    const searchForm = searchInput.closest("form");
    if (!searchForm) throw new Error("search form not found");
    fireEvent.submit(searchForm);

    expect(push).toHaveBeenCalledWith("/knowledge?q=%E7%BB%AD%E6%96%B9%E9%9C%80%E8%A6%81%E5%93%AA%E4%BA%9B%E7%A1%AE%E8%AE%A4");
  });
});
