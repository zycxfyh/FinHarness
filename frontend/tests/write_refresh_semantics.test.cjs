"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const frontendDir = path.resolve(__dirname, "..");

function successfulWriteResponse() {
  return {
    ok: true,
    status: 200,
    statusText: "OK",
    headers: {
      get() {
        return null;
      },
    },
    json: async () => ({
      execution_allowed: false,
    }),
  };
}

function loadCockpitWindow() {
  const html = fs.readFileSync(
    path.join(frontendDir, "index.html"),
    "utf8",
  );

  const dom = new JSDOM(html, {
    runScripts: "outside-only",
    url: "https://cockpit.finharness.test/",
  });

  dom.window.console.debug = () => {};
  dom.window.console.error = () => {};

  dom.window.fetch = async () => {
    throw new Error("fetch disabled during bootstrap");
  };

  for (const filename of [
    "api.js",
    "state.js",
    "actions.js",
    "app.js",
  ]) {
    dom.window.eval(
      fs.readFileSync(
        path.join(frontendDir, filename),
        "utf8",
      ),
    );
  }

  return dom.window;
}

function settle() {
  return new Promise((resolve) => {
    setTimeout(resolve, 25);
  });
}

async function proveSavedRefreshFailure({
  name,
  method,
  endpoint,
  renderForm,
  fillForm,
  confirm = false,
}) {
  const window = loadCockpitWindow();
  const parent = window.document.createElement("div");

  let writeCalls = 0;
  let refreshCalls = 0;

  window.confirm = () => confirm;

  window.fetch = async (requestPath, options = {}) => {
    const normalizedMethod =
      String(options.method || "GET").toUpperCase();
    const normalizedPath = String(requestPath);

    if (
      normalizedMethod === method &&
      normalizedPath === endpoint
    ) {
      writeCalls += 1;
      return successfulWriteResponse();
    }

    refreshCalls += 1;
    throw new Error("simulated refresh failure");
  };

  renderForm(window, parent);

  const form = parent.querySelector("form");
  assert.ok(form, `${name}: form must render`);

  fillForm(form);

  form.dispatchEvent(
    new window.Event("submit", {
      cancelable: true,
      bubbles: true,
    }),
  );

  await settle();

  assert.equal(
    writeCalls,
    1,
    `${name}: the governed write must run exactly once`,
  );

  assert.ok(
    refreshCalls >= 1,
    `${name}: the post-write refresh must be attempted`,
  );

  const submitButton = form.querySelector(
    'button[type="submit"]',
  );

  assert.equal(
    submitButton.disabled,
    true,
    `${name}: committed form must remain disabled`,
  );

  const status =
    window.document.querySelector("#api-status");

  assert.equal(
    status.textContent,
    "Saved; refresh failed",
    `${name}: refresh failure must preserve saved status`,
  );

  const proposalDetail =
    window.document.querySelector("#proposal-detail");

  assert.match(
    proposalDetail.textContent,
    /Saved, but refresh failed: simulated refresh failure/,
    `${name}: UI must distinguish refresh failure`,
  );

  assert.doesNotMatch(
    proposalDetail.textContent,
    /Write failed:/,
    `${name}: committed write must not be reported as failed`,
  );
}

(async () => {
  await proveSavedRefreshFailure({
    name: "review event",
    method: "POST",
    endpoint:
      "/proposals/prop_1/review-events",
    confirm: true,
    renderForm(window, parent) {
      window.renderReviewEventForm(
        parent,
        "prop_1",
      );
    },
    fillForm(form) {
      form.querySelector('[name="kind"]').value =
        "annotation";
      form.querySelector('[name="attester"]').value =
        "operator";
      form.querySelector('[name="reason"]').value =
        "Record review evidence.";
      form.querySelector('[name="text"]').value =
        "Refresh may fail after commit.";
    },
  });

  await proveSavedRefreshFailure({
    name: "scaffold revision",
    method: "PATCH",
    endpoint:
      "/proposals/prop_1/decision-scaffold",
    confirm: true,
    renderForm(window, parent) {
      window.renderScaffoldRevisionForm(
        parent,
        "prop_1",
      );
    },
    fillForm(form) {
      form.querySelector(
        '[name="counter_evidence"]',
      ).value = "Counter-evidence condition.";
      form.querySelector('[name="attester"]').value =
        "operator";
      form.querySelector('[name="reason"]').value =
        "Record falsification condition.";
    },
  });

  await proveSavedRefreshFailure({
    name: "attestation",
    method: "POST",
    endpoint:
      "/proposals/prop_1/attest",
    renderForm(window, parent) {
      window.renderAttestationForm(
        parent,
        "prop_1",
        {
          proposal_version_id:
            "proposal_version_1",
          receipt_ref:
            "data/receipts/proposals/prop_1.json",
        },
      );
    },
    fillForm(form) {
      form.querySelector('[name="decision"]').value =
        "approved";
      form.querySelector('[name="attester"]').value =
        "operator";
      form.querySelector('[name="reason"]').value =
        "Human decision evidence.";
    },
  });

  console.log(
    "write_refresh_semantics.test.cjs: " +
      "all assertions passed",
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
