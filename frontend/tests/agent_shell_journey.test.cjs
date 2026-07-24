"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const root = path.resolve(__dirname, "../..");
const frontend = path.join(root, "frontend-agent");
const html = fs.readFileSync(path.join(frontend, "index.html"), "utf8");
const appSource = fs.readFileSync(path.join(frontend, "app.js"), "utf8");

const world = {
  world_id: "capital_world_test",
  basis_digest: "capital_world:test-digest",
  status: "admitted",
  evidence_integrity: "verified",
  completeness: "complete",
  valuation_status: "valued",
  blockers: [],
  positions: [
    {
      symbol: "SPY",
      quantity: "9",
      unit_price: "1000",
      market_value: "9000",
      valuation_status: "valued",
      currency: "USD",
    },
  ],
  recovery_refs: [],
};

const driftedWorld = {
  ...world,
  world_id: "capital_world_test_drifted",
  basis_digest: "capital_world:test-digest:drifted",
};

const missionBundle = {
  launch_id: "launch_test",
  request_id: "mission:test:browser",
  constitution: {
    constitution_id: "constitution_test",
    principal_id: "principal:test",
    goals: ["Reduce concentration"],
    liquidity_floor: "1000",
    max_simulated_notional: "3000",
    prohibited_effects: [],
    supersedes: null,
    created_at_utc: "2026-07-24T00:00:00+00:00",
  },
  mission: {
    mission_id: "mission_test",
    principal_id: "principal:test",
    agent_id: "agent:test",
    objective: "Reduce concentration",
    success_conditions: ["One paper Effect reconciles"],
    constitution_ref: "constitution_test",
    state: "active",
    current_world_id: world.world_id,
    current_world_basis_digest: world.basis_digest,
    checkpoint_ids: [],
    created_at_utc: "2026-07-24T00:00:00+00:00",
    updated_at_utc: "2026-07-24T00:00:00+00:00",
    closed_reason: null,
  },
  belief: {
    belief_id: "belief_test",
    mission_id: "mission_test",
    claim: "SPY concentration may be high",
    confidence: "0.5",
    evidence_refs: [`capital-world:${world.world_id}`],
    counter_evidence_refs: [],
    review_condition: "Review if World changes",
    created_at_utc: "2026-07-24T00:00:00+00:00",
  },
  delegation: {
    delegation_id: "delegation_test",
    constitution_ref: "constitution_test",
    principal_id: "principal:test",
    agent_id: "agent:test",
    allowed_effect_kinds: ["simulated_order"],
    max_notional: "2500",
    max_uses: 3,
    expires_at_utc: "2026-07-25T00:00:00+00:00",
    state: "active",
    created_at_utc: "2026-07-24T00:00:00+00:00",
    updated_at_utc: "2026-07-24T00:00:00+00:00",
    revoked_reason: null,
  },
  world,
  created_at_utc: "2026-07-24T00:00:00+00:00",
  simulated_effect_allowed: true,
  live_execution_allowed: false,
};

const bootstrap = {
  schema_version: "finharness.agent_shell.v1",
  principal_id: "principal:test",
  principal_label: "Test Principal",
  agent_runtime_id: "agent:test",
  authentication_method: "test_static_session",
  model: {
    provider: "api.openai.com",
    model: "test-model",
    configured: false,
    base_url_configured: false,
    api_key_source: "absent",
    browser_secret_input_allowed: false,
  },
  world,
  missions: [],
  paper_broker_id: "broker:finharness-local-paper",
  paper_account_id: "execution:finharness-local-paper",
  runtime_available: true,
  simulated_effect_allowed: true,
  live_execution_allowed: false,
  browser_secret_input_allowed: false,
};

function response(body, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 || status === 201 ? "OK" : "Error",
    json: async () => body,
  });
}

async function waitFor(predicate, label) {
  for (let index = 0; index < 80; index += 1) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
  assert.fail(`timed out waiting for ${label}`);
}

(async () => {
  const dom = new JSDOM(html, {
    runScripts: "outside-only",
    url: "http://127.0.0.1:8766/agent-ui/",
  });
  let uuidCounter = 0;
  Object.defineProperty(dom.window, "crypto", {
    configurable: true,
    value: {
      randomUUID() {
        uuidCounter += 1;
        return `00000000-0000-4000-8000-${String(uuidCounter).padStart(12, "0")}`;
      },
    },
  });

  const requests = [];
  let worldRecovered = false;
  dom.window.fetch = (endpoint, options = {}) => {
    const method = options.method || "GET";
    requests.push({ endpoint, method, options });
    if (endpoint === "/agent/bootstrap") return response(bootstrap);
    if (endpoint === "/identity/browser-mutation-binding") {
      return response({ binding_id: "b".repeat(64) });
    }
    if (endpoint === "/agent/missions" && method === "POST") {
      return response(missionBundle, 201);
    }
    if (endpoint.endsWith("/world-drift") && method === "GET") {
      return response({
        mission_id: "mission_test",
        drifted: !worldRecovered,
        mission_world_id: worldRecovered ? driftedWorld.world_id : world.world_id,
        mission_world_basis_digest: worldRecovered
          ? driftedWorld.basis_digest
          : world.basis_digest,
        current_world: driftedWorld,
        can_checkpoint_and_resume: !worldRecovered,
        live_execution_allowed: false,
      });
    }
    if (endpoint.endsWith("/world-recovery") && method === "POST") {
      worldRecovered = true;
      return response({
        recovery_id: "world_recovery_test",
        request_id: "world-recovery:test:browser",
        mission_id: "mission_test",
        previous_world_id: world.world_id,
        previous_world_basis_digest: world.basis_digest,
        current_world: driftedWorld,
        checkpoint: {
          checkpoint_id: "checkpoint_test",
          mission_id: "mission_test",
          world_id: driftedWorld.world_id,
          world_basis_digest: driftedWorld.basis_digest,
          belief_refs: [],
          effect_refs: [],
          note: "Checkpoint current World",
          created_at_utc: "2026-07-24T00:00:30+00:00",
        },
        mission: {
          ...missionBundle.mission,
          current_world_id: driftedWorld.world_id,
          current_world_basis_digest: driftedWorld.basis_digest,
          checkpoint_ref: "mission-checkpoints/checkpoint_test.json",
        },
        domain_receipt_ref: "/tmp/world-recovery.json",
        recovered_at_utc: "2026-07-24T00:00:30+00:00",
        live_execution_allowed: false,
      });
    }
    if (endpoint.endsWith("/messages") && method === "POST") {
      return response({
        turn_id: "turn_test",
        request_id: "message:test:browser",
        mission_id: "mission_test",
        world_id: world.world_id,
        world_basis_digest: world.basis_digest,
        answer: "The World is admitted; this conversation cannot create an Effect.",
        observations: ["SPY is valued at 1000 USD."],
        uncertainties: ["Suitability is not established."],
        next_steps: ["Use the structured paper form only."],
        model_status: "unavailable",
        model_provider: "api.openai.com",
        model_name: "test-model",
        created_at_utc: "2026-07-24T00:01:00+00:00",
        execution_allowed: false,
        live_execution_allowed: false,
      });
    }
    if (endpoint.endsWith("/paper-effects") && method === "POST") {
      return response({
        mission_id: "mission_test",
        effect_intent: { effect_intent_id: "effect_test" },
        admission_id: "admission_test",
        verified_reference_price: "1000",
        admitted_notional: "1000",
        runtime: { jobId: "job_test", status: "succeeded" },
        execution: { execution_id: "execution_test", state: "completed" },
        simulated_effect: true,
        live_execution_allowed: false,
      });
    }
    return response({ detail: { message: `unexpected request: ${method} ${endpoint}` } }, 500);
  };

  dom.window.eval(appSource);
  const document = dom.window.document;

  await waitFor(
    () => document.querySelector("#connection-status").textContent === "Ready",
    "bootstrap",
  );
  assert.match(document.querySelector("#session-facts").textContent, /Test Principal/);
  assert.match(document.querySelector("#position-list").textContent, /SPY/);

  document.querySelector("#mission-objective").value = "Reduce concentration";
  document.querySelector("#mission-success").value = "One paper Effect reconciles";
  document.querySelector("#initial-belief").value = "SPY concentration may be high";
  document.querySelector("#mission-form").dispatchEvent(
    new dom.window.Event("submit", { bubbles: true, cancelable: true }),
  );
  await waitFor(() => !document.querySelector("#active-mission").hidden, "Mission render");
  assert.match(document.querySelector("#mission-summary").textContent, /mission_test/);
  await waitFor(
    () => !document.querySelector("#world-drift-card").hidden,
    "World drift card",
  );
  assert.match(
    document.querySelector("#world-drift-detail").textContent,
    /capital_world_test_drifted/,
  );
  document.querySelector("#world-recovery-button").click();
  await waitFor(
    () => document.querySelector("#effect-result").textContent.includes("checkpoint_test"),
    "World recovery",
  );
  assert.equal(document.querySelector("#world-drift-card").hidden, true);
  assert.match(document.querySelector("#mission-summary").textContent, /capital_world_test_drifted/);

  document.querySelector("#message-input").value = "What is uncertain?";
  document.querySelector("#message-form").dispatchEvent(
    new dom.window.Event("submit", { bubbles: true, cancelable: true }),
  );
  await waitFor(
    () => document.querySelectorAll("#conversation-log .turn.agent").length === 1,
    "conversation reply",
  );
  assert.match(document.querySelector("#conversation-log").textContent, /cannot create an Effect/);

  document.querySelector("#effect-quantity").value = "1";
  document.querySelector("#effect-rationale").value = "Bounded paper test";
  document.querySelector("#effect-form").dispatchEvent(
    new dom.window.Event("submit", { bubbles: true, cancelable: true }),
  );
  await waitFor(
    () => document.querySelector("#effect-result").textContent.includes("job_test"),
    "paper Effect result",
  );
  assert.match(document.querySelector("#effect-result").textContent, /verified price 1000/);

  const mutations = requests.filter((item) => item.method === "POST");
  assert.equal(mutations.length, 4);
  for (const mutation of mutations) {
    assert.ok(mutation.options.headers["Idempotency-Key"]);
    assert.equal(
      mutation.options.headers["X-FinHarness-Browser-Mutation-Binding"],
      "b".repeat(64),
    );
    const body = JSON.parse(mutation.options.body);
    assert.ok(body.request_id);
    assert.equal(Object.hasOwn(body, "api_key"), false);
    assert.equal(Object.hasOwn(body, "executable"), false);
    assert.equal(Object.hasOwn(body, "environment"), false);
  }

  console.log("agent shell browser journey: ok");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
