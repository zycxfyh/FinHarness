const state = {
  activeView: "overview",
  selectedProposalId: null,
  proposalFilter: "all",
};

const productNonClaims = [
  "Read-only cockpit summary.",
  "Not investment advice.",
  "Not execution authorization.",
];

const selectors = {
  status: document.querySelector("#api-status"),
  refresh: document.querySelector("#refresh-button"),
  tabs: [...document.querySelectorAll(".tab")],
  views: {
    overview: document.querySelector("#overview-view"),
    exposure: document.querySelector("#exposure-view"),
    proposals: document.querySelector("#proposals-view"),
    timeline: document.querySelector("#timeline-view"),
  },
  summaryGrid: document.querySelector("#summary-grid"),
  dailyBriefHeadline: document.querySelector("#daily-brief-headline"),
  dailyBriefSections: document.querySelector("#daily-brief-sections"),
  exposureGrid: document.querySelector("#exposure-grid"),
  exposureHoldings: document.querySelector("#exposure-holdings"),
  exposureObligations: document.querySelector("#exposure-obligations"),
  exposureGaps: document.querySelector("#exposure-gaps"),
  latestBrief: document.querySelector("#latest-brief"),
  controls: document.querySelector("#controls-block"),
  proposalFilter: document.querySelector("#proposal-filter"),
  proposalList: document.querySelector("#proposal-list"),
  proposalDetail: document.querySelector("#proposal-detail"),
  timelineList: document.querySelector("#timeline-list"),
  emptyTemplate: document.querySelector("#empty-template"),
  boundaryLine: document.querySelector("#boundary-line"),
};

function setStatus(text, tone = "") {
  selectors.status.textContent = text;
  selectors.status.className = `status-pill ${tone}`.trim();
}

function clear(element) {
  element.replaceChildren();
}

function textElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) {
    element.className = className;
  }
  element.textContent = text;
  return element;
}

function emptyNode() {
  return selectors.emptyTemplate.content.firstElementChild.cloneNode(true);
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") {
    return "Unknown";
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  return String(value);
}

function formatMoney(value) {
  if (typeof value !== "number") {
    return "Unknown";
  }
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  }).format(value);
}

function renderRows(element, rows) {
  clear(element);
  if (!rows.length) {
    element.append(emptyNode());
    return;
  }
  for (const [key, value] of rows) {
    const row = document.createElement("div");
    row.className = "data-row";
    row.append(textElement("span", "data-key", key));
    row.append(textElement("span", "data-value", formatValue(value)));
    element.append(row);
  }
}

function renderNonClaims(element, nonClaims = productNonClaims) {
  const wrap = document.createElement("div");
  wrap.className = "non-claims";
  for (const claim of nonClaims) {
    wrap.append(textElement("span", "tag", claim));
  }
  element.append(wrap);
}

async function apiGet(path) {
  const response = await fetch(path, { headers: { accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function apiPost(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: {
      accept: "application/json",
      "content-type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body.detail ? JSON.stringify(body.detail) : response.statusText;
    throw new Error(`${response.status} ${detail}`);
  }
  return body;
}

function activate(view) {
  state.activeView = view;
  for (const tab of selectors.tabs) {
    tab.classList.toggle("active", tab.dataset.view === view);
  }
  for (const [name, element] of Object.entries(selectors.views)) {
    element.classList.toggle("active", name === view);
  }
  refresh();
}

function metric(label, value) {
  const node = document.createElement("div");
  node.className = "metric";
  node.append(textElement("span", "metric-label", label));
  node.append(textElement("span", "metric-value", value));
  return node;
}

function renderDailyBrief(dailyBrief) {
  selectors.dailyBriefHeadline.textContent = dailyBrief.headline;
  clear(selectors.dailyBriefSections);
  for (const section of dailyBrief.sections) {
    selectors.dailyBriefSections.append(textElement("h4", "", section.title));
    const list = document.createElement("ul");
    list.className = "brief-lines";
    for (const line of section.lines) {
      list.append(textElement("li", "", line));
    }
    selectors.dailyBriefSections.append(list);
  }
  renderNonClaims(selectors.dailyBriefSections, dailyBrief.non_claims);
}

async function renderOverview() {
  const [summary, dailyBrief, brief, controls, limits] = await Promise.all([
    apiGet("/dashboard/summary"),
    apiGet("/brief/daily"),
    apiGet("/brief/latest"),
    apiGet("/controls/status"),
    apiGet("/controls/limits"),
  ]);

  renderDailyBrief(dailyBrief);

  clear(selectors.summaryGrid);
  selectors.summaryGrid.append(
    metric("Accounts", summary.account_count),
    metric("Positions", summary.position_count),
    metric("Market Value", formatMoney(summary.total_market_value)),
    metric("Liabilities", summary.liability_count),
    metric("Liability Balance", formatMoney(summary.liability_balance_total)),
    metric("Goals", summary.goal_count),
    metric("Cashflows", summary.cashflow_count),
    metric("Tax Events", summary.tax_event_count),
    metric("Insurance", summary.insurance_policy_count),
    metric("Documents", summary.document_count),
    metric("Open Reviews", summary.open_proposal_count),
    metric("Receipts", summary.receipt_count),
    metric("Execution", formatValue(summary.execution_allowed)),
  );

  renderRows(selectors.latestBrief, [
    ["Available", brief.available],
    ["Receipt", brief.receipt?.receipt_id],
    ["Kind", brief.receipt?.kind],
    ["Path", brief.receipt?.path],
  ]);
  renderNonClaims(selectors.latestBrief, brief.non_claims);

  renderRows(selectors.controls, [
    ["Execution endpoints", controls.api_execution_endpoints_present],
    ["Approval grants execution", controls.proposal_approval_is_execution_authorization],
    ["Raise limits via API", limits.raising_limits_via_api_allowed],
    ["Execution allowed", controls.execution_allowed],
  ]);
  renderNonClaims(selectors.controls, controls.non_claims);
}

function proposalStatusTag(proposal) {
  const tag = textElement(
    "span",
    `tag ${proposal.open_for_review ? "open" : "attested"}`,
    proposal.open_for_review ? "open" : "attested",
  );
  return tag;
}

async function fetchProposals() {
  const query = new URLSearchParams({ status: state.proposalFilter });
  return apiGet(`/proposals?${query.toString()}`);
}

function renderProposalList(proposals) {
  clear(selectors.proposalList);
  if (!proposals.length) {
    selectors.proposalList.append(emptyNode());
    return;
  }
  if (!state.selectedProposalId) {
    state.selectedProposalId = proposals[0].proposal.proposal_id;
  }
  if (!proposals.some((item) => item.proposal.proposal_id === state.selectedProposalId)) {
    state.selectedProposalId = proposals[0].proposal.proposal_id;
  }
  for (const item of proposals) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "item";
    button.classList.toggle("active", item.proposal.proposal_id === state.selectedProposalId);
    button.dataset.proposalId = item.proposal.proposal_id;
    button.append(textElement("span", "item-title", item.proposal.claim));
    button.append(textElement("span", "item-meta", item.proposal.kind));
    button.append(proposalStatusTag(item));
    button.addEventListener("click", () => {
      state.selectedProposalId = item.proposal.proposal_id;
      renderProposals();
    });
    selectors.proposalList.append(button);
  }
}

function renderAttestations(parent, attestations) {
  if (!attestations.length) {
    parent.append(textElement("p", "empty-state", "No attestations recorded."));
    return;
  }
  for (const attestation of attestations) {
    const item = document.createElement("div");
    item.className = "item";
    item.append(
      textElement(
        "span",
        "item-title",
        `${decisionLabel(attestation)} by ${attestation.attester}`,
      ),
    );
    item.append(textElement("span", "item-meta", attestation.reason));
    parent.append(item);
  }
}

function renderAttestationForm(parent, proposalId) {
  const form = document.createElement("form");
  form.className = "attestation-form";
  form.innerHTML = `
    <div class="form-row">
      <label for="attestation-decision">Decision</label>
      <select id="attestation-decision" name="decision">
        <option value="approved">attested</option>
        <option value="rejected">rejected</option>
      </select>
    </div>
    <div class="form-row">
      <label for="attestation-attester">Attester</label>
      <input id="attestation-attester" name="attester" autocomplete="name" />
    </div>
    <div class="form-row">
      <label for="attestation-reason">Reason</label>
      <textarea id="attestation-reason" name="reason"></textarea>
    </div>
    <button class="submit-button" type="submit">Record Attestation</button>
  `;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    try {
      await apiPost(`/proposals/${proposalId}/attest`, {
        decision: data.get("decision"),
        attester: data.get("attester"),
        reason: data.get("reason"),
      });
      setStatus("Synced", "ok");
      await renderProposals();
    } catch (error) {
      setStatus("API error", "error");
      selectors.proposalDetail.prepend(textElement("p", "error-text", error.message));
    }
  });
  parent.append(form);
}

function decisionLabel(attestation) {
  return attestation.decision === "approved" ? "attested" : attestation.decision;
}

const STRUCTURAL_EVIDENCE_KEYS = new Set([
  "options",
  "key_risks",
  "reversibility",
  "dimension",
  "research_evidence",
]);

function renderTextList(parent, title, values) {
  if (!Array.isArray(values) || !values.length) {
    return;
  }
  parent.append(textElement("h4", "", title));
  for (const value of values) {
    parent.append(textElement("p", "item-meta", String(value)));
  }
}

function renderCandidateDetail(parent, proposal) {
  const evidence = proposal.evidence || {};
  const options = Array.isArray(evidence.options) ? evidence.options : [];
  // Only capital-allocation candidates carry a dimension/options block; other
  // (e.g. trading-domain) proposals fall through unchanged.
  if (!evidence.dimension && !options.length) {
    return;
  }
  parent.append(textElement("h4", "", "Capital allocation"));
  const meta = document.createElement("div");
  meta.className = "data-row";
  meta.append(textElement("span", "data-key", "Dimension"));
  meta.append(textElement("span", "data-value", formatValue(evidence.dimension)));
  parent.append(meta);

  // Trigger evidence: scalar metrics, kept descriptive (not claimed exact).
  const triggerRows = Object.entries(evidence)
    .filter(([key, value]) => !STRUCTURAL_EVIDENCE_KEYS.has(key) && typeof value !== "object")
    .map(([key, value]) => [key, value]);
  if (Array.isArray(evidence.source_refs) && evidence.source_refs.length) {
    triggerRows.push(["source_refs", evidence.source_refs.join(", ")]);
  }
  if (triggerRows.length) {
    parent.append(textElement("h4", "", "Trigger evidence"));
    for (const [key, value] of triggerRows) {
      const row = document.createElement("div");
      row.className = "data-row";
      row.append(textElement("span", "data-key", key));
      row.append(textElement("span", "data-value", formatValue(value)));
      parent.append(row);
    }
  }

  if (options.length) {
    parent.append(textElement("h4", "", "Options"));
    for (const option of options) {
      const item = document.createElement("div");
      item.className = "item";
      item.append(textElement("span", "item-title", `[${option.kind}] ${option.label}`));
      if (option.cost) {
        item.append(textElement("span", "item-meta", `Cost: ${option.cost}`));
      }
      if (option.reversibility) {
        item.append(textElement("span", "item-meta", `Reversibility: ${option.reversibility}`));
      }
      parent.append(item);
    }
  }

  renderTextList(parent, "Key risks", evidence.key_risks);
  if (evidence.reversibility) {
    parent.append(textElement("h4", "", "Reversibility"));
    parent.append(textElement("p", "item-meta", evidence.reversibility));
  }
  renderTextList(parent, "Assumptions", proposal.assumptions && proposal.assumptions.items);
  renderTextList(parent, "Limitations", proposal.limitations && proposal.limitations.items);
}

function renderRevisionHistory(parent, revisionHistory) {
  const revisions =
    revisionHistory && Array.isArray(revisionHistory.revisions) ? revisionHistory.revisions : [];
  parent.append(textElement("h4", "", "Revisions"));
  if (!revisions.length) {
    parent.append(textElement("p", "empty-state", "No revisions recorded."));
    return;
  }
  for (const revision of revisions) {
    const proposal = revision.proposal || {};
    const item = document.createElement("div");
    item.className = "item";
    item.append(
      textElement(
        "span",
        "item-title",
        `${revision.created_at_utc || "Unknown"} · ${proposal.claim || revision.receipt_id}`,
      ),
    );
    item.append(textElement("span", "item-meta", `Receipt: ${revision.receipt_ref}`));
    if (revision.content_hash) {
      item.append(textElement("span", "item-meta", `Hash: ${revision.content_hash.slice(0, 12)}`));
    }
    if (revision.supersedes) {
      item.append(textElement("span", "item-meta", `Supersedes: ${revision.supersedes}`));
    }
    item.append(textElement("span", "tag", `execution_allowed=${revision.execution_allowed}`));
    parent.append(item);
  }
}

async function renderProposalDetail() {
  clear(selectors.proposalDetail);
  if (!state.selectedProposalId) {
    selectors.proposalDetail.append(emptyNode());
    return;
  }
  const [detail, revisionHistory] = await Promise.all([
    apiGet(`/proposals/${state.selectedProposalId}`),
    apiGet(`/proposals/${state.selectedProposalId}/revisions`),
  ]);
  renderRows(selectors.proposalDetail, [
    ["ID", detail.proposal.proposal_id],
    ["Kind", detail.proposal.kind],
    ["Claim", detail.proposal.claim],
    ["Open", detail.open_for_review],
    ["Execution allowed", detail.execution_allowed],
    ["Receipt", detail.proposal.receipt_ref],
  ]);
  renderCandidateDetail(selectors.proposalDetail, detail.proposal);
  renderRevisionHistory(selectors.proposalDetail, revisionHistory);
  renderNonClaims(selectors.proposalDetail, detail.non_claims);
  selectors.proposalDetail.append(textElement("h4", "", "Attestations"));
  renderAttestations(selectors.proposalDetail, detail.attestations);
  renderAttestationForm(selectors.proposalDetail, detail.proposal.proposal_id);
}

async function renderProposals() {
  const proposals = await fetchProposals();
  renderProposalList(proposals);
  await renderProposalDetail();
}

function percent(value) {
  if (typeof value !== "number") {
    return "Unknown";
  }
  return `${(value * 100).toFixed(1)}%`;
}

async function renderExposure() {
  const exposure = await apiGet("/exposure");

  clear(selectors.exposureGrid);
  selectors.exposureGrid.append(
    metric("Net Worth", formatMoney(exposure.net_worth)),
    metric("Assets", formatMoney(exposure.total_assets)),
    metric("Liabilities", formatMoney(exposure.total_liabilities)),
    metric("Cash", formatMoney(exposure.cash_total)),
    metric(
      "Cash Runway",
      exposure.cash_runway_months === null
        ? "Unknown"
        : `${exposure.cash_runway_months.toFixed(1)} mo`,
    ),
    metric("Top Holding", percent(exposure.top_holding_weight)),
    metric("Concentration (HHI)", exposure.concentration_hhi.toFixed(3)),
    metric("Interest-Bearing Debt", formatMoney(exposure.interest_bearing_debt_total)),
    metric("Avg Rate", percent(exposure.weighted_avg_interest_rate)),
    metric("Annual Interest", formatMoney(exposure.annual_interest_estimate)),
  );

  const holdingRows = exposure.holdings.map((holding) => [
    holding.symbol,
    `${formatMoney(holding.market_value)} (${percent(holding.weight)})`,
  ]);
  renderRows(selectors.exposureHoldings, holdingRows);
  if (exposure.concentration_flagged) {
    selectors.exposureHoldings.append(
      textElement(
        "p",
        "tag",
        `Top holding crosses ${percent(exposure.concentration_threshold)} concentration flag`,
      ),
    );
  }
  renderNonClaims(selectors.exposureHoldings, exposure.non_claims);

  clear(selectors.exposureObligations);
  if (!exposure.upcoming_obligations.length) {
    selectors.exposureObligations.append(emptyNode());
  } else {
    for (const obligation of exposure.upcoming_obligations) {
      const item = document.createElement("div");
      item.className = "item";
      item.append(textElement("span", "item-title", `${obligation.due_date} · ${obligation.label}`));
      const money =
        obligation.amount === null
          ? ""
          : ` · ${formatMoney(obligation.amount)} ${obligation.currency || ""}`.trimEnd();
      item.append(textElement("span", "item-meta", `${obligation.kind}${money}`));
      selectors.exposureObligations.append(item);
    }
  }

  clear(selectors.exposureGaps);
  if (!exposure.data_gaps.length) {
    selectors.exposureGaps.append(textElement("p", "empty-state", "No data gaps."));
  } else {
    for (const gap of exposure.data_gaps) {
      selectors.exposureGaps.append(textElement("p", "data-row", gap));
    }
  }
}

async function renderTimeline() {
  const entries = await apiGet("/timeline");
  clear(selectors.timelineList);
  if (!entries.length) {
    selectors.timelineList.append(emptyNode());
    return;
  }
  for (const entry of entries) {
    const item = document.createElement("div");
    item.className = "item";
    item.append(textElement("span", "item-title", entry.summary));
    item.append(textElement("span", "item-meta", `${entry.event_type} / ${entry.created_at_utc}`));
    item.append(textElement("span", "tag", `execution_allowed=${entry.execution_allowed}`));
    selectors.timelineList.append(item);
  }
}

const renderers = {
  overview: renderOverview,
  exposure: renderExposure,
  proposals: renderProposals,
  timeline: renderTimeline,
};

const errorTargets = {
  overview: () => selectors.latestBrief,
  exposure: () => selectors.exposureGrid,
  proposals: () => selectors.proposalDetail,
  timeline: () => selectors.timelineList,
};

async function refresh() {
  setStatus("Syncing");
  selectors.boundaryLine.textContent = "execution_allowed=false";
  try {
    await (renderers[state.activeView] || renderOverview)();
    setStatus("Synced", "ok");
  } catch (error) {
    setStatus("API error", "error");
    const target = (errorTargets[state.activeView] || errorTargets.overview)();
    clear(target);
    target.append(textElement("p", "error-text", error.message));
  }
}

selectors.tabs.forEach((tab) => {
  tab.addEventListener("click", () => activate(tab.dataset.view));
});

selectors.refresh.addEventListener("click", refresh);
selectors.proposalFilter.addEventListener("change", (event) => {
  state.proposalFilter = event.target.value;
  state.selectedProposalId = null;
  renderProposals().catch((error) => {
    setStatus("API error", "error");
    selectors.proposalDetail.replaceChildren(textElement("p", "error-text", error.message));
  });
});

refresh();
