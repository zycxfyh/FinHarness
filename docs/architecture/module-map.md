# FinHarness Module Map

This page is the generated runtime-root projection of
[`system-catalog.yml`](system-catalog.yml). It is not a roadmap, planned-layer
list, command inventory, product completion claim, or changelog.

For current capability and boundaries, read
[FinHarness Current System](../current-system.md). For live commands use
`Taskfile.yml` and `task --list`. For current work authorization and sequence use
GitHub Issue/PR state and labels.

The **Canonical plane model** vocabulary—**Truth**, **Knowledge**,
**Judgment**, **Control**, **Agent**, **Action/Learning**, **Product**, and
**Assurance**—is owned by the architecture layer matrix and its ADR. This
generated runtime projection does not redefine or sequence those planes.

## Mainline Modules

<!-- BEGIN GENERATED: system-catalog -->
> Generated from `docs/architecture/system-catalog.yml`. Do not edit this section; run `task docs:generate-current-views`.

| System | Lifecycle | Runtime roots | Ownership note |
| --- | --- | --- | --- |
| Shared Artifact and Receipt Store | `current` | `src/finharness/artifact_store.py`<br>`src/finharness/import_provenance.py`<br>`src/finharness/statecore/receipt_io.py` | Domain services own semantics and authority; the store owns durability and integrity. Descriptors and bytes are truth, while indexes are reconstructable. |
| Product North Star | `current` | `README.md`<br>`docs/current-system.md`<br>`docs/product/` | Keep current capability separate from product direction; direction never authorizes work or proves shipped behavior. |
| State Core | `current` | `src/finharness/statecore/`<br>`src/finharness/capital_import_contract.py`<br>`src/finharness/statecore/identities.py`<br>`src/finharness/position_valuation.py`<br>`src/finharness/personal_finance.py`<br>`src/finharness/beancount_adapter.py`<br>`src/finharness/api/routes_state.py` | Borrow event/receipt-sourcing ideas without adopting a heavy event platform. |
| Capital Map | `current` | `src/finharness/exposure.py`<br>`src/finharness/daily_brief.py`<br>`src/finharness/daily_change_brief.py` | BI/read-model pattern; FinHarness mirrors state and does not replace the ledger. |
| IPS / Policy / Authority Credentials | `current` | `src/finharness/ips.py`<br>`src/finharness/api/routes_ips.py`<br>`src/finharness/authority_administration.py`<br>`src/finharness/statecore/capital_mandates.py`<br>`src/finharness/api/routes_capital_mandates.py`<br>`src/finharness/statecore/agent_authority_grants.py`<br>`src/finharness/api/routes_agent_authority_grants.py` | IdentityProvider assertions feed one closed domain-owned human-administration guard; they do not become capital authority by authentication alone. CapitalMandate versions and lifecycle events remain immutable principal-bound inputs. AgentAuthorityGrant stays exact-version/currency/scope bound, while Agent-runtime consumption remains separate from human administration and never grants execution authority. |
| Decision Workflow | `current` | `src/finharness/allocation.py`<br>`src/finharness/statecore/decision_scaffold.py`<br>`src/finharness/statecore/risk_classification.py` | RFC and decision-record style; human review remains authority. |
| Review System | `current` | `src/finharness/statecore/proposals.py`<br>`src/finharness/review_read.py`<br>`src/finharness/risk_register.py`<br>`src/finharness/lesson_loop.py`<br>`src/finharness/rule_change_ledger.py` | Decision log plus risk/issue register discipline; attestation and risk severity hints are review evidence, not execution. |
| Execution Kernel | `canonical` | `src/finharness/statecore/execution_models.py`<br>`src/finharness/execution/`<br>`src/finharness/api/routes_execution.py` | Classical execution kernel with receipt-backed services, service-enforced immutable capabilities, and an adapter protocol; only simulated submission is enabled and real external execution remains absent. |
| Research Evidence | `current` | `src/finharness/research_evidence.py`<br>`src/finharness/research_assets.py`<br>`src/finharness/research_enrichment.py` | Mature finance wheels provide calculations; FinHarness owns claims, redlines, and receipts. |
| External Data / Mature Wheels | `thin` | `src/finharness/data_entry.py`<br>`src/finharness/market_data.py`<br>`src/finharness/providers/`<br>`src/finharness/portfolio_risk.py`<br>`src/finharness/data_quality.py` | Adopt-not-invent; use mature wheels for heavy calculation and scanning. |
| Agent Explanation | `current` | `src/finharness/agent_capabilities.py`<br>`src/finharness/agent_context.py`<br>`src/finharness/agent_context_projection.py`<br>`src/finharness/agent_evidence.py`<br>`src/finharness/agent_runtime.py`<br>`src/finharness/agent_tool_entries.py`<br>`src/finharness/agent_tools.py`<br>`src/finharness/scaffold_candidate_preflight.py`<br>`src/finharness/review_read.py`<br>`src/finharness/proposal_queue_checks.py`<br>`src/finharness/hermes_bridge.py` | Hermes-style spec, availability, dispatch wrapper, output-budget, toolset registry, and capability-profile ideas; ToolEntry availability and profiles are diagnostics/visibility, not permission bypasses. |
| Agent Cognition Runtime / Work Orchestrator | `current` | `src/finharness/agent_shell.py`<br>`src/finharness/api/routes_agent_shell.py`<br>`scripts/serve_local_agent.py`<br>`frontend-agent/`<br>`src/finharness/capital_agent.py`<br>`src/finharness/capital_runtime.py`<br>`src/finharness/runtime_worker.py`<br>`crates/finharness-runtime/`<br>`src/finharness/agent_cognition_flow.py`<br>`src/finharness/agent_run_receipts.py`<br>`src/finharness/agent_runtime_receipts.py`<br>`src/finharness/agent_tool_registry.py`<br>`src/finharness/agent_tool_availability.py`<br>`src/finharness/agent_tool_result_envelope.py`<br>`src/finharness/agent_context_trust_map.py`<br>`src/finharness/agent_receipt_search.py`<br>`src/finharness/domain_memory.py`<br>`src/finharness/playbook_loader.py`<br>`src/finharness/evaluator_registry.py`<br>`src/finharness/agent_operating_flow.py`<br>`src/finharness/review_workspace.py`<br>`src/finharness/agent_work_loop.py` | Python owns capital and Agent semantics; the local Agent Shell only orchestrates authenticated product journeys. The transplanted Rust kernel owns execution identity, idempotency, process lifecycle, bounded Artifacts, and recovery. Paper Effects create an identity-bound pending domain receipt before Runtime dispatch and complete it after reconciliation; if domain-receipt completion or outer acknowledgement is lost, typed reconciliation observes the same Runtime Job and reconstructs the response from complete Runtime and StateCore truth without redispatch. Registered operations prevent model-selected executables or environment, browser sessions never receive provider secrets, and broker/capital reconciliation remain domain-owned. |
| Agent Autonomy Control Plane | `current` | `src/finharness/autonomy_control.py`<br>`src/finharness/agent_autonomy_adapter.py`<br>`src/finharness/agent_work_loop.py` | Keep admission local, typed, deterministic, and provider-neutral. Consider an external policy engine only after rule volume or multi-runtime consistency creates measured pressure. |
| Cockpit / API | `current` | `src/finharness/api/`<br>`frontend/` | Thin adapter and view-contract discipline; avoid heavy frontend framework until needed. |
| Engineering Assurance | `thin` | `.github`<br>`data/security`<br>`src/finharness/hardening.py`<br>`src/finharness/repo_intelligence.py`<br>`scripts/check_architecture_boundaries.py`<br>`scripts/check_keyed_mutation_route_capabilities.py`<br>`scripts/run_fuzz_baseline.py` | Use direct executable evidence and retain hard blockers only for non-recoverable consequences. |
<!-- END GENERATED: system-catalog -->

## Maintenance Contract

Change the generated section only through `system-catalog.yml` and
`task docs:generate-current-views`. Explanations and historical reasoning belong
in the owning current document or frozen historical evidence, not in this file.
