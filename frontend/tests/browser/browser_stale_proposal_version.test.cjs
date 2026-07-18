"use strict";

const assert = require("node:assert/strict");
const { spawn, spawnSync } = require("node:child_process");
const fs = require("node:fs");
const net = require("node:net");
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
const ROOT = fs.mkdtempSync(
  path.join(os.tmpdir(), "finharness-browser-stale-version-"),
);
const MUTATION_STORAGE_KEY = "finharness.cockpit.mutation-attempts.v1";
const MARKER = "browser stale-version acceptance issue-390";
const NOTE = "This review event must bind only the version visible after reload.";

function freePort() {
  return new Promise((resolve, reject) => {
    const listener = net.createServer();
    listener.unref();
    listener.once("error", reject);
    listener.listen(0, "127.0.0.1", () => {
      const port = listener.address().port;
      listener.close((error) =>
        error ? reject(error) : resolve(String(port)),
      );
    });
  });
}

function pythonCommand(script, args = []) {
  return process.env.FINHARNESS_PYTHON
    ? { command: process.env.FINHARNESS_PYTHON, args: [script, ...args] }
    : { command: "uv", args: ["run", "python", script, ...args] };
}

function startServer(port) {
  const invocation = pythonCommand(
    "scripts/run_browser_stale_proposal_version_smoke_server.py",
  );
  return spawn(invocation.command, invocation.args, {
    cwd: REPO_ROOT,
    env: {
      ...process.env,
      BROWSER_STALE_PROPOSAL_VERSION_ROOT: ROOT,
      BROWSER_STALE_PROPOSAL_VERSION_PORT: port,
    },
    stdio: ["ignore", "inherit", "inherit"],
  });
}

async function waitForHealth(base, timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      if ((await fetch(`${base}/health`)).ok) return;
    } catch {
      // The ephemeral server has not bound yet.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`stale-version server never became healthy at ${base}`);
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

function readMetadata() {
  return JSON.parse(
    fs.readFileSync(path.join(ROOT, "fixture.json"), "utf-8"),
  );
}

function probe(metadata) {
  const invocation = pythonCommand(
    "frontend/tests/browser/support/probe_stale_proposal_version.py",
    [
      "--state-core-db",
      metadata.state_db,
      "--receipt-root",
      metadata.receipt_root,
      "--proposal-id",
      metadata.proposal_id,
      "--marker",
      MARKER,
    ],
  );
  const result = spawnSync(invocation.command, invocation.args, {
    cwd: REPO_ROOT,
    encoding: "utf-8",
  });
  if (result.status !== 0) {
    throw new Error(result.stderr || result.stdout || "stale probe failed");
  }
  return JSON.parse(result.stdout);
}

async function openProposal(page, base, proposalId) {
  await page.goto(`${base}/cockpit/`, { waitUntil: "networkidle" });
  await page.locator('button.tab[data-view="proposals"]').click();
  const proposal = page.locator(
    `#proposal-list button[data-proposal-id="${proposalId}"]`,
  );
  await proposal.waitFor({ state: "visible" });
  await proposal.click();
  await page.locator("form.review-event-form").waitFor({ state: "visible" });
}

async function submitScaffoldRevision(page) {
  const form = page.locator("form.scaffold-revision-form");
  await form
    .locator('textarea[name="counter_evidence"]')
    .fill("Tab A advances the immutable ProposalVersion.");
  await form
    .locator('textarea[name="reason"]')
    .fill("Advance the proposal while Tab B retains its original basis.");
  page.once("dialog", (dialog) => dialog.accept());
  await form.locator('button[type="submit"]').click();
}

async function submitReviewEvent(page) {
  const form = page.locator("form.review-event-form");
  await form.locator('select[name="kind"]').selectOption("annotation");
  await form.locator('textarea[name="reason"]').fill(MARKER);
  await form.locator('textarea[name="text"]').fill(NOTE);
  assert.equal(
    await form.locator('textarea[name="reason"]').inputValue(),
    MARKER,
  );
  page.once("dialog", (dialog) => dialog.accept());
  await form.locator('button[type="submit"]').click();
}

async function waitForAttemptCleanup(page, endpoint, timeoutMs = 10000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const retained = await page.evaluate(
      ({ key, target }) => {
        const raw = localStorage.getItem(key);
        if (raw === null) return false;
        const payload = JSON.parse(raw);
        return payload.attempts.some((attempt) => attempt.endpoint === target);
      },
      { key: MUTATION_STORAGE_KEY, target: endpoint },
    );
    if (!retained) return;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error("terminal stale-version rejection did not clear its retry attempt");
}

async function run() {
  const port = process.env.BROWSER_STALE_PROPOSAL_VERSION_PORT || (await freePort());
  const base = `http://127.0.0.1:${port}`;
  const server = startServer(port);
  await waitForHealth(base);

  let browser;
  try {
    const metadata = readMetadata();
    assert.equal(
      metadata.capability_id,
      "finharness.api.proposals.review-event.keyed.v1",
    );
    assert.equal(metadata.execution_allowed, false);

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
      launchOptions.executablePath =
        process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
    }
    browser = await chromium.launch(launchOptions);
    const context = await browser.newContext({
      extraHTTPHeaders: { Authorization: "Bearer alice-session" },
      serviceWorkers: "block",
    });
    const tabA = await context.newPage();
    const tabB = await context.newPage();
    await openProposal(tabA, base, metadata.proposal_id);
    await openProposal(tabB, base, metadata.proposal_id);

    const reviewRequests = [];
    context.on("request", (request) => {
      if (
        request.method() === "POST" &&
        request.url() === `${base}${metadata.review_event_path}`
      ) {
        reviewRequests.push(JSON.parse(request.postData()));
      }
    });

    const advanceResponsePromise = tabA.waitForResponse(
      (response) =>
        response.request().method() === "PATCH" &&
        response.url() === `${base}${metadata.scaffold_path}`,
    );
    await submitScaffoldRevision(tabA);
    const advanceResponse = await advanceResponsePromise;
    const advanceBody = await advanceResponse.json();
    assert.equal(advanceResponse.status(), 200);
    assert.equal(advanceBody.execution_allowed, false);
    assert.deepEqual(
      advanceBody.admitted_proposal_version,
      {
        proposal_id: metadata.proposal_id,
        ...metadata.initial_version,
      },
    );
    const versionTwo = advanceBody.resulting_proposal_version;
    assert.notEqual(
      versionTwo.proposal_version_id,
      metadata.initial_version.proposal_version_id,
    );

    const staleResponsePromise = tabB.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response.url() === `${base}${metadata.review_event_path}`,
    );
    await submitReviewEvent(tabB);
    const staleResponse = await staleResponsePromise;
    const staleBody = await staleResponse.json();
    assert.equal(staleResponse.status(), 409);
    assert.equal(staleBody.detail.code, "proposal_version_conflict");
    assert.deepEqual(staleBody.detail.expected, metadata.initial_version);
    assert.deepEqual(staleBody.detail.current, {
      proposal_version_id: versionTwo.proposal_version_id,
      receipt_ref: versionTwo.receipt_ref,
    });
    assert.equal(staleBody.detail.execution_allowed, false);
    assert.ok(staleResponse.headers()["x-finharness-trace-id"]);
    assert.equal(reviewRequests.length, 1);
    assert.equal(
      reviewRequests[0].expected_proposal_version_id,
      metadata.initial_version.proposal_version_id,
    );
    assert.equal(
      reviewRequests[0].expected_proposal_receipt_ref,
      metadata.initial_version.receipt_ref,
    );
    const visibleError = tabB.locator("#proposal-detail .error-text").first();
    await visibleError.waitFor({ state: "visible" });
    assert.match(await visibleError.textContent(), /proposal_version_conflict/);
    assert.match(await visibleError.textContent(), /trace:/);
    assert.doesNotMatch(await visibleError.textContent(), /Saved/);
    await new Promise((resolve) => setTimeout(resolve, 300));
    assert.equal(reviewRequests.length, 1, "a stale write must not auto-retry");
    await waitForAttemptCleanup(tabB, metadata.review_event_path);

    const rejected = probe(metadata);
    assert.deepEqual(rejected.current_version, {
      proposal_version_id: versionTwo.proposal_version_id,
      receipt_ref: versionTwo.receipt_ref,
    });
    assert.equal(rejected.matching_review_event_count, 0);
    assert.equal(rejected.matching_review_receipt_count, 0);
    assert.equal(rejected.matching_review_index_count, 0);

    await tabB.reload({ waitUntil: "networkidle" });
    await tabB.locator('button.tab[data-view="proposals"]').click();
    await tabB
      .locator(
        `#proposal-list button[data-proposal-id="${metadata.proposal_id}"]`,
      )
      .click();
    await tabB.locator("form.review-event-form").waitFor({ state: "visible" });
    await tabB.waitForTimeout(500);

    const acceptedResponsePromise = tabB.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response.url() === `${base}${metadata.review_event_path}`,
    );
    await submitReviewEvent(tabB);
    const acceptedResponse = await acceptedResponsePromise;
    const acceptedBody = await acceptedResponse.json();
    assert.equal(
      acceptedResponse.status(),
      200,
      JSON.stringify(acceptedBody),
    );
    assert.equal(acceptedBody.execution_allowed, false);
    assert.deepEqual(acceptedBody.admitted_proposal_version, versionTwo);
    assert.equal(reviewRequests.length, 2);
    assert.equal(
      reviewRequests[1].expected_proposal_version_id,
      versionTwo.proposal_version_id,
    );
    assert.equal(
      reviewRequests[1].expected_proposal_receipt_ref,
      versionTwo.receipt_ref,
    );
    await tabB
      .locator("#api-status")
      .filter({ hasText: "Saved" })
      .waitFor({ state: "visible" });

    const accepted = probe(metadata);
    assert.equal(accepted.matching_review_event_count, 1);
    assert.equal(accepted.matching_review_receipt_count, 1);
    assert.equal(accepted.matching_review_index_count, 1);
    assert.deepEqual(accepted.bound_versions, [
      {
        proposal_version_id: versionTwo.proposal_version_id,
        receipt_ref: versionTwo.receipt_ref,
      },
    ]);
    assert.deepEqual(accepted.execution_allowed, [false]);
    assert.match(
      await tabB.locator("#boundary-line").textContent(),
      /execution_allowed=false/,
    );

    await context.close();
    console.log(
      "Browser stale ProposalVersion: PASS " +
        "(v1 stale conflict has zero effects; reload v2 admits exactly one).",
    );
  } finally {
    if (browser) await browser.close();
    await stopServer(server).catch(() => {});
    fs.rmSync(ROOT, { recursive: true, force: true });
  }
}

run().catch((error) => {
  console.error("Browser stale ProposalVersion: FAIL");
  console.error(error && error.stack ? error.stack : String(error));
  process.exitCode = 1;
});
