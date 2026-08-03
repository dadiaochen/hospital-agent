import { describe, expect, it } from "vitest";

import { navigationItems } from "./navigation";

describe("public navigation", () => {
  it("only contains user-facing health entry points", () => {
    expect(navigationItems.map((item) => item.href)).toEqual([
      "/agent",
      "/agent-runs",
      "/family",
      "/reports",
    ]);
  });
});
