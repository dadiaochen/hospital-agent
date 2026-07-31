import { expect, test } from "@playwright/test";

const runButton = "运行 Agent";
const confirmButton = "确认并创建本地草稿";

test.describe("4C-3 Agent 黄金链路", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/agent");
    await expect(page.getByLabel("当前家庭成员")).toBeVisible();
  });

  test("续方：首次 run 进入 DRAFT，未确认不会推进", async ({ page }) => {
    await page.getByRole("button", { name: "正常续方" }).click();
    await page.getByRole("button", { name: runButton }).click();

    await expect(page.getByText("DRAFT", { exact: true })).toBeVisible();
    await expect(page.getByText("等待你的明确确认")).toBeVisible();
    await expect(page.getByRole("button", { name: confirmButton })).toBeDisabled();
    await expect(page.getByText("结构化答案", { exact: true })).toBeVisible();
  });

  test("续方：确认后产生 continuation run 并完成本地草稿", async ({ page }) => {
    await page.getByRole("button", { name: "正常续方" }).click();
    await page.getByRole("button", { name: runButton }).click();

    const confirmation = page.getByRole("button", { name: confirmButton });
    await expect(confirmation).toBeVisible();
    await expect(confirmation).toBeDisabled();
    await page.getByRole("checkbox").check();
    await expect(confirmation).toBeEnabled();
    await confirmation.click();

    await expect(page.getByText("LOCAL_COMPLETED", { exact: true })).toBeVisible();
    await expect(page.getByText("continuation run", { exact: true })).toBeVisible();
    await expect(page.getByText("续跑来源", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: confirmButton })).toHaveCount(0);
  });

  test("用药提醒：确认后完成本地提醒草稿", async ({ page }) => {
    await page.getByRole("button", { name: "用药提醒" }).click();
    await page.getByRole("button", { name: runButton }).click();

    await expect(page.getByText("DRAFT", { exact: true })).toBeVisible();
    await page.getByRole("checkbox").check();
    await page.getByRole("button", { name: confirmButton }).click();

    await expect(page.getByText("LOCAL_COMPLETED", { exact: true })).toBeVisible();
    await expect(page.getByText("外部提交状态：")).toBeVisible();
    await expect(page.getByText("not_submitted", { exact: true })).toBeVisible();
  });

  test("复诊材料：第三条回归线保留来源和安全结果", async ({ page }) => {
    await page.getByRole("button", { name: "复诊材料" }).click();
    await page.getByRole("button", { name: runButton }).click();

    await expect(page.getByText("结构化答案", { exact: true })).toBeVisible();
    await expect(page.getByText("事实与规则来源", { exact: true })).toBeVisible();
    await expect(page.getByText("安全与人工确认", { exact: true })).toBeVisible();
    await expect(page.getByText("task_id", { exact: true })).toBeVisible();
  });

  test("高风险请求：SafetyAgent 拦截且不显示业务确认按钮", async ({ page }) => {
    await page.getByRole("button", { name: "高风险拦截" }).click();
    await page.getByRole("button", { name: runButton }).click();

    await expect(page.getByText("BLOCKED", { exact: true })).toBeVisible();
    await expect(page.getByText("安全拦截", { exact: true })).toBeVisible();
    await expect(page.getByText("dosage_change_request", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: confirmButton })).toHaveCount(0);
  });
});
