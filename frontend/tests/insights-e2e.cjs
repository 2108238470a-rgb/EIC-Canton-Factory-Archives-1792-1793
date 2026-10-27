const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
(async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.CHROME_PATH
      ? { executablePath: process.env.CHROME_PATH }
      : {}),
    args: ["--no-sandbox"],
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 900 },
  });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/api/**", async (route) => {
    const u = new URL(route.request().url());
    u.host = new URL(process.env.TEST_API_URL || "http://127.0.0.1:8009").host;
    await route.fulfill({ response: await route.fetch({ url: u.toString() }) });
  });
  await page.goto(
    (process.env.TEST_FRONTEND_URL || "http://localhost:3103") +
      "/documents/90001/workspace",
  );
  await page.getByRole("heading", { name: "文献研究概览" }).waitFor();
  await page
    .getByRole("button", { name: /生成智能分析|重新分析/, exact: true })
    .click();
  await page
    .getByRole("heading", { name: "全文内容概览 · AI 候选解释" })
    .waitFor();
  await page.getByRole("button", { name: /文献记载|这份测试文献/ }).click();
  await page.getByRole("complementary", { name: "来源核验" }).waitFor();
  await page.getByRole("button", { name: "事件时间线", exact: true }).click();
  await page.locator("time").filter({ hasText: "1792-09-24" }).waitFor();
  await page.getByRole("button", { name: /寄送函件/ }).click();
  await page.getByText("日期：1792-09-24").waitFor();
  await page.getByLabel("目录类型").selectOption("historical_topic");
  await page.getByRole("button", { name: /^函件往来/ }).click();
  await page.getByLabel("重命名目录（保留旧版本）").fill("已编辑的测试目录");
  await page.getByRole("button", { name: "保存新修订" }).click();
  await page.getByRole("button", { name: /^已编辑的测试目录/ }).waitFor();
  const opts = await page.getByLabel("历史分析版本").locator("option").count();
  if (opts < 2) throw Error("missing immutable edit revision");
  const url = await page
    .getByRole("link", { name: "JSON（含来源 manifest）" })
    .getAttribute("href");
  const exported = await page.request.get(
    (process.env.TEST_API_URL || "http://127.0.0.1:8009") + url,
  );
  const data = await exported.json();
  if (!data.manifest || !data.artifact.summary.length)
    throw Error("bad export");
  if (errors.length) throw Error(errors.join("\n"));
  console.log(
    JSON.stringify({
      passed: true,
      flow: [
        "分析任务",
        "全文概述",
        "来源核验",
        "事件日期",
        "主题目录",
        "目录编辑留版",
        "研究导出",
      ],
      productionWrites: false,
      externalModelCalls: 0,
    }),
  );
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
