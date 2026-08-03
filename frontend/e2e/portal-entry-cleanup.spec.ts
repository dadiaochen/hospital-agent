import { expect, test } from "@playwright/test";

test.describe("public portal entry cleanup", () => {
  test("home only exposes the four public health entry points", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByRole("heading", { name: "先说一件事，我们一起整理" })).toBeVisible();
    await expect(page.locator('a[href="/agent"]').first()).toBeVisible();
    await expect(page.locator('a[href="/reports"]').first()).toBeVisible();
    await expect(page.locator('a[href="/family"]').first()).toBeVisible();
    await expect(page.locator('a[href="/agent-runs"]').first()).toBeVisible();

    await expect(page.getByText(/安全知识检索|附近药店库存|固定演示场景|可审计执行记录|Trace/)).toHaveCount(0);
  });

  test("legacy internal pages redirect to public business entries", async ({ page }) => {
    const redirects = [
      ["/knowledge", "/agent"],
      ["/purchase-plans", "/family"],
      ["/refill-plans", "/family"],
      ["/medicine-box", "/family"],
      ["/reminders", "/agent"],
      ["/agent-runs/legacy-run", "/agent-runs"],
    ] as const;

    for (const [source, destination] of redirects) {
      await page.goto(source);
      await expect(page).toHaveURL(new RegExp(`${destination.replace("/", "\\/")}$`));
    }
  });
});
