"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");
const {
  createSerialLockManager,
  createSharedStorage,
  installSharedStorage,
  installWebLocks,
} = require("./_web_locks.cjs");

const frontendDir = path.resolve(__dirname, "..");

function successfulWriteResponse() {
  return {
    ok: true,
    status: 200,
    statusText: "OK",
    headers: {
      get(name) {
        return String(name).toLowerCase() ===
          "x-finharness-identity-receipt"
          ? "identity_cleanup_ui"
          : null;
      },
    },
    json: async () => ({
      execution_allowed: false,
    }),
  };
}

function loadCockpit({
  storage,
  locks,
}) {
  const html = fs.readFileSync(
    path.join(frontendDir, "index.html"),
    "utf8",
  );

  const dom = new JSDOM(html, {
    runScripts: "outside-only",
    url: "https://cockpit.finharness.test/",
  });

  installSharedStorage(
    dom.window,
    storage,
  );
  installWebLocks(
    dom.window,
    locks,
  );

  dom.window.console.debug = () => {};
  dom.window.console.error = () => {};

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

  return dom;
}

function settle() {
  return new Promise((resolve) => {
    setTimeout(resolve, 40);
  });
}

(async () => {
  const storage = createSharedStorage();
  const locks = createSerialLockManager();
  const dom = loadCockpit({
    storage,
    locks,
  });

  let postCalls = 0;

  dom.window.confirm = () => true;
  dom.window.fetch = async (
    requestPath,
    options = {},
  ) => {
    const method =
      String(options.method || "GET").toUpperCase();

    if (
      method === "POST" &&
      String(requestPath) ===
        "/proposals/prop_1/review-events"
    ) {
      postCalls += 1;
      return successfulWriteResponse();
    }

    if (
      method === "GET" &&
      String(requestPath).startsWith(
        "/proposals?",
      )
    ) {
      return {
        ok: true,
        status: 200,
        statusText: "OK",
        headers: {
          get() {
            return null;
          },
        },
        json: async () => [],
      };
    }

    return {
      ok: true,
      status: 200,
      statusText: "OK",
      headers: {
        get() {
          return null;
        },
      },
      json: async () => ({}),
    };
  };

  const parent =
    dom.window.document.createElement("div");

  dom.window.renderReviewEventForm(
    parent,
    "prop_1",
  );

  const form = parent.querySelector("form");
  form.querySelector('[name="kind"]').value =
    "annotation";
  form.querySelector('[name="reason"]').value =
    "The server write succeeds.";
  form.querySelector('[name="text"]').value =
    "Only local cleanup fails.";

  storage.failNextRemove(
    new Error("simulated cleanup failure"),
  );

  form.dispatchEvent(
    new dom.window.Event("submit", {
      cancelable: true,
      bubbles: true,
    }),
  );

  await settle();

  assert.equal(
    postCalls,
    1,
    "cleanup failure must not send a second write",
  );

  assert.equal(
    form.querySelector(
      'button[type="submit"]',
    ).disabled,
    true,
    "committed form remains disabled",
  );

  assert.equal(
    dom.window.document.querySelector(
      "#api-status",
    ).textContent,
    "Saved; retry state retained",
  );

  const detailText =
    dom.window.document.querySelector(
      "#proposal-detail",
    ).textContent;

  assert.match(
    detailText,
    /Saved, but local retry state could not be cleared/,
  );

  assert.doesNotMatch(
    detailText,
    /Write failed:/,
    "successful mutation must not be labelled failed",
  );

  const registryKey =
    dom.window.FinHarness.api
      .MUTATION_ATTEMPTS_STORAGE_KEY;

  const retained = JSON.parse(
    storage.getItem(registryKey),
  );

  assert.equal(
    retained.attempts.length,
    1,
    "safe replay attempt remains durable",
  );

  console.log(
    "mutation_acknowledgement_semantics.test.cjs: " +
      "all assertions passed",
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
