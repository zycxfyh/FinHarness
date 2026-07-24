"use strict";

/** Real Chromium journey for the local Agent Shell product slice. */

const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const net = require("node:net");
const os = require("node:os");
const path = require("node:path");

let chromium;
try {
  ({ chromium } = require("playwright"));
} catch (error) {
  console.error("FATAL: `playwright` is not installed. Run `pnpm install` first.");
  console.error(String(error && error.message));
  process.exit(2);
}

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const ARTIFACTS = path.join(REPO_ROOT, "frontend", "tests", "browser", "artifacts");

async function availablePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = address && typeof address === "object" ? address.port : null;
      server.close((error) => (error ? reject(error) : resolve(port)));
    });
  });
}

function startServer(root, port) {
  const python = process.env.FINHARNESS_PYTHON;
  const command = python || "uv";
  const args = python
    ? [
        "scripts/serve_agent_shell_test_fixture.py",
        "--root",
        root,
        "--port",
        String(port),
        "--runtime-mode",
        "fixture",
      ]
    : [
        "run",
        "python",
        "scripts/serve_agent_shell_test_fixture.py",
        "--root",
        root,
        "--port",
        String(port),
        "--runtime-mode",
        "fixture",
      ];
  return spawn(command, args, {
    cwd: REPO_ROOT,
    env: { ...process.env },
    stdio: ["ignore", "inherit", "inherit"],
  });
}

async function waitForReady(base, server) {
  const deadline = Date.now() + 60000;
  while (Date.now() < deadline) {
    if (server.exitCode !== null) {
      throw new Error(`Agent Shell fixture exited early: ${server.exitCode}`);
    }
    try {
      const response = await fetch(`${base}/agent/bootstrap`);
      if (response.ok) return;
    } catch {
      // Server is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Agent Shell fixture did not become ready at ${base}`);
}

async function screenshot(page, name) {
  fs.mkdirSync(ARTIFACTS, { recursive: true });
  await page.screenshot({ path: path.join(ARTIFACTS, name), fullPage: true });
}

async function run() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "finharness-agent-browser-"));
  const port = await availablePort();
  const base = `http://127.0.0.1:${port}`;
  const server = startServer(root, port);
  let browser;
  try {
    await waitForReady(base, server);
    browser = await chromium.launch({
      headless: true,
      args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
    });
    const page = await browser.newPage();
    const pageErrors = [];
    page.on("pageerror", (error) => pageErrors.push(`pageerror: ${error.message}`));
    page.on("console", (message) => {
      if (message.type() === "error") pageErrors.push(`console.error: ${message.text()}`);
    });

    await page.goto(`${base}/agent-ui/`, { waitUntil: "networkidle" });
    await page.locator("#connection-status").filter({ hasText: "Ready" }).waitFor({ timeout: 15000 });
    assert.match(
      (await page.locator("body").textContent()) || "",
      /live_execution_allowed=false/,
    );
    assert.equal(
      await page.locator('input[name*="key" i], input[placeholder*="key" i]').count(),
      0,
      "browser must not expose an API-key field",
    );

    await page.fill("#mission-objective", "Prove the real browser Agent journey");
    await page.fill("#mission-success", "One paper Effect is reconciled exactly once");
    await page.fill("#initial-belief", "The bounded paper Effect should preserve one identity chain");
    await page.click("#mission-submit");
    await page.locator("#active-mission").waitFor({ state: "visible", timeout: 15000 });
    await page.locator("#mission-message").filter({ hasText: "Mission started" }).waitFor();
    assert.match((await page.locator("#mission-summary").textContent()) || "", /Mission:/);
    assert.equal(await page.locator("#world-drift-card").isHidden(), true);
    await screenshot(page, "agent-shell-01-mission.png");

    await page.fill("#message-input", "What is known and uncertain before the paper test?");
    await page.locator("#message-form button").click();
    await page.locator("#conversation-log .turn.agent").waitFor({ timeout: 15000 });
    assert.match(
      (await page.locator("#conversation-log").textContent()) || "",
      /cannot create an Effect/i,
    );

    await page.selectOption("#effect-symbol", "SPY");
    await page.selectOption("#effect-side", "sell");
    await page.fill("#effect-quantity", "1");
    await page.fill("#effect-rationale", "Real browser bounded paper Effect");
    await page.click("#effect-submit");
    await page.locator("#effect-result .effect-card").waitFor({ timeout: 30000 });
    const effectText = (await page.locator("#effect-result").textContent()) || "";
    assert.match(effectText, /Completed/);
    assert.match(effectText, /Job job-/);
    assert.match(effectText, /verified price 1000/);
    await screenshot(page, "agent-shell-02-effect.png");

    assert.equal(
      pageErrors.length,
      0,
      `Agent Shell journey emitted browser errors:\n${pageErrors.join("\n")}`,
    );
    console.log(
      "Agent Shell browser journey: PASS (Mission, conversation, persisted fixture Runtime paper Effect).",
    );
  } finally {
    if (browser) await browser.close();
    server.kill("SIGTERM");
    await new Promise((resolve) => {
      const timer = setTimeout(resolve, 5000);
      server.once("exit", () => {
        clearTimeout(timer);
        resolve();
      });
    });
    fs.rmSync(root, { recursive: true, force: true });
  }
}

run().catch((error) => {
  console.error("Agent Shell browser journey: FAIL");
  console.error(error && error.stack ? error.stack : String(error));
  process.exitCode = 1;
});
