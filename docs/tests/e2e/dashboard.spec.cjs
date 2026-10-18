const { test, expect } = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;
async function ready(page, path = "/") {
  await page.goto(path);
  await expect(page.locator("#list")).toHaveAttribute("aria-busy", "false");
  await expect(page.locator(".card").first()).toBeVisible();
}
async function filters(page) {
  if (await page.locator("#filter-toggle").isVisible())
    await page.locator("#filter-toggle").click();
}
async function closeFilters(page) {
  if (await page.locator("#filter-close").isVisible())
    await page.locator("#filter-close").click();
}

test("loads compact snapshot; search, filters, URL and lazy detail work", async ({
  page,
}) => {
  const errors = [],
    requests = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("request", (r) => requests.push(r.url()));
  await ready(page, "/?tab=all");
  expect(requests.some((u) => u.endsWith("/index.json"))).toBe(true);
  expect(requests.some((u) => u.endsWith("/programs.min.json"))).toBe(false);
  expect(requests.some((u) => u.includes("/details/"))).toBe(false);
  await page.locator("#q").fill("starbucks");
  await expect(page).toHaveURL(/q=starbucks/);
  await expect(page.locator(".card").first()).toContainText(/Starbucks/i);
  await filters(page);
  await page.locator("#currency").selectOption("USD");
  await closeFilters(page);
  await expect(page).toHaveURL(/currency=USD/);
  await page.reload();
  await expect(page.locator("#list")).toHaveAttribute("aria-busy", "false");
  await filters(page);
  await expect(page.locator("#currency")).toHaveValue("USD");
  await page.locator("#reset").click();
  await closeFilters(page);
  await expect(page.locator(".card").first()).toBeVisible();
  await page.locator(".card").first().click();
  await expect(page.locator("#detail")).toBeVisible();
  await expect(page.locator("#d-in")).not.toContainText("Đang tải");
  expect(requests.some((u) => u.includes("/details/"))).toBe(true);
  await expect(page).toHaveURL(/program=/);
  await page.keyboard.press("Escape");
  await expect(page.locator("#detail")).not.toBeVisible();
  expect(errors).toEqual([]);
});

test("bookmark, note, reload and versioned export preserve user work", async ({
  page,
}) => {
  await ready(page);
  await page.locator(".card").first().click();
  await page
    .locator("#d-note")
    .fill("Research note <script>not executable</script>");
  await expect(page.locator("#note-status")).toHaveText(
    "Đã lưu trên thiết bị.",
  );
  await expect(page.locator("#saved-count")).toHaveText("1");
  const title = await page.locator("#d-title").textContent();
  await page.reload();
  await expect(page.locator("#detail")).toBeVisible();
  await expect(page.locator("#d-title")).toHaveText(title);
  await expect(page.locator("#d-note")).toHaveValue(
    "Research note <script>not executable</script>",
  );
  await page.keyboard.press("Escape");
  await page.locator('[data-tab="saved"]').click();
  await expect(page.locator(".card")).toHaveCount(1);
  const downloadPromise = page.waitForEvent("download");
  await page.locator("#export").click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("scopeboard-saved.json");
  const fs = require("node:fs");
  const data = JSON.parse(fs.readFileSync(await download.path(), "utf8"));
  expect(data.version).toBe(1);
  expect(Object.values(data.items)[0].note).toContain("Research note");
});

test("imports preview before merge and retain orphaned saved program", async ({
  page,
}) => {
  await ready(page);
  const upload = async (json) =>
    page.locator("#import").setInputFiles({
      name: "saved.json",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(json)),
    });
  await upload([1, 2]);
  await expect(page.locator("#toast")).toContainText("Không nhập được");
  await expect(page.locator("#saved-count")).toHaveText("0");
  await upload({
    "self-host:gone": {
      note: "keep this",
      program: {
        name: "Archived research",
        platform: "self-host",
        url: "https://example.org",
      },
    },
  });
  await expect(page.locator("#import-dialog")).toBeVisible();
  await expect(page.locator("#saved-count")).toHaveText("0");
  await page.locator("#confirm-import").click();
  await page.locator('[data-tab="saved"]').click();
  await expect(page.locator(".card")).toContainText("Archived research");
  await expect(page.locator(".card")).toContainText("Đã rời feed");
  await page.locator(".card").click();
  await expect(page.locator("#d-note")).toHaveValue("keep this");
});

test("storage quota errors are visible, notes remain exportable", async ({
  page,
}) => {
  await page.addInitScript(() => {
    Storage.prototype.setItem = () => {
      throw new DOMException("full", "QuotaExceededError");
    };
  });
  await ready(page);
  await page.locator(".card").first().click();
  await page.locator("#d-note").fill("unsaved but recoverable");
  await expect(page.locator("#note-status")).toContainText("Chưa lưu được");
  await page.keyboard.press("Escape");
  await expect(page.locator("#storage-status")).toContainText(
    "hãy xuất bản sao",
  );
  await expect(page.locator("#saved-count")).toHaveText("1");
});

test("network failure has retry and detail requests can recover", async ({
  page,
}) => {
  await page.route("**/data/manifest.json", (route) =>
    route.fulfill({ status: 503, body: "unavailable" }),
  );
  await page.goto("/");
  await expect(page.locator("#load-error")).toBeVisible();
  await page.unroute("**/data/manifest.json");
  await page.locator("#retry").click();
  await expect(page.locator(".card").first()).toBeVisible();
  await page.route("**/details/*.json", (route) =>
    route.fulfill({ status: 503, body: "unavailable" }),
  );
  await page.locator(".card").first().click();
  await expect(page.locator("#retry-detail")).toBeVisible();
  await expect(page.locator("#d-in")).toContainText("Chưa tải được");
  await page.unroute("**/details/*.json");
  await page.locator("#retry-detail").click();
  await expect(page.locator("#d-in")).not.toContainText("Chưa tải được");
});

test("keyboard navigation, mobile drawer and accessibility", async ({
  page,
}) => {
  await ready(page);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  if (await page.locator("#filter-toggle").isVisible()) {
    await page.locator("#filter-toggle").click();
    await expect(page.locator("#filter-close")).toBeFocused();
    await page.keyboard.press("Shift+Tab");
    await expect(page.locator("#reset")).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(page.locator("#filter-toggle")).toBeFocused();
  }
  const card = page.locator(".card").first();
  await card.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("#detail")).toBeVisible();
  const detailAudit = await new AxeBuilder({ page }).analyze();
  expect(detailAudit.violations).toEqual([]);
  await page.keyboard.press("Escape");
  await expect(card.locator(".open-program")).toBeFocused();
  const audit = await new AxeBuilder({ page }).analyze();
  expect(audit.violations).toEqual([]);
});

test("Back and Forward restore filters and program deep links", async ({
  page,
}) => {
  await ready(page, "/?tab=all");
  await page.locator("#q").fill("starbucks");
  await expect(page).toHaveURL(/q=starbucks/);
  await page.goBack();
  await expect(page.locator("#q")).toHaveValue("");
  await page.goForward();
  await expect(page.locator("#q")).toHaveValue("starbucks");
  await page.locator(".card").first().click();
  await expect(page).toHaveURL(/program=/);
  await page.goBack();
  await expect(page.locator("#detail")).not.toBeVisible();
  await page.goForward();
  await expect(page.locator("#detail")).toBeVisible();
});

test("rejects mixed snapshot versions and retries successfully", async ({
  page,
}) => {
  await page.route("**/snapshots/*/index.json", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    await route.fulfill({
      response,
      json: { ...data, snapshot_id: "invalid-generation" },
    });
  });
  await page.goto("/");
  await expect(page.locator("#load-error")).toContainText(
    "Snapshot chưa nhất quán",
  );
  await expect(page.locator(".card")).toHaveCount(0);
  await page.unroute("**/snapshots/*/index.json");
  await page.locator("#retry").click();
  await expect(page.locator(".card").first()).toBeVisible();
});
