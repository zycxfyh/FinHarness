# Interface Reference

This reference lists the major current FinHarness interfaces, the external or
mature-wheel owner of heavy work, and the local boundary FinHarness keeps.

Use this as a lookup page. For system ownership, read
[System Map](../architecture/system-map.md). For layering, read
[Capital OS Layering](../architecture/capital-os-layering.md).

## Interface Table

| Interface | External / mature owner | Local FinHarness owner | Primary docs/tasks |
| --- | --- | --- | --- |
| PersonalCapitalImportInterface | Beancount / `bean-query`, user-generated FinHarness CSV | Read-only mirror into State Core, source refs, reconciliation-by-source | `task beancount:import`, `task personal-finance:import` |
| StateCoreInterface | SQLite / SQLModel | Queryable mirror, DecimalText money, receipt index, atomic writes | `statecore/`, [Receipt Reference](receipts.md) |
| CapitalMapInterface | Local deterministic views | Net worth, cash runway, concentration, liabilities, obligations, data gaps | `exposure.py`, `task brief:daily` |
| IPSInterface | User policy | Receipt-backed Investment Policy Statement, threshold mapping, compliance check | `ips.py`, `/ips/current`, `/ips/check` |
| CapitalMandateInterface | Human-attested user policy domain | Principal-owned immutable versions and append-only lifecycle evidence; deterministic principal-bound current resolution; human-only server-asserted administration with elevated create/replace/resume and standard immediate server-timed suspend/revoke; `CapitalMandate.status` remains a compatibility mirror and the mandate never authorizes execution | `authority_administration.py`, `statecore/capital_mandates.py`, `/capital-mandates`, `/capital-mandates/current` |
| AgentAuthorityGrantInterface | Mandate-bound authority credential | Human-only server-asserted create/revoke administration with server-timed atomic revocation; principal/runtime/exact-mandate-version binding; closed exact-money and mandate-bounded scope; atomic Agent-runtime consumption remains separate from administration; never approves, bypasses preflight, submits orders, or authorizes execution | `authority_administration.py`, `statecore/agent_authority_grants.py`, `/agent-authority-grants`, `/agent-authority-grants/{grant_id}/validate`, `/consume`, `/revoke` |
| ActionIntentAuthorityBindingInterface | Authority admission control | Receipt-backed admission result for agent/human/system-authored ActionIntentCandidates; agent-authored intents must cite a valid AgentAuthorityGrant and preserve structured deny reasons; allowed means admission to downstream checks only | `statecore/action_intent_authority_bindings.py`, `/action-intents/{action_intent_id}/authority-bindings`, `/action-intent-authority-bindings/{binding_id}` |
| ProposalInterface | Local governed commands | Proposal creation, decision scaffold revision, high-risk confirmation gate, receipts | `task decisions:scan`, `statecore/proposals.py` |
| ReviewInterface | Local governed commands + deterministic read models | Attestation, scaffold revision, annotation, archive/reopen, compare marks, annual review, and proposal review queue triage; governed HTTP writes derive the actor from `OperatorContext`, never request prose | `/review/queue`, `task review:annual`, `review_read.py` |
| ApiMutationIdentityInterface | FastAPI + authenticated identity provider | Optional `Idempotency-Key` claim bound to actor, canonical target/query, semantic headers, and body hash; 1 MiB request/response limits; durable locked CAS terminal transitions; exact replay; typed domain-truth reconciliation | `identity.py`, `task identity:reconcile`, [Durable write mini-RFC](../proposals/2026-07-13-durable-write-and-api-mutation-semantics.md) |
| RiskRegisterInterface | Local deterministic read model | Derived risk register view over review queue signals; no risk acceptance, scoring, scenario generation, or writes | `/risk/register`, `risk_register.py` |
| ResearchEvidenceInterface | yfinance/mature data adapters where enabled | Historical/descriptive evidence, source grades, data gaps, no prediction | `research_evidence.py`, `task decisions:research-smoke` |
| AgentToolInterface | OpenAI Agents SDK, local Hermes bridge | Profile-selected Agent tools resolved through `AgentToolEntry`, profile-aware context projection, evidence provider registry, and the runtime pipeline; default profile is read-only baseline; review-draft profile can create append-only governed proposal drafts; review-note profile can create append-only `AgentReviewNoteDraft` artifacts on existing proposals; scaffold-candidate profile can create append-only `AgentScaffoldRevisionApplyCandidate` artifacts from risk register items; system preflight recomputes candidate readiness before human-confirmed apply; stronger permissions graduate through explicit runtime contracts and governance carriers | `agent_context.py`, `agent_context_projection.py`, `agent_capabilities.py`, `agent_evidence.py`, `agent_tools.py`, `agent_runtime.py`, `scaffold_candidate_preflight.py`, `proposal_queue_checks.py`, `review_read.py`, `task agent:describe`, `task agent:run` |
| AgentReceiptSearchInterface | Local immutable checkpoints and update segments | Bounded per-run index updates, atomic generation commits, source high-water metadata, and fail-closed completeness/freshness diagnostics; full scans are recovery/audit operations | `agent_receipt_search.py`, `tests/test_agent_receipt_search.py` |
| ExecutionKernelInterface | SQLModel + local SimulatedBrokerAdapter | Canonical draft/check/approval/stage/simulated-submit lifecycle; immutable capabilities are enforced before service effects; no live adapter, network, credential, or funded-account path | `execution/services.py`, `execution/commands.py`, `/execution/*` |
| CockpitInterface | FastAPI + static frontend | Exposure, IPS, proposals, review, legacy paper compatibility, and Execution Kernel views/routes; governed review writes persist one logical mutation attempt before fetch, reuse its stable key across response loss/reload, and clear it only after terminal boundary validation; execution mutations still require deployment capability | `task api:serve`, `frontend/api.js`, `frontend/actions.js` |
| SecurityScanInterface | pip-audit, gitleaks, Trivy, uv | Scanner aggregation, redaction, fail-closed missing/timeout result | `task security:audit`, `task security:scan` |
| EvidenceInterface | Possible future OpenLineage/MLflow/DVC/Sigstore adapter | Receipt schema, claim boundaries, non-claims, review hooks | [Receipt Reference](receipts.md), [Evidence Inventory](../architecture/evidence-inventory.md) |

The [Capital Decision Agent Harness ownership ADR](../adr/2026-07-16-capital-decision-agent-harness-boundary.md)
defines `AgentWorkDecisionPort` as the single future provider selection point.
It accepts one next-action decision, not a nested SDK Runner: every candidate
tool call returns to the Harness reducer for autonomy/tool admission, budgets,
and Observation reduction. Provider state is non-authoritative but remains
durable while pause/resume obligations exist. MCP transport OAuth is distinct
from FinHarness Principal, mandate, grant, admission, and execution authority.
The ADR does not select a provider or add a runtime dependency.

## Common Interface Rules

- Mature wheels can compute or retrieve evidence; they do not grant authority.
- FinHarness records source, quality, lineage, receipt, and authority boundary.
- Every suggestion/proposal needs evidence, assumptions, limitations, non-claims,
  and `execution_allowed=false`.
- Human attestation is review evidence, not execution authorization.
- CapitalMandate is a policy-domain carrier future authority objects may cite.
  Its domain command derives `human_attester` from a current server-asserted
  human authority administrator; Agent runtimes, services, ordinary humans,
  and legacy local labels cannot administer it. The request supplies
  `human_reason` and `explicit_confirmation=true`;
  it still has `execution_allowed=false` and `authority_transition=false`, and
  it is not an Agent identity grant, AuthorityContract, order ticket, broker
  instruction, or execution authorization.
- A `capital_mandate_id` is permanently bound to the durable
  `CapitalMandateVersion.principal_id`. Reuse by another principal is rejected
  before any receipt or domain mutation. Currentness is resolved only by
  `resolve_capital_mandate(principal_id, at_utc)` using descending
  `(effective_at_utc, created_at_utc, version_number, capital_mandate_id,
  mandate_version_id)`. The final lexical identifiers make ties stable; they do
  not express economic or permission priority. Lifecycle ties use descending
  `(effective_at_utc, created_at_utc, mandate_lifecycle_event_id)`.
- `CapitalMandate.status` and the legacy global `current_capital_mandate()`
  helper are non-authoritative compatibility views. Historical unowned rows
  remain readable, but free-text labels cannot be promoted into verified owner
  identity. A historical mandate ID with multiple durable version owners is
  invalid for every principal: resolution returns no version, grant validation
  and creation return `mandate_series_owner_conflict`, and lifecycle writes fail
  before evidence or domain mutation. HTTP grant creation exposes the conflict
  as a typed 422 rather than an unhandled CapitalMandate exception.
- AgentAuthorityGrant is a mandate-bound authority credential, not authentication
  or execution permission. It must reference an active CapitalMandate at creation
  time, bind the authenticated principal and agent runtime to an exact mandate
  version, and re-check the same principal exact current version, lifecycle,
  closed typed mandate limit book, effective per-use cap, persisted grant
  currency/caps, scope, usage, and nonce at use time. A grant that omits a
  per-use cap inherits the exact mandate cap. A new current version under either the
  same or another mandate ID yields `mandate_version_changed`; another
  principal cannot cause that drift. Only
  atomic consumption spends capacity; validation never does.
  Its validator returns closed deny reasons such as `capital_mandate_not_active`,
  `requested_scope_exceeds_grant`, and forbidden execution/approval/broker/
  preflight-bypass semantics. It does not approve trade plans, bypass preflight,
  submit orders, create broker authority, or authorize execution.
- ActionIntentAuthorityBinding is the authority admission layer for capital
  action intents. `POST /action-intents/{action_intent_id}/authority-bindings`
  records whether an `agent`, `human`, or `system` author may admit the intent
  into downstream capital-action checks. Agent-authored intents must reference
  `agent_authority_grant_id`; the server validates that grant at use time and
  preserves grant deny reasons separately from binding deny reasons. Human
  intents may omit grants, and system intents may omit grants only when a source
  rule is recorded. Binding `allowed=true` is only admission into downstream
  checks; it is not preflight, trade-plan approval, order-ticket creation,
  broker submission, preflight bypass, authentication, AuthorityContract, or
  execution authorization.
- Archived live-trading code is not a current interface.
- Agent capability profiles are explicit product postures resolved through a
  runtime `AgentToolEntry` registry/factory, not permission bypasses; Agent tool
  metadata exposes capability, toolset, side-effect, availability, evidence
  provider ids, profile-aware context projection, and authority-boundary claims.
  The Agent runtime pipeline resolves visible/hidden/unavailable tools and
  normalizes dispatch results/errors plus evidence envelopes without creating
  approval, recommendations, or execution authorization by implication. New
  Agent permissions should be opened through explicit profiles, tool entries,
  context projection policies, evidence providers, review/approval contracts,
  and tests rather than by broad prompt language. Agent-created proposal drafts
  are review objects.
- Agent-created proposal drafts expose review provenance (`created_by=agent`,
  active profile, context/source refs, receipt ref, and human-review state) in
  proposal review responses.
- Agent-created review notes are typed append-only review artifacts on proposal
  timelines. They may surface findings, risks, open questions, evidence refs,
  source refs, context-pack refs, and data gaps; they are not approval,
  attestation, scaffold revision, rejection, recommendation, or execution
  authorization.
- Agent-created proposal drafts expose read-only queue checks (`pass`/`warn`/`block`,
  block codes, blocked transition scope, recovery hints, source refs, receipt
  refs) without granting approval, attestation, or execution authority. A
  `human_review_required` block means the draft must move through human review;
  it is not a reason to keep the draft out of the review queue.
- Proposal review tasks and evidence requests are read-only projections derived
  from proposals, attestations, review events, and queue checks. They are not a
  separate mutable Kanban board and do not create approval or execution authority.
- Review queue triage is a deterministic read model derived from proposals,
  attestations, archived state, review events, AgentReviewNoteDraft payloads,
  receipt index rows, and proposal queue checks. It prioritizes human review
  work and next actions; it is not approval, rejection, attestation, execution
  authorization, or investment advice.
- Risk register v0 is a deterministic read model derived from review queue
  signals. It turns data gaps, stale context, duplicate candidates, policy
  mismatches, counter-evidence needs, Agent-reported risks, and open questions
  into comparable risk objects; it is not a persistent risk table, risk
  acceptance workflow, scoring model, scenario generator, approval, execution
  authorization, or investment advice.
- Agent-created scaffold revision apply candidates are typed append-only review
  artifacts derived from existing risk register items. They carry
  `scaffold_patch`, `proposed_scaffold`, `changed_fields`, preflight/rollback
  context, risk coverage, and human confirmation requirements, but they do not
  mutate proposals. Their preflight, risk coverage, and rollback fields are
  Agent-supplied candidate payload until a later system preflight recomputes
  them. Applying the patch requires a later human-confirmed flow.
- Human-confirmed scaffold candidate apply is a review-state transition:
  `POST /scaffold-revision-candidates/{candidate_id}/apply` derives its actor
  from the server-authenticated `OperatorContext` and requires a written reason,
  expected candidate receipt, expected proposal receipt,
  expected system preflight report hash, and `explicit_confirmation=true`.
  The server recomputes preflight at apply time, rejects mismatched hashes,
  hard-blocks blocking findings, and only allows warning findings when the human
  explicitly acknowledges all warning codes. Successful apply writes a normal
  proposal revision receipt linked back to the candidate and preflight evidence.
  It is not Agent auto-apply, approval, attestation, or execution authorization.
- Action intent candidates are the first capital-action bridge:
  `POST /proposals/{proposal_id}/action-intents` creates a receipt-backed
  `ActionIntentCandidate` from the current proposal receipt, and
  `GET /action-intents/{action_intent_id}` retrieves it. The create path requires
  expected proposal receipt freshness, source refs, typed action intent, target
  scope, summary, and rationale; it rejects order/broker/execution/authority
  fields. `GET /action-intents/{action_intent_id}/preflight` recomputes whether
  the candidate is fresh, authority-admitted where required, structurally
  complete, IPS-compatible, and ready for its expected next step. Agent-authored
  intents block unless the latest/current `ActionIntentAuthorityBinding` is
  allowed, matches the current action-intent receipt, and preserves grant
  validation evidence. Human/system intents may omit a binding, but if a binding
  exists preflight consumes its allowed/denied state and receipt refs. The
  report returns pass/warn/block findings, `authority_status`, authority binding
  refs, v0 impact summary, risk posture, and a deterministic report hash. The
  object and preflight report are not an order ticket, simulation, approval,
  broker action, or execution authorization.
- Action intent authority bindings are the admission fact between
  AgentAuthorityGrant and downstream action checks:
  `POST /action-intents/{action_intent_id}/authority-bindings` writes
  `state_core_action_intent_authority_binding`, and
  `GET /action-intent-authority-bindings/{binding_id}` retrieves it. v0 stores
  author type/id, requested scope, validated scope, allow/deny result,
  `binding` vs `grant_validation` deny reason sources, linked action intent
  receipt, linked grant/mandate refs when present, and non-claims. Denied
  bindings are persisted so downstream gates can read structured refusal
  evidence instead of reinterpreting AgentAuthorityGrant semantics. Action
  intent preflight consumes the latest binding result rather than revalidating
  grants itself.
- Preflight-bound action intent simulation reports are the first downstream
  consumer of action preflight hashes:
  `POST /action-intents/{action_intent_id}/simulation-reports` requires the
  current action intent receipt ref, current system preflight report hash,
  simulation reason, and explicit acknowledgement of all warning finding codes
  when preflight is warn. The server recomputes preflight at create time,
  rejects stale receipts or hashes, hard-blocks blocking findings, and writes a
  `state_core_action_intent_simulation_report` receipt. `GET
  /action-intent-simulation-reports/{simulation_report_id}` retrieves the
  report. v0 reports are qualitative and descriptive; they do not size trades,
  choose venues, create order tickets, approve actions, or authorize execution.
- Preflight-bound trade plan candidates are pre-trade plan artifacts:
  `POST
  /action-intent-simulation-reports/{simulation_report_id}/trade-plan-candidates`
  requires the current simulation report receipt, current action intent receipt,
  current action preflight hash, plan reason, plan-direction/scope/cap fields,
  and explicit acknowledgement of all current warning finding codes when
  preflight is warn. The server recomputes preflight at create time, rejects
  stale receipts or hashes, rejects simulation reports not bound to the current
  preflight hash, hard-blocks blocking findings, rejects exact quantity and
  broker/order-ready fields in v0, and writes a
  `state_core_trade_plan_candidate` receipt. `GET
  /trade-plan-candidates/{trade_plan_candidate_id}` retrieves the candidate.
  TradePlanCandidate may describe a possible pre-trade plan, but only a future
  AuthorityContract can authorize any execution path or transform it into an
  order ticket.
- Capital objective fits are objective/benefit review evidence over current
  plan evidence: `POST
  /trade-plan-candidates/{trade_plan_candidate_id}/capital-objective-fits`
  requires the current trade plan candidate receipt, current simulation report
  receipt, current action intent receipt, current action preflight hash,
  objective alignment, benefit thesis, impact summaries, alternatives,
  uncertainties, and a recommended next safe path. The server recomputes
  current preflight at create time, rejects stale receipts or hashes, persists a
  `state_core_capital_objective_fit` receipt, and rejects advice/approval/
  suitability/order/broker/execution fields. `GET
  /capital-objective-fits/{capital_objective_fit_id}` retrieves the fit.
  CapitalObjectiveFit helps review whether a candidate appears aligned,
  unclear, or conflicted with user capital objectives; it is not investment
  advice, suitability certification, trade-plan approval, an order ticket,
  broker submission, or execution authorization.
- Trade plan review gates are human review results over current plan evidence:
  `POST /trade-plan-candidates/{trade_plan_candidate_id}/review-gates` requires
  the current trade plan candidate receipt, current simulation report receipt,
  current action intent receipt, current action preflight hash, a human reviewer,
  and an allow/deny decision for order-ticket-candidate staging. The server
  recomputes current preflight at create time, rejects stale receipts or hashes,
  persists allow and deny results as `state_core_trade_plan_review_gate`
  receipts, and rejects broker/order-ready/execution fields. `GET
  /trade-plan-review-gates/{review_gate_id}` retrieves the gate. An allowed
  gate means the candidate may enter future order-ticket-candidate staging; it
  does not create an order ticket, submit to a broker, certify suitability,
  create an AuthorityContract, or authorize execution.
- System scaffold candidate preflight is a read-only recomputation surface:
  `GET /scaffold-revision-candidates/{candidate_id}/preflight` checks the
  candidate payload against current proposal state, current active risk register
  items, scaffold forcing rules, changed fields, receipt freshness, and forbidden
  authority markers. It returns pass/warn/block findings and a deterministic
  report hash, but it does not mutate proposals or authorize apply.
- There is no current Agent approval, live order, fund transfer, broker submit API,
  authority contract, or receipt deletion/overwrite interface. Those are future
  capability candidates only if they receive purpose-built runtime profiles,
  command paths, receipts, review/approval surfaces, and failure modes.
- Any new production dependency still needs explicit user approval before being
  added.

## Adapter Acceptance Checklist

Before a new adapter is considered complete:

- The existing caller-facing interface remains stable or has a migration note.
- Tests characterize the old behavior where applicable.
- Tests prove the adapter path is exercised.
- Receipts or summaries disclose backend/tool name and version when relevant.
- The adapter output includes a clear non-authority boundary.
- No current docs mention task names that are absent from `Taskfile.yml`.
