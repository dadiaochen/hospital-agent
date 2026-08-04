import { expect, test } from "@playwright/test";

const confirmButton = "确认并继续";

test.describe("4C-3 Agent 黄金链路", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/agent");
    await expect(page.getByLabel("当前家庭成员")).toBeVisible();
  });

  test("续方：首次咨询完成整理，未确认不会推进", async ({ page }) => {
    await submitPrompt(page, "我爸的降压药快吃完了，帮我看看能不能续方。");

    await expect(page.getByText("信息已经整理好了", { exact: true })).toBeVisible();
    await expect(page.getByText("请确认是否继续")).toBeVisible();
    await expect(page.getByRole("button", { name: confirmButton })).toBeDisabled();
    await expect(page.getByText("整理结果", { exact: true })).toBeVisible();
  });

  test("续方：确认后产生 continuation run 并完成本地草稿", async ({ page }) => {
    await submitPrompt(page, "我爸的降压药快吃完了，帮我看看能不能续方。");

    const confirmation = page.getByRole("button", { name: confirmButton });
    await expect(confirmation).toBeVisible();
    await expect(confirmation).toBeDisabled();
    await page.getByRole("checkbox", { name: "确认继续" }).check();
    await expect(confirmation).toBeEnabled();
    await confirmation.click();

    await expect(page.getByText("这次咨询已完成", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: confirmButton })).toHaveCount(0);
  });

  test("用药提醒：确认后完成本地提醒草稿", async ({ page }) => {
    await submitPrompt(page, "帮我给妈妈设置每天早晚的用药提醒。");

    await expect(page.getByText("信息已经整理好了", { exact: true })).toBeVisible();
    await page.getByRole("checkbox", { name: "确认继续" }).check();
    await page.getByRole("button", { name: confirmButton }).click();

    await expect(page.getByText("这次咨询已完成", { exact: true })).toBeVisible();
    await expect(page.getByText("外部提交状态：")).toHaveCount(0);
  });

  test("复诊材料：第三条回归线保留来源和安全结果", async ({ page }) => {
    await submitPrompt(page, "我妈上次开的中药快喝完了，帮我整理复诊材料。");

    await expect(page.getByText("整理结果", { exact: true })).toBeVisible();
    await expect(page.getByText("参考信息", { exact: true })).toBeVisible();
    await expect(page.getByText("安全提示", { exact: true })).toBeVisible();
    await expect(page.getByText("task_id", { exact: true })).toHaveCount(0);
  });

  test("高风险请求：SafetyAgent 拦截且不显示业务确认按钮", async ({ page }) => {
    await submitPrompt(page, "我爸这个降压药能不能加量？");

    await expect(page.getByText("这件事需要专业人员确认", { exact: true })).toBeVisible();
    await expect(page.getByText("安全提示", { exact: true })).toBeVisible();
    await expect(page.getByText("dosage_change_request", { exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: confirmButton })).toHaveCount(0);
  });
});

async function submitPrompt(page: import("@playwright/test").Page, prompt: string) {
  await page.getByRole("textbox", { name: "输入你的问题" }).fill(prompt);
  await page.getByRole("button", { name: "开始咨询" }).click();
}
