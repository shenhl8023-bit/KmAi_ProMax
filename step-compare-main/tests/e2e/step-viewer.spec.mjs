import { expect, test } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { readFileSync } from "node:fs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const fixture = path.join(root, "S-DEMO-02.stp");

test("uploads, compares, clears, and reloads the same STEP file", async ({ page }) => {
  const consoleErrors = [];
  const externalRequests = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.hostname !== "127.0.0.1" && url.hostname !== "localhost") externalRequests.push(request.url());
  });

  await page.goto("/");
  await page.locator('input[data-slot="a"]').setInputFiles(fixture);
  await expect(page.locator('[data-name="a"]')).toHaveText("S-DEMO-02");
  await expect(page.locator('[data-meta="a"]')).toContainText("50.0 × 50.0 × 25.0 mm");

  await page.locator('input[data-slot="b"]').setInputFiles(fixture);
  await expect(page.locator('[data-name="b"]')).toHaveText("S-DEMO-02");

  const overlay = page.locator('[data-mode="overlay"]');
  await overlay.click();
  await expect(overlay).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator('[data-mode="split"]')).toHaveAttribute("aria-pressed", "false");

  await page.locator('[data-clear="b"]').click();
  await expect(page.locator('[data-name="b"]')).toHaveText("点击或拖入 STEP（可选）");
  await page.locator('input[data-slot="b"]').setInputFiles(fixture);
  await expect(page.locator('[data-name="b"]')).toHaveText("S-DEMO-02");

  await page.setViewportSize({ width: 375, height: 800 });
  const columns = await page.locator(".slots").evaluate((element) =>
    getComputedStyle(element).gridTemplateColumns.split(" ").filter(Boolean).length,
  );
  expect(columns).toBe(1);
  expect(consoleErrors).toEqual([]);
  expect(externalRequests).toEqual([]);
});

test("a newer upload wins when the previous request is still pending", async ({ page }) => {
  let first = true;
  await page.route("**/api/tessellate/v2", async (route) => {
    if (first) {
      first = false;
      await new Promise((resolve) => setTimeout(resolve, 300));
    }
    try {
      await route.continue();
    } catch {
      // The expected AbortController cancellation can close the first route.
    }
  });
  await page.goto("/");
  const buffer = readFileSync(fixture);
  const input = page.locator('input[data-slot="a"]');
  await input.setInputFiles({ name: "old.stp", mimeType: "application/octet-stream", buffer });
  await input.setInputFiles({ name: "new.stp", mimeType: "application/octet-stream", buffer });
  await expect(page.locator('[data-name="a"]')).toHaveText("new", { timeout: 30_000 });
});

test("shows a readable state when GLTF parsing fails", async ({ page }) => {
  await page.route("**/api/tessellate/v2", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      model_id: "broken",
      name: "broken",
      source_unit: "mm",
      unit: "mm",
      bounds: [[0, 0, 0], [1, 1, 1]],
      extents: [1, 1, 1],
      vertices: 3,
      faces: 1,
      glb_url: "/api/models/broken.glb",
      cache_hit: false,
    }),
  }));
  await page.route("**/api/models/broken.glb", (route) => route.fulfill({
    status: 200,
    contentType: "model/gltf-binary",
    body: "not a glb",
  }));
  await page.goto("/");
  await page.locator('input[data-slot="a"]').setInputFiles(fixture);
  await expect(page.locator("#status")).not.toHaveText("已打开");
  await expect(page.locator("#status")).not.toBeEmpty();
  await expect(page.locator('[data-name="a"]')).toHaveText("点击或拖入 STEP");
});
