"use strict";

const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

let chromium;
try {
  ({ chromium } = require("playwright"));
} catch (err) {
  console.error("FATAL: `playwright` is not installed. Run `pnpm install` first.");
  process.exit(2);
}

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const PORT = process.env.LOCAL_REVIEW_SMOKE_PORT || "8774";
const BASE = `http://127.0.0.1:${PORT}`;
const ROOT = fs.mkdtempSync(path.join(os.tmpdir(), "finharness-local-review-"));

function startServer(mode) {
  const python = process.env.FINHARNESS_PYTHON;
  return spawn(python || "uv", python
    ? ["scripts/run_local_review_smoke_server.py"]
    : ["run", "python", "scripts/run_local_review_smoke_server.py"], {
    cwd: REPO_ROOT,
    env: {
      ...process.env,
      LOCAL_REVIEW_SMOKE_ROOT: ROOT,
      LOCAL_REVIEW_SMOKE_PORT: PORT,
      LOCAL_REVIEW_SMOKE_MODE: mode,
    },
    stdio: ["ignore", "inherit", "inherit"],
  });
}

async function waitForHealth(timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      if ((await fetch(`${BASE}/health`)).ok) return;
    } catch {
      // Server has not bound yet.
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error(`local review server never became healthy at ${BASE}`);
}

async function stopServer(server) {
  if (!server || server.exitCode !== null) return;
  server.kill("SIGTERM");
  await Promise.race([
    new Promise((resolve) => server.once("exit", resolve)),
    new Promise((_, reject) => setTimeout(() => reject(new Error("server did not stop")), 10000)),
  ]);
}

async function openProposal(page, proposalId) {
  await page.locator(`#proposal-list button[data-proposal-id="${proposalId}"]`).click();
  await page.waitForFunction(
    (id) => document.querySelector("#proposal-detail")?.textContent.includes(id),
    proposalId,
  );
}

async function recordDecision(page, proposalId, decision) {
  await openProposal(page, proposalId);
  const form = page.locator("#proposal-detail form.attestation-form");
  await form.locator('[name="decision"]').selectOption(decision);
  await form.locator('[name="attester"]').fill("Browser Human");
  await form.locator('[name="reason"]').fill(`Browser ${decision} review`);
  await form.locator('button[type="submit"]').click();
  await page.waitForFunction(
    ([id, expected]) => {
      const selected = document.querySelector(`#proposal-list button[data-proposal-id="${id}"]`);
      return selected && document.querySelector("#proposal-detail")?.textContent.includes(expected);
    },
    [proposalId, decision === "approved" ? "confirmed by Browser Human" : `${decision} by Browser Human`],
  );
}

async function run() {
  let server = startServer("review");
  await waitForHealth();
  const launchOptions = {
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
  };
  if (process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH) {
    launchOptions.executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
  }
  let browser;
  try {
    browser = await chromium.launch(launchOptions);
    const page = await browser.newPage();
    await page.goto(`${BASE}/cockpit/`, { waitUntil: "networkidle" });
    await page.locator('button.tab[data-view="proposals"]').click();
    await page.waitForSelector('#proposal-list button[data-proposal-id="browser-confirm"]');

    await recordDecision(page, "browser-confirm", "approved");
    await recordDecision(page, "browser-reject", "rejected");
    await recordDecision(page, "browser-defer", "deferred");

    await stopServer(server);
    server = startServer("review");
    await waitForHealth();
    await page.reload({ waitUntil: "networkidle" });
    await page.locator('button.tab[data-view="proposals"]').click();
    for (const [proposalId, label] of [
      ["browser-confirm", "confirmed by Browser Human"],
      ["browser-reject", "rejected by Browser Human"],
      ["browser-defer", "deferred by Browser Human"],
    ]) {
      await openProposal(page, proposalId);
      const detail = await page.locator("#proposal-detail").textContent();
      assert.match(detail, new RegExp(label), `${proposalId} must survive restart`);
      assert.match(detail, /Bound version:/, `${proposalId} must expose version binding`);
    }

    await openProposal(page, "browser-confirm");
    const oldVersion = await page.evaluate(async () =>
      (await (await fetch("/proposals/browser-confirm/revisions")).json()).revisions[0],
    );
    page.once("dialog", (dialog) => dialog.accept());
    const revision = page.locator("#proposal-detail form.scaffold-revision-form");
    await revision.locator('[name="counter_evidence"]').fill("Browser falsifier");
    await revision.locator('[name="attester"]').fill("Browser Human");
    await revision.locator('[name="reason"]').fill("Revise after decision");
    await revision.locator('button[type="submit"]').click();
    await page.waitForFunction(() =>
      document.querySelector("#proposal-detail")?.textContent.includes("confirmed by Browser Human (stale)"),
    );
    const staleStatus = await page.evaluate(async (expected) => {
      const response = await fetch("/proposals/browser-confirm/attest", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          decision: "rejected",
          attester: "Stale Browser Tab",
          reason: "Must be rejected",
          expected_proposal_version_id: expected.receipt_id,
          expected_proposal_receipt_ref: expected.receipt_ref,
        }),
      });
      return response.status;
    }, oldVersion);
    assert.equal(staleStatus, 409, "stale browser write must fail with conflict");

    await stopServer(server);
    server = startServer("read-only");
    await waitForHealth();
    await page.reload({ waitUntil: "networkidle" });
    await page.locator('button.tab[data-view="proposals"]').click();
    await openProposal(page, "browser-defer");
    const deniedForm = page.locator("#proposal-detail form.attestation-form");
    await deniedForm.locator('[name="decision"]').selectOption("approved");
    await deniedForm.locator('[name="attester"]').fill("Browser Human");
    await deniedForm.locator('[name="reason"]').fill("Read-only must deny this");
    await deniedForm.locator('button[type="submit"]').click();
    await page.waitForSelector("#proposal-detail .error-text");
    assert.match(
      (await page.locator("#proposal-detail .error-text").first().textContent()) || "",
      /403.*write_capability_required/,
      "permission denial must be visible in the browser",
    );

    console.log("Local review browser mode: PASS (3 decisions, restart, stale, permission denial).");
  } finally {
    if (browser) await browser.close();
    await stopServer(server).catch(() => {});
    fs.rmSync(ROOT, { recursive: true, force: true });
  }
}

run().catch((err) => {
  console.error("Local review browser mode: FAIL");
  console.error(err && err.stack ? err.stack : String(err));
  process.exitCode = 1;
});
