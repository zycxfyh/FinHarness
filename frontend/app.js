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
    retrospective: document.querySelector("#retrospective-view"),
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
  retrospectiveBlock: document.querySelector("#retrospective-block"),
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

// Read-only Retrospective panel: latest annual_review summary (closure taken from the
// receipt) + rule-change drill-down + data gaps. Unclosed lessons are shown as neutral
// disclosure, never a recommendation; the panel has no action affordances.
function renderRetrospectivePanel(parent, data) {
  const retro = data && data.retrospective ? data.retrospective : null;
  const ruleChanges = data && Array.isArray(data.rule_changes) ? data.rule_changes : [];
  const gaps = data && Array.isArray(data.data_gaps) ? data.data_gaps : [];
  if (!retro) {
    parent.append(
      textElement("p", "empty-state", "No annual review yet. Run `task review:annual`."),
    );
  } else {
    renderRows(parent, [
      ["Period", retro.period_label],
      ["Lessons closed", retro.lessons_closed],
      ["Lessons open", Array.isArray(retro.lessons_open) ? retro.lessons_open.length : 0],
      [
        "Untraceable rule changes",
        Array.isArray(retro.untraceable_rule_changes) ? retro.untraceable_rule_changes.length : 0,
      ],
      ["Source receipt", (data && data.retrospective_receipt_ref) || "—"],
    ]);
    if (Array.isArray(retro.lessons_open) && retro.lessons_open.length) {
      parent.append(textElement("h4", "", "Unclosed lessons (disclosure)"));
      for (const lesson of retro.lessons_open) {
        parent.append(textElement("p", "item-meta", String(lesson)));
      }
    }
  }
  if (ruleChanges.length) {
    parent.append(textElement("h4", "", "Rule changes"));
    for (const change of ruleChanges) {
      parent.append(
        textElement(
          "p",
          "item-meta",
          `${change.rule_target} [${change.status}] ${
            change.traceable ? "traceable" : "untraceable"
          } by ${change.attester}`,
        ),
      );
    }
  }
  if (gaps.length) {
    renderTextList(parent, "Data gaps", gaps);
  }
  // Mandatory disclosure (never collapsed).
  renderNonClaims(parent, data && data.non_claims);
}

async function renderRetrospective() {
  clear(selectors.retrospectiveBlock);
  const data = await apiGet("/review/retrospective");
  renderRetrospectivePanel(selectors.retrospectiveBlock, data);
}

// Read-only merged review timeline (attestations + review events). The server already
// orders newest-first deterministically; this just renders, with no action affordances.
function renderReviewTimeline(parent, timeline) {
  const entries = timeline && Array.isArray(timeline.entries) ? timeline.entries : [];
  parent.append(textElement("h4", "", "Review timeline"));
  if (timeline && timeline.is_archived) {
    parent.append(textElement("span", "data-badge", "archived"));
  }
  if (!entries.length) {
    parent.append(textElement("p", "empty-state", "No review activity recorded."));
    return;
  }
  for (const entry of entries) {
    const item = document.createElement("div");
    item.className = "item review-timeline-entry";
    item.append(
      textElement("span", "item-title", `[${entry.source_type}] ${entry.kind} by ${entry.attester}`),
    );
    item.append(textElement("span", "item-meta", entry.created_at_utc));
    if (entry.reason) {
      item.append(textElement("p", "item-meta", entry.reason));
    }
    parent.append(item);
  }
}

// Human write affordance: annotation / archive / reopen. State-changing, so it requires
// an explicit confirm before any POST — rendering alone never writes.
function renderReviewEventForm(parent, proposalId) {
  const form = document.createElement("form");
  form.className = "review-event-form";
  form.innerHTML = `
    <div class="form-row">
      <label for="review-kind">Action</label>
      <select id="review-kind" name="kind">
        <option value="annotation">annotation</option>
        <option value="archive">archive</option>
        <option value="reopen">reopen</option>
      </select>
    </div>
    <div class="form-row">
      <label for="review-attester">Reviewer</label>
      <input id="review-attester" name="attester" autocomplete="name" />
    </div>
    <div class="form-row">
      <label for="review-reason">Reason</label>
      <textarea id="review-reason" name="reason"></textarea>
    </div>
    <div class="form-row">
      <label for="review-text">Note (optional)</label>
      <textarea id="review-text" name="text"></textarea>
    </div>
    <button class="submit-button" type="submit">Record Review Action</button>
  `;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const kind = data.get("kind");
    if (!window.confirm(`Record review action "${kind}"? It is logged with your name and reason.`)) {
      return; // explicit confirm required; no write on cancel
    }
    try {
      await apiPost(`/proposals/${proposalId}/review-events`, {
        kind,
        attester: data.get("attester"),
        reason: data.get("reason"),
        text: data.get("text") || null,
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

const STRUCTURAL_EVIDENCE_KEYS = new Set([
  "options",
  "key_risks",
  "reversibility",
  "dimension",
  "research_evidence",
  "research_evidence_gaps",
]);

// Whitelisted descriptive statistics for the research-evidence block. Only these keys
// render; anything else in value is ignored so the read-only block cannot quietly widen
// into advice-shaped fields.
const RESEARCH_VALUE_KEYS = [
  "realized_volatility",
  "max_drawdown",
  "conditional_var",
  "average_volume",
];

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
  renderResearchEvidence(parent, evidence);
}

// Read-only render of attached historical research evidence. Descriptive only: grade and
// disclaimers (limitations + non_claims) are always shown next to the claim, value is
// limited to the whitelisted stats, and the block carries no action affordances.
function renderResearchEvidence(parent, evidence) {
  const items = Array.isArray(evidence.research_evidence) ? evidence.research_evidence : [];
  const gaps = Array.isArray(evidence.research_evidence_gaps)
    ? evidence.research_evidence_gaps
    : [];
  if (!items.length && !gaps.length) {
    return; // default no-op path attaches nothing to render
  }
  parent.append(textElement("h4", "", "Research evidence (historical, descriptive)"));
  for (const item of items) {
    const card = document.createElement("div");
    card.className = "item research-evidence";
    // Fail-closed: the cockpit is the last anti-misread surface. A risk claim/value must
    // never render without its mandatory disclosure (grade + non_claims) co-located, so
    // a malformed/legacy/hand-made item is omitted with a safe notice instead of leaking
    // an undisclosed claim. The normal RE1/RE2 path always supplies both.
    const nonClaims = Array.isArray(item.non_claims) ? item.non_claims : [];
    if (!item.evidence_grade || !nonClaims.length) {
      card.append(
        textElement(
          "p",
          "item-meta",
          "Research evidence item omitted because mandatory disclosure is missing.",
        ),
      );
      parent.append(card);
      continue;
    }
    // Grade badge sits with the claim so the descriptive framing cannot be detached.
    card.append(textElement("span", "data-badge", item.evidence_grade));
    if (item.claim) {
      card.append(textElement("p", "item-title", item.claim));
    }
    if (item.time_window) {
      card.append(textElement("span", "item-meta", `Window: ${item.time_window}`));
    }
    const value = item.value && typeof item.value === "object" ? item.value : {};
    for (const key of RESEARCH_VALUE_KEYS) {
      if (key in value) {
        const row = document.createElement("div");
        row.className = "data-row";
        row.append(textElement("span", "data-key", key));
        row.append(textElement("span", "data-value", formatValue(value[key])));
        card.append(row);
      }
    }
    // Disclaimers are mandatory and never collapsed.
    renderTextList(card, "Limitations", item.limitations);
    renderTextList(card, "Not claimed", item.non_claims);
    if (Array.isArray(item.source_refs) && item.source_refs.length) {
      card.append(textElement("p", "item-meta", `Sources: ${item.source_refs.join(", ")}`));
    }
    parent.append(card);
  }
  if (gaps.length) {
    renderTextList(parent, "Data gaps", gaps);
  }
}

function shortenValue(value) {
  if (value === null || value === undefined) {
    return "∅";
  }
  if (typeof value === "object") {
    return Array.isArray(value) ? `[${value.length} items]` : "{…}";
  }
  const text = String(value);
  return text.length > 40 ? `${text.slice(0, 37)}…` : text;
}

// Read-only diff of one revision against the next-older one (its supersedes
// target). Surfaces why a candidate changed, not just that it changed.
function describeRevisionChanges(current, previous) {
  const changes = [];
  const now = current.proposal || {};
  const before = previous.proposal || {};
  if (now.claim !== before.claim) {
    changes.push(`claim: "${before.claim ?? ""}" → "${now.claim ?? ""}"`);
  }
  for (const field of ["evidence", "assumptions", "limitations"]) {
    const nowField = now[field] || {};
    const beforeField = before[field] || {};
    const keys = new Set([...Object.keys(nowField), ...Object.keys(beforeField)]);
    for (const key of [...keys].sort()) {
      if (JSON.stringify(nowField[key]) !== JSON.stringify(beforeField[key])) {
        changes.push(
          `${field}.${key}: ${shortenValue(beforeField[key])} → ${shortenValue(nowField[key])}`,
        );
      }
    }
  }
  return changes;
}

function renderRevisionHistory(parent, revisionHistory) {
  const revisions =
    revisionHistory && Array.isArray(revisionHistory.revisions) ? revisionHistory.revisions : [];
  parent.append(textElement("h4", "", "Revisions"));
  if (!revisions.length) {
    parent.append(textElement("p", "empty-state", "No revisions recorded."));
    return;
  }
  revisions.forEach((revision, index) => {
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

    // Revisions are latest-first, so the previous version is the next entry.
    const previous = revisions[index + 1];
    if (!previous) {
      item.append(textElement("span", "item-meta", "Initial version"));
    } else {
      const changes = describeRevisionChanges(revision, previous);
      if (!changes.length) {
        item.append(textElement("span", "item-meta", "No field changes from previous version"));
      } else {
        item.append(textElement("span", "item-meta", "Changes from previous:"));
        const list = document.createElement("ul");
        list.className = "revision-changes";
        for (const change of changes) {
          const entry = document.createElement("li");
          entry.textContent = change;
          list.append(entry);
        }
        item.append(list);
      }
    }
    parent.append(item);
  });
}

async function renderProposalDetail() {
  clear(selectors.proposalDetail);
  if (!state.selectedProposalId) {
    selectors.proposalDetail.append(emptyNode());
    return;
  }
  const [detail, revisionHistory, timeline] = await Promise.all([
    apiGet(`/proposals/${state.selectedProposalId}`),
    apiGet(`/proposals/${state.selectedProposalId}/revisions`),
    apiGet(`/proposals/${state.selectedProposalId}/timeline`),
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
  renderReviewTimeline(selectors.proposalDetail, timeline);
  renderReviewEventForm(selectors.proposalDetail, detail.proposal.proposal_id);
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
  retrospective: renderRetrospective,
};

const errorTargets = {
  overview: () => selectors.latestBrief,
  exposure: () => selectors.exposureGrid,
  proposals: () => selectors.proposalDetail,
  timeline: () => selectors.timelineList,
  retrospective: () => selectors.retrospectiveBlock,
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
