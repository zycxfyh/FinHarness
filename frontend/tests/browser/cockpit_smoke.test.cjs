"use strict";

/**
 * D8 Browser Golden Paths — real-browser smoke (Playwright + headless Chromium).
 *
 * NOT part of `task check`. CI-only execution target (see
 * docs/proposals/2026-06-23-d8-browser-golden-paths.md). Plain `node` + the `playwright`
 * library, matching the existing `node frontend/tests/*.test.cjs` convention — no second
 * Node test runner (`@playwright/test`).
 *
 * It spawns an ephemeral seeded cockpit server, loads `/cockpit/`, and asserts 2-3 golden
 * paths render non-blank with no uncaught page error. A fault check
 * (COCKPIT_SMOKE_FAULT=1, no server) proves it fails loudly instead of false-greening.
 */

const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

let chromium;
try {
  ({ chromium } = require("playwright"));
} catch (err) {
  console.error("FATAL: `playwright` is not installed. Run `pnpm install` first.");
  console.error(String(err && err.message));
  process.exit(2);
}

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const PORT = process.env.COCKPIT_SMOKE_PORT || "8773";
const BASE = `http://127.0.0.1:${PORT}`;
const FAULT = process.env.COCKPIT_SMOKE_FAULT === "1"; // skip server start to prove fail-loud
const ARTIFACTS = path.join(REPO_ROOT, "frontend", "tests", "browser", "artifacts");

function startServer() {
  if (FAULT) return null;
  const proc = spawn(
    "uv",
    ["run", "python", "scripts/run_cockpit_smoke_server.py"],
    {
      cwd: REPO_ROOT,
      env: { ...process.env, PYTHONPATH: "src", COCKPIT_SMOKE_PORT: PORT },
      stdio: ["ignore", "inherit", "inherit"],
    },
  );
  return proc;
}

async function waitForHealth(timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${BASE}/health`);
      if (res.ok) return true;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

async function shot(page, name) {
  fs.mkdirSync(ARTIFACTS, { recursive: true });
  await page.screenshot({ path: path.join(ARTIFACTS, `${name}.png`), fullPage: true });
}

async function run() {
  const server = startServer();
  const healthMs = FAULT ? 4000 : 60000;
  const healthy = await waitForHealth(healthMs);
  if (!healthy) {
    if (FAULT) {
      console.log("FAULT_OK: server absent, smoke aborts loudly (no false green).");
      process.exit(3);
    }
    throw new Error(`seeded cockpit server never became healthy at ${BASE}`);
  }

  const browser = await chromium.launch({
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
  });
  const pageErrors = [];
  try {
    const page = await browser.newPage();
    page.on("pageerror", (e) => pageErrors.push(`pageerror: ${e.message}`));
    page.on("console", (m) => {
      if (m.type() === "error") pageErrors.push(`console.error: ${m.text()}`);
    });

    // --- Golden path 1: cockpit loads, not blank -------------------------------------
    await page.goto(`${BASE}/cockpit/`, { waitUntil: "networkidle" });
    await page.waitForSelector("#api-status", { state: "visible" });
    await page
      .locator("#api-status")
      .filter({ hasNotText: "Connecting" })
      .first()
      .waitFor({ timeout: 15000 });
    const boundary = (await page.locator("#boundary-line").textContent()) || "";
    assert.match(boundary, /execution_allowed=false/, "boundary line must show execution_allowed=false");
    assert.ok(
      await page.locator("#overview-view.view.active").count(),
      "Overview view must be the active default view",
    );
    const tabCount = await page.locator("nav.tabs button.tab").count();
    assert.equal(tabCount, 6, "expected the 6 cockpit tabs");
    await shot(page, "01-cockpit-load");

    // --- Golden path 2: Proposals view opens (seeded) --------------------------------
    await page.locator('button.tab[data-view="proposals"]').click();
    await page.waitForSelector("#proposals-view.view.active");
    const listItems = page.locator("#proposal-list button");
    await listItems.first().waitFor({ timeout: 10000 });
    assert.ok(await listItems.count(), "seeded proposal queue must have at least one item");
    // The detail auto-renders the first proposal ASYNCHRONOUSLY (Promise.all of 3 fetches,
    // then render). The list being present does NOT mean the detail finished — wait for the
    // seeded review chain to land before reading #proposal-detail. (This exact race is what
    // the real browser surfaced that jsdom did not.)
    await page.waitForSelector("#proposal-detail .review-timeline-entry", { timeout: 15000 });
    const detailText = (await page.locator("#proposal-detail").textContent()) || "";
    assert.ok(detailText.trim().length > 0, "proposal detail must not be blank");
    assert.ok(
      await page.locator("#proposal-detail .review-timeline-entry").count(),
      "seeded review timeline (annotation/compare) must render in detail",
    );
    await shot(page, "02-proposals-seeded");

    // --- Golden path 3: Compare read-only view renders -------------------------------
    await page.locator('button.tab[data-view="compare"]').click();
    await page.waitForSelector("#compare-view.view.active");
    // #compare-block also renders asynchronously (fetch /review/compare-marks then render).
    await page.waitForFunction(
      () => {
        const el = document.querySelector("#compare-block");
        return !!el && el.textContent.trim().length > 0;
      },
      { timeout: 15000 },
    );
    const compareText = (await page.locator("#compare-block").textContent()) || "";
    assert.ok(compareText.trim().length > 0, "compare block must render content (seeded compare_mark)");
    await shot(page, "03-compare");

    assert.equal(
      pageErrors.length,
      0,
      `cockpit golden paths must have no uncaught page error, saw:\n${pageErrors.join("\n")}`,
    );
    console.log("D8 browser golden paths: PASS (3 paths, 0 page errors).");
  } finally {
    await browser.close();
    if (server) server.kill("SIGTERM");
  }
}

run().catch((err) => {
  console.error("D8 browser golden paths: FAIL");
  console.error(err && err.stack ? err.stack : String(err));
  process.exitCode = 1;
  // ensure the process does not hang on a stray child
  setTimeout(() => process.exit(process.exitCode || 1), 500);
});
