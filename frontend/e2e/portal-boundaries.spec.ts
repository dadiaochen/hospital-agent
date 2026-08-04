import { expect, test } from "@playwright/test";

test.describe("4C-3 患者端边界回归", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/agent");
    await expect(page.getByLabel("当前家庭成员")).toBeVisible();
  });

  test("切换 member_id 后清理前一成员的运行结果", async ({ page }) => {
    const memberSelect = page.getByLabel("当前家庭成员");
    const initialMember = await memberSelect.inputValue();
    const options = memberSelect.locator("option");
    const optionCount = await options.count();
    expect(optionCount).toBeGreaterThanOrEqual(2);

    await submitPrompt(page, "我爸的降压药快吃完了，帮我看看能不能续方。");
    await expect(page.getByText("整理结果", { exact: true })).toBeVisible();

    const switchedValue = await findDifferentMemberValue(memberSelect, initialMember, optionCount);
    await memberSelect.selectOption(switchedValue);

    await expect(memberSelect).toHaveValue(switchedValue);
    await expect(page.getByText("整理结果", { exact: true })).toHaveCount(0);
    await expect(page.getByText("DRAFT", { exact: true })).toHaveCount(0);
  });

  test("Agent API 失败时展示错误而不是伪造成功答案", async ({ page }) => {
    await page.route("**/api/agent-runs", async (route) => {
      if (route.request().method() !== "POST") {
        await route.continue();
        return;
      }
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({
          error: {
            code: "provider_unavailable",
            message: "模拟 Provider 不可用",
          },
        }),
      });
    });

    await submitPrompt(page, "我爸的降压药快吃完了，帮我看看能不能续方。");

    await expect(page.getByText("模拟 Provider 不可用", { exact: true })).toBeVisible();
    await expect(page.getByText("整理结果", { exact: true })).toHaveCount(0);
    await expect(page.getByText("DRAFT", { exact: true })).toHaveCount(0);
  });
});

async function findDifferentMemberValue(
  select: ReturnType<import("@playwright/test").Page["getByLabel"]>,
  currentValue: string,
  optionCount: number,
): Promise<string> {
  for (let index = 0; index < optionCount; index += 1) {
    const value = await select.locator("option").nth(index).getAttribute("value");
    if (value && value !== currentValue) return value;
  }
  throw new Error("测试数据至少需要两个家庭成员");
}

async function submitPrompt(page: import("@playwright/test").Page, prompt: string) {
  await page.getByRole("textbox", { name: "输入你的问题" }).fill(prompt);
  await page.getByRole("button", { name: "开始咨询" }).click();
}
