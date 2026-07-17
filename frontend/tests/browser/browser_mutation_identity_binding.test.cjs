"use strict";

const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

let chromium;
try {
  ({ chromium } = require("playwright"));
} catch {
  console.error("FATAL: `playwright` is not installed. Run `pnpm install` first.");
  process.exit(2);
}

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const PORT = process.env.BROWSER_IDENTITY_BINDING_PORT || "8788";
const BASE = `http://127.0.0.1:${PORT}`;
const ROOT = fs.mkdtempSync(path.join(os.tmpdir(), "finharness-browser-binding-"));
const STORAGE_KEY = "finharness.cockpit.mutation-attempts.v1";
const PAYLOAD = {
  kind: "allocation",
  claim: "Browser identity binding fixture",
  decision_scaffold: {
    decision_intent: "Prove same-session retry",
    thesis: "The browser binding is current",
    do_nothing_case: "No proposal is admitted",
    risk_if_wrong: "A retained attempt crosses identity",
  },
  source_refs: ["test:#388:chromium"],
};

function startServer() {
  const python = process.env.FINHARNESS_PYTHON;
  return spawn(
    python || "uv",
    python
      ? ["scripts/run_browser_identity_binding_smoke_server.py"]
      : ["run", "python", "scripts/run_browser_identity_binding_smoke_server.py"],
    {
      cwd: REPO_ROOT,
      env: {
        ...process.env,
        BROWSER_IDENTITY_BINDING_ROOT: ROOT,
        BROWSER_IDENTITY_BINDING_PORT: PORT,
      },
      stdio: ["ignore", "inherit", "inherit"],
    },
  );
}

async function waitForHealth(timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      if ((await fetch(`${BASE}/health`)).ok) return;
    } catch {
      // Server has not bound yet.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`browser identity server never became healthy at ${BASE}`);
}

async function stopServer(server) {
  if (!server || server.exitCode !== null) return;
  server.kill("SIGTERM");
  await Promise.race([
    new Promise((resolve) => server.once("exit", resolve)),
    new Promise((_, reject) =>
      setTimeout(() => reject(new Error("server did not stop")), 10000),
    ),
  ]);
}

async function pageFor(browserContext, token, diagnostics) {
  const page = await browserContext.newPage();
  await page.setExtraHTTPHeaders({ Authorization: `Bearer ${token}` });
  page.on("pageerror", (error) => diagnostics.pageErrors.push(String(error)));
  page.on("console", (message) => {
    if (message.type() === "error") diagnostics.consoleErrors.push(message.text());
  });
  await page.goto(`${BASE}/cockpit/`, { waitUntil: "networkidle" });
  return page;
}

async function invoke(page, payload = PAYLOAD, acknowledge = false) {
  return page.evaluate(
    async ({ body, shouldAcknowledge }) => {
      try {
        const result = await window.FinHarness.api.apiMutation(
          "POST",
          "/proposals",
          body,
        );
        if (shouldAcknowledge) await result.acknowledge();
        return {
          ok: true,
          key: result.idempotencyKey,
          executionAllowed: result.body.execution_allowed,
        };
      } catch (error) {
        return {
          ok: false,
          name: error.name,
          reason: error.reason || null,
          attemptRetained: error.attemptRetained === true,
          message: error.message,
        };
      }
    },
    { body: payload, shouldAcknowledge: acknowledge },
  );
}

async function run() {
  const server = startServer();
  await waitForHealth();
  const launchOptions = {
    headless: true,
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
      "--disable-gpu",
    ],
  };
  if (process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH) {
    launchOptions.executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
  }
  let browser;
  try {
    browser = await chromium.launch(launchOptions);
    const browserContext = await browser.newContext();
    const diagnostics = { pageErrors: [], consoleErrors: [] };
    const alice = await pageFor(browserContext, "alice-session-1", diagnostics);

    let alicePosts = 0;
    await alice.route("**/proposals", async (route) => {
      if (route.request().method() === "POST") {
        alicePosts += 1;
        await route.abort("failed");
        return;
      }
      await route.continue();
    });
    const retained = await invoke(alice);
    assert.equal(retained.name, "MutationTransportError");
    assert.equal(retained.attemptRetained, true);
    assert.equal(alicePosts, 1);
    const retainedRegistry = await alice.evaluate(
      (key) => JSON.parse(localStorage.getItem(key)),
      STORAGE_KEY,
    );
    const retainedKey = retainedRegistry.attempts[0].idempotency_key;

    const bob = await pageFor(browserContext, "bob-session-1", diagnostics);
    let bobPosts = 0;
    bob.on("request", (request) => {
      if (request.method() === "POST" && request.url() === `${BASE}/proposals`) {
        bobPosts += 1;
      }
    });
    const bobResult = await invoke(bob);
    assert.equal(bobResult.reason, "principal_mismatch");
    assert.equal(bobPosts, 0);
    assert.doesNotMatch(bobResult.message, new RegExp(retainedKey));

    const alice2 = await pageFor(browserContext, "alice-session-2", diagnostics);
    let rotatedPosts = 0;
    alice2.on("request", (request) => {
      if (request.method() === "POST" && request.url() === `${BASE}/proposals`) {
        rotatedPosts += 1;
      }
    });
    const rotated = await invoke(alice2);
    assert.equal(rotated.reason, "session_epoch_mismatch");
    assert.equal(rotatedPosts, 0);

    await alice.unroute("**/proposals");
    await alice.reload({ waitUntil: "networkidle" });
    let replayKey = null;
    alice.on("request", (request) => {
      if (request.method() === "POST" && request.url() === `${BASE}/proposals`) {
        replayKey = request.headers()["idempotency-key"];
      }
    });
    const replay = await invoke(alice, PAYLOAD, true);
    assert.equal(replay.ok, true);
    assert.equal(replay.executionAllowed, false);
    assert.equal(replay.key, retainedKey);
    assert.equal(replayKey, retainedKey);
    assert.equal(
      await alice.evaluate((key) => localStorage.getItem(key), STORAGE_KEY),
      null,
    );

    const expired = await pageFor(
      browserContext,
      "expired-alice-session",
      diagnostics,
    );
    let expiredPosts = 0;
    expired.on("request", (request) => {
      if (request.method() === "POST" && request.url() === `${BASE}/proposals`) {
        expiredPosts += 1;
      }
    });
    const expiredResult = await invoke(expired, {
      ...PAYLOAD,
      claim: "Expired browser identity fixture",
    });
    assert.equal(expiredResult.reason, "current_binding_expired");
    assert.equal(expiredPosts, 0);

    const legacyRaw = JSON.stringify({
      schema: "finharness.cockpit_mutation_attempts.v1",
      attempts: [],
    });
    await alice.evaluate(
      ({ key, raw }) => localStorage.setItem(key, raw),
      { key: STORAGE_KEY, raw: legacyRaw },
    );
    const legacy = await invoke(alice, {
      ...PAYLOAD,
      claim: "Legacy registry fixture",
    });
    assert.equal(legacy.reason, "legacy_unbound");
    assert.equal(
      await alice.evaluate((key) => localStorage.getItem(key), STORAGE_KEY),
      legacyRaw,
    );

    assert.deepEqual(diagnostics.pageErrors, []);
    assert.ok(
      diagnostics.consoleErrors.some((message) =>
        message.includes("net::ERR_FAILED"),
      ),
      "the intentional pre-server transport abort must be visible",
    );
    assert.ok(
      diagnostics.consoleErrors.some((message) =>
        message.includes("403 (Forbidden)"),
      ),
      "the expired binding denial must be visible",
    );
    assert.equal(
      diagnostics.consoleErrors.filter(
        (message) =>
          !message.includes("net::ERR_FAILED") &&
          !message.includes("403 (Forbidden)"),
      ).length,
      0,
      "no unexpected console errors are allowed",
    );
    console.log(
      "Browser mutation identity binding: PASS " +
        "(principal switch, epoch rotation, reload reuse, expired, legacy).",
    );
  } finally {
    if (browser) await browser.close();
    await stopServer(server).catch(() => {});
    fs.rmSync(ROOT, { recursive: true, force: true });
  }
}

run().catch((error) => {
  console.error("Browser mutation identity binding: FAIL");
  console.error(error && error.stack ? error.stack : String(error));
  process.exitCode = 1;
});
