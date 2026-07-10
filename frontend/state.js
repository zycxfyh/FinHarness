// FinHarness Cockpit — shared runtime state.
"use strict";

window.FinHarness = window.FinHarness || {};
window.FinHarness.state = Object.seal({
  activeView: "overview",
  selectedProposalId: null,
  proposalFilter: "all",
});
