const { test, expect } = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;
async function ready(page, path = "/") {
  await page.goto(path);
  await expect(page.locator("#list")).toHaveAttribute("aria-busy", "false");
  await expect(
    page.locator(".card, .program-table tbody tr").first(),
  ).toBeVisible();
}
async function tab(page, name) {
  const mobile = page.locator(`.mobile-nav [data-route="${name}"]`);
  if (await mobile.isVisible()) await mobile.click();
  else await page.locator(`.tabs [data-tab="${name}"]`).click();
}
async function filters(page) {
  if (
    (await page.locator("#filter-toggle").getAttribute("aria-expanded")) !==
    "true"
  )
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
  await tab(page, "saved");
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
  await tab(page, "saved");
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
    if (page.viewportSize().width <= 760) {
      await page.keyboard.press("Shift+Tab");
      await expect(page.locator("#reset")).toBeFocused();
    }
    await page.keyboard.press("Escape");
    await expect(page.locator("#filter-toggle")).toBeFocused();
  }
  const card = page.locator(".card").first();
  await card.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("#detail")).toBeVisible();
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all(
      document
        .getAnimations()
        .filter(
          (animation) =>
            animation.effect.getComputedTiming().iterations !== Infinity,
        )
        .map((animation) => animation.finished.catch(() => {})),
    );
  });
  const detailAudit = await new AxeBuilder({ page }).analyze();
  expect(detailAudit.violations).toEqual([]);
  await page.keyboard.press("Escape");
  await expect(card.locator(".open-program")).toBeFocused();
  await page.evaluate(async () => {
    await Promise.all(
      document
        .getAnimations()
        .filter(
          (animation) =>
            animation.effect.getComputedTiming().iterations !== Infinity,
        )
        .map((animation) => animation.finished.catch(() => {})),
    );
  });
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

test("platform selection preserves focus and note editing preserves card nodes", async ({
  page,
}) => {
  await ready(page, "/?tab=all");
  await filters(page);
  const chip = page.locator('#platforms [data-platform="hackerone"]');
  await chip.focus();
  await page.keyboard.press("Enter");
  await expect(chip).toBeFocused();
  await expect(chip).toHaveAttribute("aria-pressed", "true");
  await page.evaluate(() => {
    window.originalChip = document.querySelector(
      '#platforms [data-platform="hackerone"]',
    );
  });
  await page.keyboard.press("Space");
  await expect(chip).toBeFocused();
  expect(
    await page.evaluate(
      () =>
        window.originalChip ===
        document.querySelector('#platforms [data-platform="hackerone"]'),
    ),
  ).toBe(true);
  await closeFilters(page);
  await page
    .getByRole("button", { name: "Xóa bộ lọc HackerOne", exact: true })
    .click();
  await expect(page.locator("#q")).toBeFocused();
  await page.evaluate(() => {
    window.originalCard = document.querySelector(".card");
  });
  await page.locator(".card").first().click();
  await page.locator("#d-note").fill("Stable DOM while taking notes");
  expect(
    await page.evaluate(
      () => window.originalCard === document.querySelector(".card"),
    ),
  ).toBe(true);
  await expect(page.locator(".card .bookmark").first()).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});

test("result is above fold, typography stays readable and saved navigation is reachable", async ({
  page,
}) => {
  await ready(page);
  await page.evaluate(() => document.fonts.ready);
  const geometry = await page.locator(".card").first().boundingBox();
  expect(geometry.y + 50).toBeLessThan(page.viewportSize().height);
  expect(
    await page
      .locator(".card-summary")
      .first()
      .evaluate((el) => parseFloat(getComputedStyle(el).fontSize)),
  ).toBeGreaterThanOrEqual(16);
  await tab(page, "easy");
  await expect(page.locator("#list-scope")).toContainText("Top 50");
  await expect(page.locator("#easy-caption")).toContainText("top 50");
  await tab(page, "saved");
  await expect(page.locator("#section-title")).toHaveText("Bộ sưu tập của bạn");
  if (page.viewportSize().width <= 760) {
    const nav = page.locator('.mobile-nav [data-route="saved"]');
    await expect(nav).toBeInViewport();
    await expect(nav).toHaveAttribute("aria-pressed", "true");
  }
});

test("pagination keeps at most fifty cards and filter changes reset the URL page", async ({
  page,
}) => {
  await ready(page, "/?tab=all");
  await expect(page.locator(".card")).toHaveCount(50);
  const first = await page
    .locator(".card")
    .first()
    .getAttribute("data-program-id");
  await page.locator("#page-next").click();
  await expect(page).toHaveURL(/page=2/);
  await expect(page.locator(".card")).toHaveCount(50);
  expect(
    await page.locator(".card").first().getAttribute("data-program-id"),
  ).not.toBe(first);
  await page.reload();
  await expect(page.locator("#page-summary")).toHaveText(/Trang 2\//);
  await page.locator("#q").fill("starbucks");
  await expect(page).not.toHaveURL(/page=/);
  await expect(page.locator("#page-summary")).toHaveText(/Trang 1\//);
});

test("table view preserves interactions and URL; phones keep cards", async ({
  page,
}) => {
  await ready(page, "/?tab=all&view=table");
  if (page.viewportSize().width <= 760) {
    await expect(page.locator(".card")).toHaveCount(50);
    await expect(page.locator(".program-table")).toHaveCount(0);
    return;
  }
  await expect(page.locator(".program-table tbody tr")).toHaveCount(50);
  await expect(page.locator("#view-table")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  const row = page.locator(".program-table tbody tr").first();
  await row.locator(".bookmark").click();
  await expect(row.locator(".bookmark")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.locator("#detail")).not.toBeVisible();
  await row.locator(".open-program").click();
  await expect(page.locator("#detail")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(row.locator(".open-program")).toBeFocused();
  await page.evaluate(async () => {
    await Promise.all(
      document
        .getAnimations()
        .filter((a) => a.effect.getComputedTiming().iterations !== Infinity)
        .map((a) => a.finished.catch(() => {})),
    );
  });
  const audit = await new AxeBuilder({ page }).analyze();
  expect(audit.violations).toEqual([]);
  await page.locator("#view-cards").click();
  await expect(page.locator(".card")).toHaveCount(50);
  await expect(page).not.toHaveURL(/view=table/);
});
