"use strict";

const assert = require("node:assert/strict");
const { spawn, spawnSync } = require("node:child_process");
const crypto = require("node:crypto");
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
  path.join(os.tmpdir(), "finharness-browser-response-loss-"),
);
const ARTIFACTS = path.join(
  REPO_ROOT,
  "frontend",
  "tests",
  "browser",
  "artifacts",
);
const STORAGE_KEY = "finharness.cockpit.mutation-attempts.v1";
const STORAGE_SCHEMA = "finharness.cockpit_mutation_attempts.v2";
const CAPABILITY_ID = "finharness.api.proposals.review-event.keyed.v1";
const RESOLVER_ID = "finharness.api.review_event_create.v1";
const MARKER = "browser-response-loss acceptance issue-385";
const NOTE =
  "One logical review event must survive response loss without duplication.";
const FORM_PAYLOAD = {
  kind: "annotation",
  reason: MARKER,
  text: NOTE,
};

function keyDigest(value) {
  return crypto.createHash("sha256").update(String(value)).digest("hex");
}

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = address.port;
      server.close((error) => (error ? reject(error) : resolve(String(port))));
    });
  });
}

function pythonCommand(script, args = []) {
  const python = process.env.FINHARNESS_PYTHON;
  return python
    ? { command: python, args: [script, ...args] }
    : { command: "uv", args: ["run", "python", script, ...args] };
}

function startServer(port) {
  const invocation = pythonCommand(
    "scripts/run_browser_mutation_response_loss_smoke_server.py",
  );
  return spawn(invocation.command, invocation.args, {
    cwd: REPO_ROOT,
    env: {
      ...process.env,
      BROWSER_MUTATION_RESPONSE_LOSS_ROOT: ROOT,
      BROWSER_MUTATION_RESPONSE_LOSS_PORT: port,
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
      // Server has not bound yet.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`response-loss server never became healthy at ${base}`);
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

function runJsonScript(script, args) {
  const invocation = pythonCommand(script, args);
  const result = spawnSync(invocation.command, invocation.args, {
    cwd: REPO_ROOT,
    encoding: "utf-8",
  });
  if (result.status !== 0) {
    throw new Error(
      `${script} failed: ${result.stderr || result.stdout || result.status}`,
    );
  }
  return JSON.parse(result.stdout);
}

function probe(metadata, identityReceiptId = null) {
  const args = [
    "--state-core-db",
    metadata.state_db,
    "--receipt-root",
    metadata.receipt_root,
    "--proposal-id",
    metadata.proposal_id,
    "--marker",
    MARKER,
  ];
  if (identityReceiptId) {
    args.push("--identity-receipt-id", identityReceiptId);
  }
  return runJsonScript(
    "frontend/tests/browser/support/probe_mutation_response_loss.py",
    args,
  );
}

function reconcile(receiptPath, metadata, apply = false) {
  const args = [
    receiptPath,
    "--state-core-db",
    metadata.state_db,
    "--receipt-root",
    metadata.receipt_root,
  ];
  if (apply) {
    args.push(
      "--apply",
      "--reconciled-by",
      "operator:browser-response-loss-acceptance",
      "--reason",
      "Verified one bound ReviewEvent and its canonical domain receipt after the terminal response was lost.",
    );
  }
  return runJsonScript("scripts/reconcile_identity_mutation.py", args);
}

async function mutationRegistry(page) {
  return page.evaluate((key) => {
    const raw = localStorage.getItem(key);
    return raw === null ? null : JSON.parse(raw);
  }, STORAGE_KEY);
}

async function openProposal(page, base, metadata) {
  await page.goto(`${base}/cockpit/`, { waitUntil: "networkidle" });
  await page.locator('button.tab[data-view="proposals"]').click();
  const proposal = page.locator(
    `#proposal-list button[data-proposal-id="${metadata.proposal_id}"]`,
  );
  await proposal.waitFor({ state: "visible" });
  await proposal.click();
  await page.locator("form.review-event-form").waitFor({ state: "visible" });
}

async function submitReviewEvent(page) {
  const form = page.locator("form.review-event-form");
  await form.locator('select[name="kind"]').selectOption(FORM_PAYLOAD.kind);
  await form.locator('textarea[name="reason"]').fill(FORM_PAYLOAD.reason);
  await form.locator('textarea[name="text"]').fill(FORM_PAYLOAD.text);
  assert.equal(
    await form.locator('textarea[name="reason"]').inputValue(),
    FORM_PAYLOAD.reason,
  );
  page.once("dialog", (dialog) => dialog.accept());
  await form.locator('button[type="submit"]').click();
}

async function retainUnrelatedScaffoldAttempt(page, base, metadata) {
  const endpoint = `${base}/proposals/${metadata.proposal_id}/decision-scaffold`;
  let intercepted = false;
  const abortBeforeServer = async (route) => {
    intercepted = true;
    await route.abort("failed");
  };
  await page.route(endpoint, abortBeforeServer, { times: 1 });
  const form = page.locator("form.scaffold-revision-form");
  await form
    .locator('textarea[name="counter_evidence"]')
    .fill("Unrelated retained attempt used only to prove scoped acknowledgement.");
  await form
    .locator('textarea[name="reason"]')
    .fill("Preserve this separate logical operation.");
  page.once("dialog", (dialog) => dialog.accept());
  await form.locator('button[type="submit"]').click();
  const deadline = Date.now() + 10000;
  while (!intercepted && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  assert.equal(intercepted, true);
  await page
    .locator("#proposal-detail .error-text")
    .filter({ hasText: "transport failed" })
    .first()
    .waitFor({ state: "visible" });
  await page.unroute(endpoint, abortBeforeServer);
}

async function screenshot(page, name) {
  fs.mkdirSync(ARTIFACTS, { recursive: true });
  await page.screenshot({
    path: path.join(ARTIFACTS, name),
    fullPage: true,
  });
}

function readMetadata() {
  return JSON.parse(
    fs.readFileSync(path.join(ROOT, "fixture.json"), "utf-8"),
  );
}

async function run() {
  const port = process.env.BROWSER_MUTATION_RESPONSE_LOSS_PORT || (await freePort());
  const base = `http://127.0.0.1:${port}`;
  const server = startServer(port);
  await waitForHealth(base);

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

  let browser;
  try {
    const metadata = readMetadata();
    const payload = {
      ...FORM_PAYLOAD,
      expected_proposal_version_id:
        metadata.initial_version.proposal_version_id,
      expected_proposal_receipt_ref:
        metadata.initial_version.receipt_ref,
    };
    assert.equal(metadata.capability_id, CAPABILITY_ID);
    assert.equal(metadata.resolver_id, RESOLVER_ID);
    assert.equal(metadata.execution_allowed, false);

    browser = await chromium.launch(launchOptions);
    const context = await browser.newContext({
      extraHTTPHeaders: { Authorization: "Bearer alice-session" },
      serviceWorkers: "block",
    });
    const page = await context.newPage();
    const diagnostics = {
      consoleErrors: [],
      pageErrors: [],
      requestFailures: [],
    };
    page.on("console", (message) => {
      if (message.type() === "error") {
        diagnostics.consoleErrors.push(message.text());
      }
    });
    page.on("pageerror", (error) => diagnostics.pageErrors.push(String(error)));
    page.on("requestfailed", (request) => {
      if (
        request.method() === "POST" &&
        request.url() === `${base}${metadata.target_path}`
      ) {
        diagnostics.requestFailures.push(request.failure()?.errorText || "unknown");
      }
    });

    await openProposal(page, base, metadata);
    assert.equal(await mutationRegistry(page), null);
    assert.match(
      await page.locator("#boundary-line").textContent(),
      /execution_allowed=false/,
    );

    const requests = [];
    context.on("request", (request) => {
      if (
        request.method() === "POST" &&
        request.url() === `${base}${metadata.target_path}`
      ) {
        requests.push({
          key: request.headers()["idempotency-key"],
          binding:
            request.headers()["x-finharness-browser-mutation-binding"],
          body: request.postData(),
        });
      }
    });

    let injectedUpstreamStatus = null;
    let responseLossInjected = false;
    await context.route(
      `${base}${metadata.target_path}`,
      async (route) => {
        if (!responseLossInjected) {
          responseLossInjected = true;
          const upstream = await route.fetch({ maxRetries: 0 });
          injectedUpstreamStatus = upstream.status();
          await route.abort("connectionreset");
          return;
        }
        await route.continue();
      },
    );

    await submitReviewEvent(page);
    const firstError = page.locator("#proposal-detail .error-text").first();
    await firstError.waitFor({ state: "visible" });
    assert.match(await firstError.textContent(), /transport failed/i);
    assert.equal(injectedUpstreamStatus, 500);
    assert.equal(diagnostics.requestFailures.length, 1);
    assert.equal(requests.length, 1);

    const firstRegistry = await mutationRegistry(page);
    assert.equal(firstRegistry.schema, STORAGE_SCHEMA);
    assert.equal(firstRegistry.attempts.length, 1);
    assert.equal(firstRegistry.attempts[0].method, "POST");
    assert.equal(firstRegistry.attempts[0].endpoint, metadata.target_path);
    assert.equal(firstRegistry.attempts[0].body, JSON.stringify(payload));
    assert.ok(firstRegistry.attempts[0].identity_binding.binding_id);
    const firstKey = firstRegistry.attempts[0].idempotency_key;
    assert.equal(
      keyDigest(requests[0].key),
      keyDigest(firstKey),
      "the first intercepted request must use the retained key",
    );
    assert.equal(
      requests[0].binding,
      firstRegistry.attempts[0].identity_binding.binding_id,
    );
    assert.equal(requests[0].body, JSON.stringify(payload));

    const stageOne = probe(metadata);
    assert.equal(stageOne.domain_effect_count, 1);
    assert.equal(stageOne.domain_receipt_count, 1);
    assert.equal(stageOne.identity_receipt_count, 1);
    assert.equal(stageOne.identity_state, "pending");
    assert.equal(stageOne.identity_execution_allowed, false);
    assert.equal(stageOne.bound_effect_count, 1);
    assert.deepEqual(stageOne.domain_execution_allowed, [false]);
    assert.deepEqual(stageOne.domain_receipt_execution_allowed, [false]);
    const identityReceiptId = stageOne.identity_receipt_id;
    const receiptPath = path.join(
      metadata.receipt_root,
      "identity",
      `${identityReceiptId}.json`,
    );
    const faultMetadata = readMetadata();
    assert.equal(faultMetadata.terminalization_fault.triggered, true);
    assert.equal(faultMetadata.terminalization_fault.trigger_count, 1);
    assert.equal(
      (await page.locator("body").innerText()).includes(firstKey),
      false,
      "the raw idempotency key must not render in the UI",
    );
    await screenshot(page, "01-response-lost-attempt-retained.png");

    // This second real-form attempt is stopped before the server because it is
    // only an acknowledgement-scope sentinel, not the response-loss scenario.
    await retainUnrelatedScaffoldAttempt(page, base, metadata);
    const registryWithUnrelated = await mutationRegistry(page);
    assert.equal(registryWithUnrelated.attempts.length, 2);
    assert.equal(
      registryWithUnrelated.attempts.filter(
        (attempt) => attempt.endpoint === metadata.target_path,
      ).length,
      1,
    );
    assert.equal(
      registryWithUnrelated.attempts.filter(
        (attempt) =>
          attempt.endpoint ===
          `/proposals/${metadata.proposal_id}/decision-scaffold`,
      ).length,
      1,
    );

    await page.reload({ waitUntil: "networkidle" });
    await page.locator('button.tab[data-view="proposals"]').click();
    await page
      .locator(
        `#proposal-list button[data-proposal-id="${metadata.proposal_id}"]`,
      )
      .click();
    await page.locator("form.review-event-form").waitFor({ state: "visible" });
    await page.waitForTimeout(500);

    const ambiguousResponsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response.url() === `${base}${metadata.target_path}`,
    );
    await submitReviewEvent(page);
    const ambiguousResponse = await ambiguousResponsePromise;
    const ambiguousBody = await ambiguousResponse.json();
    assert.equal(
      ambiguousResponse.status(),
      409,
      `pending retry returned ${JSON.stringify(ambiguousBody)}`,
    );
    const ambiguousError = page.locator("#proposal-detail .error-text").first();
    await ambiguousError.waitFor({ state: "visible" });
    const visibleAmbiguous = await ambiguousError.textContent();

    assert.equal(ambiguousBody.detail.code, "mutation_outcome_ambiguous");
    assert.equal(ambiguousBody.detail.execution_allowed, false);
    assert.equal(
      ambiguousResponse.headers()["x-finharness-identity-receipt"],
      identityReceiptId,
    );
    assert.ok(ambiguousResponse.headers()["x-finharness-trace-id"]);
    assert.equal(
      ambiguousResponse.headers()["x-finharness-browser-mutation-binding"],
      firstRegistry.attempts[0].identity_binding.binding_id,
    );
    assert.match(visibleAmbiguous, /mutation_outcome_ambiguous/);
    assert.match(visibleAmbiguous, /trace:/);
    assert.doesNotMatch(visibleAmbiguous, /Saved/);
    assert.equal(requests.length, 2);
    assert.equal(
      keyDigest(requests[1].key),
      keyDigest(firstKey),
      "the pending retry must reuse the first key",
    );
    assert.equal(requests[1].body, JSON.stringify(payload));

    const secondRegistry = await mutationRegistry(page);
    assert.equal(secondRegistry.attempts.length, 2);
    assert.equal(
      keyDigest(
        secondRegistry.attempts.find(
          (attempt) => attempt.endpoint === metadata.target_path,
        ).idempotency_key,
      ),
      keyDigest(firstKey),
      "the retained target attempt must keep the first key",
    );
    const stageTwo = probe(metadata, identityReceiptId);
    assert.equal(stageTwo.domain_effect_count, 1);
    assert.equal(stageTwo.domain_receipt_count, 1);
    assert.equal(stageTwo.identity_state, "pending");
    assert.equal(stageTwo.bound_effect_count, 1);
    await screenshot(page, "02-ambiguous-retry-visible.png");

    const dryRun = reconcile(receiptPath, metadata);
    assert.equal(dryRun.ok, true);
    assert.equal(dryRun.dry_run, true);
    assert.equal(dryRun.receipt_id, identityReceiptId);
    assert.equal(dryRun.state, "pending");
    assert.equal(dryRun.resolver, RESOLVER_ID);
    assert.equal(dryRun.execution_allowed, false);
    assert.equal(dryRun.request.method, "POST");
    assert.equal(dryRun.request.path, metadata.target_path);

    const applied = reconcile(receiptPath, metadata, true);
    assert.equal(applied.ok, true);
    assert.equal(applied.dry_run, false);
    assert.equal(applied.receipt_id, identityReceiptId);
    assert.equal(applied.state, "reconciled_applied");
    assert.equal(applied.execution_allowed, false);
    assert.equal(applied.reconciliation.resolver_id, RESOLVER_ID);
    assert.equal(
      applied.reconciliation.domain_effect.execution_allowed,
      false,
    );

    const stageFour = probe(metadata, identityReceiptId);
    assert.equal(stageFour.domain_effect_count, 1);
    assert.equal(stageFour.domain_receipt_count, 1);
    assert.equal(stageFour.identity_state, "reconciled_applied");
    assert.equal(stageFour.resolver_id, RESOLVER_ID);

    const replayResponsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response.url() === `${base}${metadata.target_path}` &&
        response.status() === 200,
    );
    await submitReviewEvent(page);
    const replayResponse = await replayResponsePromise;
    const replayBody = await replayResponse.json();
    await page
      .locator("#api-status")
      .filter({ hasText: "Saved" })
      .waitFor({ state: "visible" });

    assert.equal(
      replayResponse.headers()["x-finharness-idempotent-replay"],
      "true",
    );
    assert.equal(
      replayResponse.headers()["x-finharness-identity-receipt"],
      identityReceiptId,
    );
    assert.equal(
      replayResponse.headers()["x-finharness-browser-mutation-binding"],
      firstRegistry.attempts[0].identity_binding.binding_id,
    );
    assert.equal(replayBody.execution_allowed, false);
    assert.equal(requests.length, 3);
    assert.equal(
      keyDigest(requests[2].key),
      keyDigest(firstKey),
      "the canonical replay must reuse the first key",
    );
    assert.equal(requests[2].body, JSON.stringify(payload));

    const terminalReceipt = JSON.parse(fs.readFileSync(receiptPath, "utf-8"));
    const canonicalBody = JSON.parse(
      Buffer.from(
        terminalReceipt.response.body_base64,
        "base64",
      ).toString("utf-8"),
    );
    assert.deepEqual(replayBody, canonicalBody);
    assert.equal(terminalReceipt.state, "reconciled_applied");
    const finalRegistry = await mutationRegistry(page);
    assert.equal(finalRegistry.schema, STORAGE_SCHEMA);
    assert.equal(finalRegistry.attempts.length, 1);
    assert.equal(
      finalRegistry.attempts[0].endpoint,
      `/proposals/${metadata.proposal_id}/decision-scaffold`,
    );
    assert.notEqual(
      keyDigest(finalRegistry.attempts[0].idempotency_key),
      keyDigest(firstKey),
      "the surviving attempt must be a separate logical operation",
    );

    const finalProbe = probe(metadata, identityReceiptId);
    assert.equal(finalProbe.domain_effect_count, 1);
    assert.equal(finalProbe.domain_receipt_count, 1);
    assert.equal(finalProbe.identity_receipt_count, 1);
    assert.equal(finalProbe.identity_state, "reconciled_applied");
    assert.equal(finalProbe.bound_effect_count, 1);
    assert.equal(finalProbe.identity_execution_allowed, false);
    assert.deepEqual(finalProbe.domain_execution_allowed, [false]);
    assert.deepEqual(finalProbe.domain_receipt_execution_allowed, [false]);

    await page
      .locator(".review-timeline-entry")
      .filter({ hasText: MARKER })
      .waitFor({ state: "visible" });
    assert.equal(
      await page
        .locator(".review-timeline-entry")
        .filter({ hasText: MARKER })
        .count(),
      1,
    );
    assert.equal(
      (await page.locator("body").innerText()).includes(firstKey),
      false,
      "the raw idempotency key must not render after recovery",
    );
    assert.equal(
      diagnostics.consoleErrors.some((message) => message.includes(firstKey)),
      false,
    );
    assert.deepEqual(diagnostics.pageErrors, []);
    await screenshot(page, "03-canonical-replay-recovered.png");

    await context.close();
    console.log(
      "Browser mutation response loss: PASS " +
        "(pending → ambiguous → reconciled_applied → replay; one domain effect).",
    );
  } finally {
    if (browser) await browser.close();
    await stopServer(server).catch(() => {});
    fs.rmSync(ROOT, { recursive: true, force: true });
  }
}

run().catch((error) => {
  console.error("Browser mutation response loss: FAIL");
  console.error(error && error.stack ? error.stack : String(error));
  process.exitCode = 1;
});
