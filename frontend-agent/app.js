(() => {
  "use strict";

  const state = {
    bootstrap: null,
    mission: null,
    worldDrift: null,
  };

  const selectors = {
    connectionStatus: document.querySelector("#connection-status"),
    refresh: document.querySelector("#refresh-button"),
    sessionFacts: document.querySelector("#session-facts"),
    worldStatus: document.querySelector("#world-status"),
    positionList: document.querySelector("#position-list"),
    missionForm: document.querySelector("#mission-form"),
    missionSubmit: document.querySelector("#mission-submit"),
    missionMessage: document.querySelector("#mission-message"),
    activeMission: document.querySelector("#active-mission"),
    missionState: document.querySelector("#mission-state"),
    missionSummary: document.querySelector("#mission-summary"),
    messageForm: document.querySelector("#message-form"),
    messageInput: document.querySelector("#message-input"),
    conversationLog: document.querySelector("#conversation-log"),
    effectForm: document.querySelector("#effect-form"),
    effectSymbol: document.querySelector("#effect-symbol"),
    effectSubmit: document.querySelector("#effect-submit"),
    effectResult: document.querySelector("#effect-result"),
    worldDriftCard: document.querySelector("#world-drift-card"),
    worldDriftDetail: document.querySelector("#world-drift-detail"),
    worldRecoveryButton: document.querySelector("#world-recovery-button"),
    factTemplate: document.querySelector("#fact-template"),
  };

  function requestId(prefix) {
    const id = window.crypto.randomUUID().replaceAll("-", "");
    return `${prefix}:${id}`;
  }

  class ApiError extends Error {
    constructor(message, detail, status) {
      super(message);
      this.name = "ApiError";
      this.detail = detail;
      this.status = status;
    }
  }

  async function responseJson(response) {
    return response.json().catch(() => ({}));
  }

  async function apiGet(path) {
    const response = await fetch(path, { headers: { Accept: "application/json" } });
    const body = await responseJson(response);
    if (!response.ok) {
      throw new ApiError(
        body.detail?.message || body.detail || response.statusText,
        body.detail,
        response.status,
      );
    }
    return body;
  }

  async function apiPost(path, body, key) {
    const binding = await apiGet("/identity/browser-mutation-binding");
    const response = await fetch(path, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "Idempotency-Key": key,
        "X-FinHarness-Browser-Mutation-Binding": binding.binding_id,
      },
      body: JSON.stringify(body),
    });
    const payload = await responseJson(response);
    if (!response.ok) {
      throw new ApiError(
        payload.detail?.message || payload.detail || response.statusText,
        payload.detail,
        response.status,
      );
    }
    return payload;
  }

  function setConnection(text, good = true) {
    selectors.connectionStatus.textContent = text;
    selectors.connectionStatus.className = `pill ${good ? "good" : "bad"}`;
  }

  function renderFacts(rows) {
    selectors.sessionFacts.replaceChildren();
    for (const [label, value] of rows) {
      const node = selectors.factTemplate.content.firstElementChild.cloneNode(true);
      node.querySelector("dt").textContent = label;
      node.querySelector("dd").textContent = value ?? "Unknown";
      selectors.sessionFacts.append(node);
    }
  }

  function renderWorld(world) {
    selectors.worldStatus.replaceChildren();
    const status = document.createElement("strong");
    status.textContent = `${world.status} · ${world.valuation_status}`;
    selectors.worldStatus.append(status);
    const identity = document.createElement("p");
    identity.className = "muted";
    identity.textContent = world.world_id;
    selectors.worldStatus.append(identity);
    if (world.blockers.length) {
      const blockers = document.createElement("p");
      blockers.className = "error";
      blockers.textContent = world.blockers.join(", ");
      selectors.worldStatus.append(blockers);
    }

    selectors.positionList.replaceChildren();
    for (const position of world.positions) {
      const node = document.createElement("div");
      node.className = "position";
      const title = document.createElement("strong");
      title.textContent = position.symbol;
      const detail = document.createElement("span");
      detail.textContent = `${position.quantity} units · ${position.unit_price ?? "unpriced"} ${position.currency ?? ""}`;
      node.append(title, detail);
      selectors.positionList.append(node);
    }

    selectors.effectSymbol.replaceChildren();
    for (const position of world.positions) {
      const option = document.createElement("option");
      option.value = position.symbol;
      option.textContent = `${position.symbol} · ${position.quantity} units`;
      selectors.effectSymbol.append(option);
    }
    selectors.effectSubmit.disabled = !state.bootstrap?.simulated_effect_allowed || !world.positions.length;
  }

  function renderWorldDrift(drift) {
    state.worldDrift = drift;
    const visible = Boolean(drift?.drifted);
    selectors.worldDriftCard.hidden = !visible;
    selectors.worldRecoveryButton.disabled = !drift?.can_checkpoint_and_resume;
    if (!visible) {
      selectors.worldDriftDetail.textContent = "";
      return;
    }
    selectors.worldDriftDetail.textContent = `Mission: ${drift.mission_world_id} → Current: ${drift.current_world.world_id}`;
  }

  async function refreshWorldDrift() {
    if (!state.mission) return;
    try {
      const drift = await apiGet(
        `/agent/missions/${encodeURIComponent(state.mission.mission.mission_id)}/world-drift`,
      );
      renderWorldDrift(drift);
    } catch (error) {
      selectors.effectResult.textContent = `World drift check failed: ${error.message}`;
    }
  }

  function renderMission(bundle) {
    state.mission = bundle;
    selectors.activeMission.hidden = false;
    selectors.missionState.textContent = bundle.mission.state;
    selectors.missionState.className = `pill ${bundle.mission.state === "active" ? "good" : "bad"}`;
    selectors.missionSummary.replaceChildren();
    const lines = [
      ["Objective", bundle.mission.objective],
      ["Mission", bundle.mission.mission_id],
      ["Delegation", `${bundle.delegation.max_notional} max · ${bundle.delegation.max_uses} uses`],
      ["Belief", bundle.belief.claim],
      ["World", bundle.mission.current_world_id],
    ];
    for (const [label, value] of lines) {
      const row = document.createElement("div");
      const strong = document.createElement("strong");
      strong.textContent = `${label}: `;
      row.append(strong, document.createTextNode(value));
      selectors.missionSummary.append(row);
    }
    void refreshWorldDrift();
  }

  function appendTurn(kind, text, details = []) {
    const node = document.createElement("div");
    node.className = `turn ${kind}`;
    const label = document.createElement("strong");
    label.textContent = kind === "user" ? "You" : "Agent";
    const paragraph = document.createElement("p");
    paragraph.textContent = text;
    node.append(label, paragraph);
    if (details.length) {
      const list = document.createElement("ul");
      for (const detail of details) {
        const item = document.createElement("li");
        item.textContent = detail;
        list.append(item);
      }
      node.append(list);
    }
    selectors.conversationLog.append(node);
    selectors.conversationLog.scrollTop = selectors.conversationLog.scrollHeight;
  }

  async function loadBootstrap() {
    setConnection("Connecting", true);
    try {
      const bootstrap = await apiGet("/agent/bootstrap");
      state.bootstrap = bootstrap;
      renderFacts([
        ["Principal", bootstrap.principal_label || bootstrap.principal_id],
        ["Agent runtime", bootstrap.agent_runtime_id],
        ["Authentication", bootstrap.authentication_method],
        ["Model", `${bootstrap.model.provider} / ${bootstrap.model.model}`],
        ["Model configured", String(bootstrap.model.configured)],
        ["Runtime", bootstrap.runtime_available ? "available" : "unavailable"],
        ["Paper account", bootstrap.paper_account_id],
      ]);
      renderWorld(bootstrap.world);
      if (!state.mission && bootstrap.missions.length) {
        const active = bootstrap.missions.find((item) => item.state === "active") || bootstrap.missions[0];
        const bundle = await apiGet(`/agent/missions/${encodeURIComponent(active.mission_id)}`);
        renderMission(bundle);
      }
      setConnection("Ready", true);
    } catch (error) {
      setConnection("Unavailable", false);
      selectors.missionMessage.textContent = error.message;
    }
  }

  selectors.refresh.addEventListener("click", loadBootstrap);

  selectors.missionForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    selectors.missionSubmit.disabled = true;
    selectors.missionMessage.textContent = "Starting Mission…";
    const key = requestId("mission");
    const successConditions = document.querySelector("#mission-success").value
      .split("\n")
      .map((item) => item.trim())
      .filter(Boolean);
    const body = {
      request_id: key,
      objective: document.querySelector("#mission-objective").value,
      success_conditions: successConditions,
      liquidity_floor: document.querySelector("#liquidity-floor").value,
      max_simulated_notional: document.querySelector("#constitution-max").value,
      delegation_max_notional: document.querySelector("#delegation-max").value,
      delegation_max_uses: Number(document.querySelector("#delegation-uses").value),
      delegation_ttl_minutes: 1440,
      initial_belief: document.querySelector("#initial-belief").value,
      belief_confidence: "0.5",
      belief_review_condition: document.querySelector("#review-condition").value,
    };
    try {
      const bundle = await apiPost("/agent/missions", body, key);
      renderMission(bundle);
      selectors.missionMessage.textContent = "Mission started.";
    } catch (error) {
      selectors.missionMessage.textContent = error.message;
    } finally {
      selectors.missionSubmit.disabled = false;
    }
  });

  selectors.messageForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!state.mission) return;
    const message = selectors.messageInput.value.trim();
    if (!message) return;
    const key = requestId("message");
    appendTurn("user", message);
    selectors.messageInput.value = "";
    try {
      const reply = await apiPost(
        `/agent/missions/${encodeURIComponent(state.mission.mission.mission_id)}/messages`,
        { request_id: key, message },
        key,
      );
      appendTurn("agent", reply.answer, [
        ...reply.observations,
        ...reply.uncertainties.map((item) => `Uncertainty: ${item}`),
        ...reply.next_steps.map((item) => `Next: ${item}`),
      ]);
    } catch (error) {
      appendTurn("agent", `Message failed: ${error.message}`);
    }
  });

  selectors.worldRecoveryButton.addEventListener("click", async () => {
    if (!state.mission || !state.worldDrift?.drifted) return;
    selectors.worldRecoveryButton.disabled = true;
    selectors.effectResult.textContent = "Checkpointing the current admitted Capital World…";
    const key = requestId("world-recovery");
    try {
      const result = await apiPost(
        `/agent/missions/${encodeURIComponent(state.mission.mission.mission_id)}/world-recovery`,
        {
          request_id: key,
          action: "checkpoint_and_resume",
          note: "Checkpoint the newly admitted Capital World before another paper Effect.",
        },
        key,
      );
      state.mission = {
        ...state.mission,
        mission: result.mission,
        world: result.current_world,
      };
      renderMission(state.mission);
      renderWorld(result.current_world);
      renderWorldDrift(null);
      selectors.effectResult.textContent = `Mission resumed at checkpoint ${result.checkpoint.checkpoint_id}.`;
    } catch (error) {
      selectors.effectResult.textContent = `World recovery failed: ${error.message}`;
      selectors.worldRecoveryButton.disabled = false;
    }
  });

  selectors.effectForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!state.mission) return;
    selectors.effectSubmit.disabled = true;
    selectors.effectResult.textContent = "Running recoverable paper Effect…";
    const key = requestId("effect");
    const body = {
      request_id: key,
      symbol: selectors.effectSymbol.value,
      side: document.querySelector("#effect-side").value,
      quantity: document.querySelector("#effect-quantity").value,
      rationale: document.querySelector("#effect-rationale").value,
    };
    try {
      const result = await apiPost(
        `/agent/missions/${encodeURIComponent(state.mission.mission.mission_id)}/paper-effects`,
        body,
        key,
      );
      selectors.effectResult.replaceChildren();
      const card = document.createElement("div");
      card.className = "effect-card";
      card.textContent = `Completed · Job ${result.runtime.jobId} · Effect ${result.execution.execution_id} · verified price ${result.verified_reference_price}`;
      selectors.effectResult.append(card);
    } catch (error) {
      if (error.detail?.code === "mission_world_changed" && error.detail.drift) {
        renderWorldDrift(error.detail.drift);
      }
      selectors.effectResult.innerHTML = `<p class="error"></p>`;
      selectors.effectResult.querySelector("p").textContent = error.message;
    } finally {
      selectors.effectSubmit.disabled = !state.bootstrap?.simulated_effect_allowed;
    }
  });

  loadBootstrap();
})();
