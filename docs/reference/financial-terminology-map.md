# Financial Terminology Map

Status: current

This document maps canonical finance and market-structure vocabulary to
FinHarness governance primitives. It is a terminology alignment layer, not a
regulatory compliance claim.

FinHarness should use canonical finance vocabulary in external explanations
when that vocabulary is precise enough. It should keep FinHarness primitive
names when traditional terms would imply adviser, broker, fiduciary, order
routing, or execution authority that the system does not have.

## Design Rule

Use this three-part mapping before adding or explaining a capital-action
primitive:

```text
Canonical finance term
  <-> FinHarness primitive
  <-> Governance / receipt meaning
```

The goal is not to make FinHarness look like a broker-dealer, RIA, OMS, EMS, or
execution venue. The goal is to keep its internal AI-agent governance language
legible to people who already know investment policy, delegated authority,
pre-trade controls, order tickets, audit trails, and supervisory review.

## Non-Claims

- Regulatory analogy is not regulatory status.
- Finance term mapping is not broker, adviser, fiduciary, or execution
  capability.
- A receipt is evidence, not authorization.
- A grant credential is not execution permission.
- Authority admission is not preflight approval.
- Preflight pass is not trade approval.
- TradePlanCandidate is not an order ticket.
- OrderTicketCandidate is not broker submission.
- Broker submission is not guaranteed execution.

## Terminology Table

| Canonical finance term | FinHarness primitive | Definition | What it permits | What it does not permit | Receipt / audit evidence | Regulatory / industry analogy | Non-claim |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Investment Policy Statement | `InvestmentPolicyStatement` / `IPS` | User-owned statement of objectives, constraints, risk limits, and policy posture. | Policy checks, context, review prompts. | Broker authority, adviser status, order routing, execution. | IPS records, policy check output, linked receipts. | IPS discipline and policy-as-code posture. | IPS is policy context, not execution authority. |
| Investment mandate / risk mandate | `CapitalMandate` | Human-attested capital policy domain that future authority objects may cite. | Future grants and checks may reference an active mandate. | Agent identity, trade approval, order tickets, broker submission, execution. | `state_core_capital_mandate` receipts. | Mandate / risk-limit control vocabulary. | A mandate is not a grant or an order. |
| Delegated authority / entitlement | `AgentAuthorityGrant` | Mandate-bound Agent credential with dynamic validation against current grant and mandate state. | Agent may hold a bounded credential for downstream governance checks. | Trade approval, preflight bypass, order submission, execution. | `state_core_agent_authority_grant` receipts and validation results. | Delegated authority / entitlement checks. | A grant is not approval to trade. |
| Investment instruction / proposed capital action | `ActionIntentCandidate` | Proposal-bound expression of a possible capital action. | A candidate action may enter authority admission and preflight if other gates allow. | Broker instruction, order ticket, execution instruction. | `state_core_action_intent` receipts. | Investment instruction or proposed action, before order creation. | An intent is not an order. |
| Authority admission / entitlement check | `ActionIntentAuthorityBinding` | Receipt-backed result proving whether an action-intent author may admit the intent into downstream checks. | Admission to the next governance step when allowed. | Preflight pass, trade approval, order ticket, broker submission, execution. | `state_core_action_intent_authority_binding` receipts preserving binding and grant deny reasons. | Entitlement check before pre-trade controls. | Admission is not authorization. |
| Pre-trade risk controls | `ActionIntentPreflight` | Deterministic checks over freshness, policy, scope, evidence, preconditions, and risk posture. | Pass / warn / block readiness for downstream review. | Trade approval, order creation, execution. | Preflight result and hash linked from later artifacts. | Market-access risk controls and pre-order risk checks. | Preflight pass is not approval. |
| Scenario analysis / what-if | `ActionIntentSimulationReport` | Descriptive simulation evidence bound to current action intent and preflight state. | Evidence for review and planning. | Authorization, advice, order creation. | `state_core_action_intent_simulation_report` receipts. | Scenario analysis / impact analysis. | Simulation is evidence, not permission. |
| Proposed trade list / rebalance proposal | `TradePlanCandidate` | Candidate-only pre-trade plan derived from an action intent and simulation evidence. | Review candidate for future approval gates. | Approved trade, order ticket, broker instruction, execution. | `state_core_trade_plan_candidate` receipts. | Proposed trade list or rebalance proposal. | A trade plan candidate is not an order. |
| Supervisory review / approval gate | `TradePlanReviewGate` | Human review gate deciding whether a candidate plan may enter future order-ticket-candidate staging. | Staging eligibility for the next candidate gate. | Order creation, broker submission, suitability certification, AuthorityContract, execution guarantee. | `state_core_trade_plan_review_gate` receipts. | Supervisory review / approval workflow. | Approval to stage is not execution. |
| Order ticket / staged order | `OrderTicketCandidate` | Future non-submitted order candidate created from an approved plan. | Input to broker submission controls. | Submitted order, routed order, execution. | Future order-ticket candidate receipts. | OMS order ticket. | A ticket candidate is not a broker submission. |
| Order routing / submission control | `BrokerSubmissionGate` | Future final gate before any broker submission capability. | Submit eligibility if all explicit conditions are met. | Execution guarantee, best execution certification, live trading by default. | Future submission-gate receipts. | Broker submission control / market-access gate. | Submission is not execution. |
| Audit trail / evidence record | `Receipt` | Immutable evidence record of what was written, when, and from what source refs. | Auditability, replay, linkage. | Authority by itself, resolution by itself. | Receipt files and `ReceiptIndex` records. | Audit trail / evidence record. | Receipt evidence is not authorization. |
| Policy decision result | Structured deny reason | Machine-readable reason a gate denied or blocked a transition. | Downstream consumption, review, debugging. | Discretionary override or hidden approval. | Deny reason fields on gate artifacts. | Policy decision result / control failure reason. | A deny reason is evidence, not a waiver. |

## Design Analogies

These analogies shape FinHarness terminology, but they do not claim FinHarness
is regulated like the referenced systems.

- SEC Rule 15c3-5 market-access guidance describes documented risk management
  controls and supervisory procedures for broker-dealers with market access,
  including controls around credit/capital thresholds, erroneous orders,
  pre-order regulatory requirements, authorized access, and periodic review:
  <https://www.sec.gov/rules-regulations/staff-guidance/trading-markets-frequently-asked-questions/divisionsmarketregfaq-0>.
- FINRA Rule 5310 describes best-execution diligence and regular review of
  execution quality for members handling customer orders:
  <https://www.finra.org/rules-guidance/rulebooks/finra-rules/5310>.
- Harness Policy as Code uses OPA/Rego to evaluate governance policies over
  platform entities and processes:
  <https://developer.harness.io/docs/platform/governance/policy-as-code/harness-governance-overview/>.

FinHarness borrows the shape of layered controls, structured policy decisions,
and reviewable evidence. It does not claim broker-dealer, RIA, exchange,
fiduciary, compliance certification, best-execution, or live-execution status.

## Maintenance Rule

Update this map when a new capital-governance primitive is added, renamed, or
promoted into a current API / receipt surface.

Before naming a new primitive:

1. Choose the canonical finance term that a reader would expect.
2. Decide whether that term is too broad or authority-implying for the actual
   FinHarness object.
3. If a FinHarness primitive is kept, document its finance analogue, receipt
   meaning, and non-claim here.
4. Keep finance analogies as design analogies, not regulatory claims.
