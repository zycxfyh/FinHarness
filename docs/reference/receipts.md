# Receipt Reference

Receipts are durable evidence roots for FinHarness workflows. They record what
was produced, which inputs and tools were used, where artifacts were written, and
what the output does not authorize.

Receipts are evidence, not proof of correctness and not trading permission.

## Type Notation

| Notation | Meaning |
| --- | --- |
| `str`, `int`, `float`, `bool` | JSON scalar values. |
| `list[T]` | JSON array of `T`. |
| `dict[str, T]` | JSON object with string keys and `T` values. |
| `A | None` | Nullable field. |
| `Literal[...]` | Field accepts only the listed values. |
| `default: ...` | Field may be omitted by model construction and defaults to that value. |
| `Field(default_factory=...)` | Field defaults to a new list/dict at runtime. |

Nested record arrays such as `EventRecord`, `ValidationJob`, `RiskGateDecision`,
or `ExecutionEvent` are named here as nested model types. This page documents the
receipt, snapshot, quality, and lineage surfaces; detailed domain-record fields
belong in the module references.

## Common Envelope

Most Pydantic-backed receipts use the following envelope:

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `receipt_id` | `str` | yes | Stable id for this receipt instance. |
| `created_at_utc` | `str` | yes | Creation timestamp in UTC. |
| `kind` | `str` | defaulted | Receipt category, for example `market_data_ingestion`. |
| `stage_flow` | `dict[str, str]` | usually | Human-readable stage map for how the result was produced. |
| `eight_layer_map` | `dict[str, str]` | market-data only | Market-data-specific stage map. |
| `snapshot` | layer snapshot model | yes | Typed output snapshot for the layer. |
| `status` | `Literal["ok", "warning", "failed"]` | most layers | Local receipt status. |

Most snapshots use the following evidence fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `quality` | layer quality model | Layer-specific quality gates and notes. |
| `lineage` | layer lineage model | Input refs, backend/method, transform version, hashes, output refs. |
| `payload_ref` | `str` | Path to normalized output payload. |
| `receipt_ref` | `str` | Path to the receipt JSON. |
| `execution_allowed` | `bool` | Usually `false`; evidence does not become execution authority. |
| `review_questions` | `list[str]` | Human review prompts where applicable. |

## Current Receipt Envelope By Surface

These are the current receipt families a maintainer should expect on the active
Capital OS path. Archived trading-chain and live-broker experiments are listed
separately below so they are not mistaken for current authority.

| Surface | Receipt model / shape | `kind` | Stage field | Snapshot field | Status |
| --- | --- | --- | --- | --- | --- |
| Market data | `DataReceipt` | `market_data_ingestion` | `eight_layer_map` | `MarketDataSnapshot` | none |
| Investment Policy Statement | direct JSON dictionary | `state_core_ips` | n/a | `InvestmentPolicyStatement` | n/a |
| Capital mandate | direct JSON dictionary | `state_core_capital_mandate` | n/a | `CapitalMandate` | n/a |
| Agent authority grant | direct JSON dictionary | `state_core_agent_authority_grant` | n/a | `AgentAuthorityGrant` | n/a |
| Action intent candidate | direct JSON dictionary | `state_core_action_intent_candidate` | n/a | `ActionIntent` | n/a |
| Action intent authority binding | direct JSON dictionary | `state_core_action_intent_authority_binding` | n/a | `ActionIntentAuthorityBinding` | n/a |
| Action intent simulation report | direct JSON dictionary | `state_core_action_intent_simulation_report` | n/a | `ActionIntentSimulationReport` | n/a |
| Trade plan candidate | direct JSON dictionary | `state_core_trade_plan_candidate` | n/a | `TradePlanCandidate` | n/a |
| Capital objective fit | direct JSON dictionary | `state_core_capital_objective_fit` | n/a | `CapitalObjectiveFit` | n/a |
| Trade plan review gate | direct JSON dictionary | `state_core_trade_plan_review_gate` | n/a | `TradePlanReviewGate` | n/a |

## Historical / Archived Receipt Envelope By Surface

These receipt families are retained for audit/history or archived evidence
reading. They are not the current product route for delegated authority.

| Surface | Receipt model / shape | `kind` | Stage field | Snapshot field | Status |
| --- | --- | --- | --- | --- | --- |
| Indicators | `IndicatorReceipt` | `indicator_processing` | `stage_flow` | `IndicatorSnapshot` | none |
| Events | `EventReceipt` | `event_ingestion` | `stage_flow` | `EventSnapshot` | `ok | warning | failed` |
| Interpretation | `InterpretationReceipt` | `interpretation_processing` | `stage_flow` | `InterpretationSnapshot` | `ok | warning | failed` |
| Hypotheses | `HypothesisReceipt` | `hypothesis_processing` | `stage_flow` | `HypothesisSnapshot` | `ok | warning | failed` |
| Validation | `ValidationReceipt` | `validation_processing` | `stage_flow` | `ValidationSnapshot` | `ok | warning | failed` |
| Proposal | `ProposalReceipt` | `proposal_processing` | `stage_flow` | `ProposalSnapshot` | `ok | warning | failed` |
| Risk Gate | `RiskGateReceipt` | `risk_gate_processing` | `stage_flow` | `RiskGateSnapshot` | `ok | warning | failed` |
| Execution | `ExecutionReceipt` | `execution_processing` | `stage_flow` | `ExecutionSnapshot` | `ok | warning | failed` |
| Post trade | `PostTradeReceipt` | `post_trade_processing` | `stage_flow` | `PostTradeSnapshot` | `ok | warning | failed` |
| Daily evidence | `DailyEvidenceReceipt` | `daily_evidence_bundle` | `stage_flow` | `DailyEvidenceSnapshot` | `ok | warning | failed` |
| Control owner | n/a | `control_owner_certification` | `lineage` | `ControlCertification` | `certified | not_certified` |
| Market access ledger | n/a | `market_access_consumption` | n/a | `LedgerEntry` | n/a |

## Typed Evidence Snapshot Schemas

Most schemas below belong to the historical ten-layer evidence chain. Market
data remains a current L0B building block; the other chain snapshots are kept so
old receipts stay readable.

| Snapshot | Fields |
| --- | --- |
| `MarketDataSnapshot` | `snapshot_id: str`; `as_of_utc: str`; `symbols: list[str]`; `fields: list[str]`; `timeframe: str`; `adjusted: bool`; `quality: MarketDataQuality`; `lineage: MarketDataLineage`; `payload_ref: str`; `receipt_ref: str` |
| `IndicatorSnapshot` | `indicator_snapshot_id: str`; `symbol: str`; `as_of_utc: str`; `latest_date: str`; `features: dict[str, Any]`; `quality: IndicatorQuality`; `lineage: IndicatorLineage`; `payload_ref: str`; `receipt_ref: str`; `execution_allowed: bool = false` |
| `EventSnapshot` | `snapshot_id: str`; `as_of_utc: str`; `universe: list[str]`; `filing_symbols: list[str]`; `context_symbols: list[str]`; `event_count: int`; `records: list[EventRecord]`; `quality: EventQuality`; `lineage: EventLineage`; `payload_ref: str`; `receipt_ref: str`; `execution_allowed: bool = false`; `review_questions: list[str]` |
| `InterpretationSnapshot` | `interpretation_snapshot_id: str`; `as_of_utc: str`; `input_event_snapshot_id: str`; `universe: list[str]`; `record_count: int`; `records: list[InterpretationRecord]`; `quality: InterpretationQuality`; `lineage: InterpretationLineage`; `payload_ref: str`; `receipt_ref: str`; `execution_allowed: bool = false`; `hypothesis_candidates: list[str]`; `review_questions: list[str]` |
| `HypothesisSnapshot` | `hypothesis_snapshot_id: str`; `as_of_utc: str`; `input_interpretation_snapshot_id: str`; `universe: list[str]`; `record_count: int`; `records: list[HypothesisRecord]`; `quality: HypothesisQuality`; `lineage: HypothesisLineage`; `payload_ref: str`; `receipt_ref: str`; `execution_allowed: bool = false`; `validation_handoff: list[str]`; `review_questions: list[str]` |
| `ValidationSnapshot` | `validation_snapshot_id: str`; `as_of_utc: str`; `input_hypothesis_snapshot_id: str`; `universe: list[str]`; `job_count: int`; `result_count: int`; `jobs: list[ValidationJob]`; `results: list[ValidationCheckResult]`; `quality: ValidationQuality`; `lineage: ValidationLineage`; `payload_ref: str`; `receipt_ref: str`; `execution_allowed: bool = false`; `proposal_handoff: list[str]`; `review_questions: list[str]` |
| `ProposalSnapshot` | `proposal_snapshot_id: str`; `as_of_utc: str`; `input_validation_snapshot_id: str`; `universe: list[str]`; `candidate_count: int`; `candidates: list[ProposalCandidate]`; `quality: ProposalQuality`; `lineage: ProposalLineage`; `payload_ref: str`; `receipt_ref: str`; `execution_allowed: bool = false`; `risk_gate_handoff: list[str]`; `review_questions: list[str]` |
| `RiskGateSnapshot` | `risk_gate_snapshot_id: str`; `as_of_utc: str`; `input_proposal_snapshot_id: str`; `universe: list[str]`; `candidate_count: int`; `decision_count: int`; `context: RiskGateContext`; `decisions: list[RiskGateDecision]`; `quality: RiskGateQuality`; `lineage: RiskGateLineage`; `payload_ref: str`; `receipt_ref: str`; `execution_allowed: bool = false`; `execution_handoff: list[str]`; `review_questions: list[str]` |
| `ExecutionSnapshot` | `execution_snapshot_id: str`; `as_of_utc: str`; `input_risk_gate_snapshot_id: str`; `input_risk_gate_receipt_ref: str`; `mode: Literal["dry_run", "paper", "live"]`; `intent_count: int`; `order_request_count: int`; `event_count: int`; `final_status: ExecutionStatus`; `intents: list[ExecutionIntent]`; `order_requests: list[ExecutionOrderRequest]`; `events: list[ExecutionEvent]`; `authorization: AuthorizationDecision`; `quality: ExecutionQuality`; `lineage: ExecutionLineage`; `payload_ref: str`; `receipt_ref: str`; `execution_allowed: bool = false`; `post_trade_handoff: list[str]`; `review_questions: list[str]` |
| `PostTradeSnapshot` | `post_trade_snapshot_id: str`; `as_of_utc: str`; `input_execution_snapshot_id: str`; `input_execution_receipt_ref: str`; `final_status: PostTradeStatus`; `reconciliation_count: int`; `cost_estimate_count: int`; `exception_count: int`; `reconciliations: list[PostTradeReconciliation]`; `cost_estimates: list[PostTradeCostEstimate]`; `exceptions: list[PostTradeException]`; `quality: PostTradeQuality`; `lineage: PostTradeLineage`; `payload_ref: str`; `receipt_ref: str`; `order_creation_allowed: bool = false`; `portfolio_handoff: list[str]`; `accounting_handoff: list[str]`; `performance_handoff: list[str]`; `review_questions: list[str]` |
| `DailyEvidenceSnapshot` | `daily_evidence_snapshot_id: str`; `as_of_utc: str`; `universe: list[str]`; `market_symbols: list[str]`; `layer_summaries: dict[str, Any]`; `quality: DailyEvidenceQuality`; `lineage: DailyEvidenceLineage`; `payload_ref: str`; `receipt_ref: str`; `execution_allowed: bool = false`; `review_questions: list[str]` |

## Quality Schemas

| Quality model | Fields |
| --- | --- |
| `MarketDataQuality` | `ok: bool`; `row_count: int`; `missing_required_columns: list[str]`; `duplicate_timestamps: int = 0`; `null_counts: dict[str, int]`; `stale: bool = false`; `outlier_flags: list[str]`; `notes: list[str]`; `reconciliation: dict[str, Any] \| None` |
| `IndicatorQuality` | `ok: bool`; `row_count: int`; `feature_count: int`; `warmup_null_counts: dict[str, int]`; `latest_null_features: list[str]`; `notes: list[str]` |
| `EventQuality` | `ok: bool`; `record_count: int`; `missing_fields: dict[str, list[str]]`; `parse_errors: list[str]`; `duplicate_count: int = 0`; `stale_count: int = 0`; `mapping_confidence_min: float | None`; `license_boundary: str = official_public_sec_data`; `execution_allowed: bool = false`; `notes: list[str]` |
| `InterpretationQuality` | `ok: bool`; `record_count: int`; `source_backed_claims: bool`; `counterevidence_present: bool`; `no_execution_language: bool`; `horizon_present: bool`; `confidence_bounded: bool`; `claim_evidence_separation: bool`; `missing_required_fields: dict[str, list[str]]`; `execution_language_hits: dict[str, list[str]]`; `notes: list[str]` |
| `HypothesisQuality` | `ok: bool`; `record_count: int`; `source_backed_hypotheses: bool`; `testable_predictions_present: bool`; `disconfirming_evidence_present: bool`; `horizon_present: bool`; `validation_plan_present: bool`; `no_execution_language: bool`; `no_recommendation_language: bool`; `claim_not_marked_validated: bool`; `temporal_context_separated: bool`; `duplicate_hypothesis_check: bool`; `missing_required_fields: dict[str, list[str]]`; `blocked_language_hits: dict[str, list[str]]`; `duplicate_hypothesis_ids: list[str]`; `notes: list[str]` |
| `ValidationQuality` | `ok: bool`; `job_count: int`; `result_count: int`; `hypothesis_source_linked: bool`; `validation_jobs_created: bool`; `source_validity_checked: bool`; `at_least_one_market_check: bool`; `at_least_one_disconfirmation_check: bool`; `benchmark_context_present: bool`; `no_proposal_or_execution_language: bool`; `limitations_present: bool`; `result_not_overclaimed: bool`; `lineage_complete: bool`; `missing_required_fields: dict[str, list[str]]`; `blocked_language_hits: dict[str, list[str]]`; `notes: list[str]` |
| `ProposalQuality` | `ok: bool`; `candidate_count: int`; `validation_snapshot_linked: bool`; `validation_quality_ok: bool`; `evidence_summary_present: bool`; `validation_summary_present: bool`; `portfolio_role_present: bool`; `invalidation_triggers_present: bool`; `risk_handoff_present: bool`; `constraints_present: bool`; `alternatives_considered: bool`; `do_nothing_case_present: bool`; `no_execution_authority: bool`; `no_order_language: bool`; `no_final_sizing: bool`; `human_review_required: bool`; `missing_required_fields: dict[str, list[str]]`; `blocked_language_hits: dict[str, list[str]]`; `notes: list[str]` |
| `RiskGateQuality` | `ok: bool`; `candidate_count: int`; `decision_count: int`; `proposal_snapshot_linked: bool`; `proposal_quality_ok: bool`; `decision_count_matches_candidate_count: bool`; `all_decisions_have_checks: bool`; `hard_blocks_enforced: bool`; `mandate_present: bool`; `permission_boundary_present: bool`; `human_review_required: bool`; `no_order_language: bool`; `no_live_execution_authority: bool`; `no_final_sizing: bool`; `lineage_complete: bool`; `receipt_written: bool`; `missing_required_fields: dict[str, list[str]]`; `blocked_language_hits: dict[str, list[str]]`; `notes: list[str]` |
| `ExecutionQuality` | `ok: bool`; `risk_gate_lineage_present: bool`; `approved_decision_required: bool`; `paper_mode_required: bool`; `live_mode_blocked: bool`; `human_review_satisfied_when_required: bool`; `idempotency_key_present: bool`; `order_request_matches_approved_intent: bool`; `raw_adapter_events_preserved: bool`; `final_state_present: bool`; `authorization_registered: bool`; `receipt_written: bool`; `notes: list[str]` |
| `PostTradeQuality` | `ok: bool`; `execution_lineage_present: bool`; `execution_receipt_present: bool`; `no_order_creation: bool`; `final_execution_state_classified: bool`; `filled_quantity_reconciled: bool`; `partial_fill_exception_preserved: bool`; `reject_cancel_exception_preserved: bool`; `tca_inputs_disclosed: bool`; `handoff_state_present: bool`; `receipt_written: bool`; `notes: list[str]` |
| `DailyEvidenceQuality` | `ok: bool`; `layer_quality: dict[str, bool]`; `failed_layers: list[str]`; `execution_allowed: bool = false`; `notes: list[str]` |

## Selected Nested Model Fields

| Model | Fields |
| --- | --- |
| `ValidationCheckResult` | `check_id: str`; `validation_job_id: str`; `hypothesis_id: str`; `check_type: Literal["source_validity", "mechanism", "event_reaction", "benchmark_context", "disconfirmation", "limitations", "backtest"]`; `result: Literal["supported", "linked", "present", "well_formed", "weakened", "disconfirmed", "inconclusive", "not_testable"]`; `supports_hypothesis: bool`; `disconfirms_hypothesis: bool`; `confidence: Literal["low", "medium", "high", "unknown"]`; `limitations: list[str]` |
| `AuthorizationDecision` | `allowed: bool`; `operator_id: str`; `account_id: str`; `environment: Literal["paper", "live"]`; `scope: str`; `registry_version: str \| None`; `registry_ref: str \| None`; `reason: str`; `blocking_reasons: list[str]`; `non_claims: list[str]`; `execution_allowed: bool = false` |
| `RestrictedSymbolDecision` | `symbol: str`; `normalized_symbol: str`; `restricted: bool`; `restricted_list_version: str \| None`; `restricted_list_ref: str \| None`; `reason: str`; `evidence_refs: list[str]` |
| `TradabilityDecision` | `symbol: str`; `normalized_symbol: str`; `provider: Literal["not_applicable", "alpaca", "okx", "manual"]`; `status: Literal["tradable", "not_tradable", "unknown", "not_applicable"]`; `allowed: bool`; `reason: str`; `source_ref: str \| None`; `evidence_refs: list[str]` |
| `RiskGateDecision` additions | `authorization: AuthorizationDecision`; `restricted_symbol: RestrictedSymbolDecision`; `tradability: TradabilityDecision`; `live_execution_allowed: bool = false` |
| `PostTradeReconciliation` additions | `intended_quantity: int`; `submitted_quantity: int`; `canceled_quantity: int`; `rejected_quantity: int`; `remaining_quantity: int`; `lifecycle_quantity_reconciled: bool`; `lifecycle_notes: list[str]` |
| `PostTradeCostEstimate` additions | `arrival_price: float \| None`; `execution_price: float \| None`; `side: Literal["buy", "sell"] \| None`; `implementation_shortfall: float \| None`; `tca_limitations: list[str]`; `notes: list[str]` |

## Lineage Schemas

| Lineage model | Fields |
| --- | --- |
| `MarketDataLineage` | `source: SourceSpec`; `fetched_at_utc: str`; `fetch_config: dict[str, Any]`; `raw_hash: str`; `normalized_hash: str`; `transform_version: str = finharness.market_data.v1`; `quality_backend: str \| None`; `quality_backend_version: str \| None`; `raw_ref: str`; `normalized_ref: str`; `catalog_ref: str \| None`; `data_bias_controls: list[str]` |
| `IndicatorLineage` | `input_snapshot_id: str | None`; `input_payload_ref: str | None`; `indicator_specs: list[IndicatorSpec]`; `computed_at_utc: str`; `transform_version: str = finharness.indicator_layer.v1`; `output_hash: str`; `output_ref: str` |
| `EventLineage` | `source: EventSourceSpec`; `fetched_at_utc: str`; `fetch_config: dict[str, Any]`; `raw_hash: str`; `parsed_hash: str`; `transform_version: str = finharness.events.sec_edgar.v1`; `raw_refs: list[str]`; `parsed_ref: str`; `linked_market_snapshot_refs: list[str]`; `linked_indicator_snapshot_refs: list[str]` |
| `InterpretationLineage` | `source: InterpretationSourceSpec`; `input_event_snapshot_id: str`; `input_event_receipt_ref: str`; `event_record_ids: list[str]`; `market_snapshot_refs: list[str]`; `indicator_snapshot_refs: list[str]`; `computed_at_utc: str`; `transform_version: str = finharness.interpretation.v1`; `output_hash: str`; `output_ref: str` |
| `HypothesisLineage` | `source: HypothesisSourceSpec`; `input_interpretation_snapshot_id: str`; `input_interpretation_receipt_ref: str`; `input_event_snapshot_id: str`; `interpretation_record_ids: list[str]`; `event_record_ids: list[str]`; `market_snapshot_refs: list[str]`; `indicator_snapshot_refs: list[str]`; `method: str`; `model_provider: str | None`; `prompt_template_version: str | None`; `computed_at_utc: str`; `transform_version: str = finharness.hypotheses.v1`; `output_hash: str`; `output_ref: str` |
| `ValidationLineage` | `source: ValidationSourceSpec`; `input_hypothesis_snapshot_id: str`; `input_hypothesis_receipt_ref: str`; `hypothesis_ids: list[str]`; `interpretation_snapshot_id: str`; `event_snapshot_id: str`; `market_snapshot_refs: list[str]`; `indicator_snapshot_refs: list[str]`; `method: str`; `model_provider: str | None`; `prompt_template_version: str | None`; `computed_at_utc: str`; `transform_version: str = finharness.validation.v1`; `output_hash: str`; `output_ref: str` |
| `ProposalLineage` | `source: ProposalSourceSpec`; `input_validation_snapshot_id: str`; `input_validation_receipt_ref: str`; `validation_result_ids: list[str]`; `hypothesis_ids: list[str]`; `validation_transform_version: str`; `method: str`; `model_provider: str | None`; `prompt_template_version: str | None`; `computed_at_utc: str`; `transform_version: str = finharness.proposal.v1`; `output_hash: str`; `output_ref: str` |
| `RiskGateLineage` | `source: RiskGateSourceSpec`; `input_proposal_snapshot_id: str`; `input_proposal_receipt_ref: str`; `proposal_ids: list[str]`; `proposal_transform_version: str`; `method: str`; `model_provider: str | None`; `prompt_template_version: str | None`; `computed_at_utc: str`; `transform_version: str = finharness.risk_gate.v1`; `output_hash: str`; `output_ref: str` |
| `ExecutionLineage` | `source: ExecutionSourceSpec`; `input_risk_gate_snapshot_id: str`; `input_risk_gate_receipt_ref: str`; `decision_ids: list[str]`; `adapter_name: str`; `adapter_mode: Literal["dry_run", "paper", "live"]`; `idempotency_keys: list[str]`; `order_request_hash: str`; `computed_at_utc: str`; `transform_version: str = finharness.execution.v1`; `output_hash: str`; `output_ref: str` |
| `PostTradeLineage` | `source: PostTradeSourceSpec`; `input_execution_snapshot_id: str`; `input_execution_receipt_ref: str`; `execution_event_ids: list[str]`; `execution_final_status: str`; `post_trade_status: PostTradeStatus`; `computed_at_utc: str`; `transform_version: str = finharness.post_trade.v1`; `output_hash: str`; `output_ref: str` |
| `DailyEvidenceLineage` | `market_snapshot_refs: list[str]`; `indicator_snapshot_refs: list[str]`; `event_snapshot_ref: str | None`; `interpretation_snapshot_ref: str | None`; `computed_at_utc: str`; `transform_version: str = finharness.daily_evidence.v1`; `output_hash: str`; `output_ref: str` |

## Non-Standard Receipt Shapes

Some receipts are written as direct JSON dictionaries rather than the common
Pydantic envelope.

### State Core IPS Receipt

Location: `data/receipts/state-core/ips/`

| Field | Type | Meaning |
| --- | --- | --- |
| `receipt_id` | `str` | IPS receipt id. |
| `kind` | `str` | `state_core_ips`. |
| `created_at_utc` | `str` | Creation timestamp. |
| `ips` | `InvestmentPolicyStatement` | Queryable IPS mirror payload. |
| `governance.execution_allowed` | `bool` | Always false. |
| `governance.not_execution_authorization` | `bool` | Explicit non-authorization flag. |
| `governance.not_investment_advice` | `bool` | Explicit non-advice flag. |
| `governance.user_set_policy` | `bool` | IPS is user-owned policy. |

### Capital Mandate Receipt

Location: `data/receipts/state-core/capital-mandates/`

| Field | Type | Meaning |
| --- | --- | --- |
| `receipt_id` | `str` | CapitalMandate receipt id. |
| `kind` | `str` | `state_core_capital_mandate`. |
| `created_at_utc` | `str` | Creation timestamp. |
| `capital_mandate` | `CapitalMandate` | Human-attested policy-domain payload. |
| `source_ips` | `InvestmentPolicyStatement \| None` | Source IPS snapshot when one is linked. |
| `governance_boundary.execution_allowed` | `bool` | Always false. |
| `governance_boundary.authority_transition` | `bool` | Always false. |
| `governance_boundary.explicit_confirmation` | `bool` | True for a valid mandate write. |
| `governance_boundary.human_attested_policy_domain` | `bool` | Mandate is human-attested policy. |
| `governance_boundary.future_authority_basis` | `bool` | Future authority objects may cite it. |
| `governance_boundary.not_execution_authorization` | `bool` | It does not authorize execution. |
| `governance_boundary.not_agent_identity_grant` | `bool` | It does not grant Agent identity. |
| `governance_boundary.not_authority_contract` | `bool` | It is not an AuthorityContract. |
| `governance_boundary.not_order_ticket` | `bool` | It is not an order ticket. |
| `non_claims` | `list[str]` | Boundary claims carried with the receipt. |

### Agent Authority Grant Receipt

Location: `data/receipts/state-core/agent-authority-grants/`

| Field | Type | Meaning |
| --- | --- | --- |
| `receipt_id` | `str` | AgentAuthorityGrant receipt id. |
| `kind` | `str` | `state_core_agent_authority_grant`. |
| `created_at_utc` | `str` | Creation timestamp. |
| `agent_authority_grant` | `AgentAuthorityGrant` | Mandate-bound authority credential payload. |
| `source_capital_mandate` | `CapitalMandate` | Linked mandate snapshot at grant creation time. |
| `creation_validation` | `AgentAuthorityGrantValidationResult` | Structured create-time validation result. |
| `governance_boundary.execution_allowed` | `bool` | Always false. |
| `governance_boundary.authority_transition` | `bool` | Always false. |
| `governance_boundary.mandate_bound_authority_credential` | `bool` | True; the grant must cite a mandate. |
| `governance_boundary.dynamic_validation_required` | `bool` | True; use-time validation must re-check current grant and mandate state. |
| `governance_boundary.not_authentication` | `bool` | It is not login/authentication identity. |
| `governance_boundary.not_trade_plan_approval` | `bool` | It does not approve a trade plan. |
| `governance_boundary.not_order_ticket` | `bool` | It is not an order ticket. |
| `governance_boundary.not_broker_submission` | `bool` | It does not submit to a broker. |
| `governance_boundary.not_preflight_bypass` | `bool` | It does not bypass preflight. |
| `governance_boundary.not_execution_authorization` | `bool` | It does not authorize execution. |
| `non_claims` | `list[str]` | Boundary claims carried with the receipt. |

### Action Intent Candidate Receipt

Location: `data/receipts/state-core/action-intents/`

| Field | Type | Meaning |
| --- | --- | --- |
| `receipt_id` | `str` | `receipt_<action_intent_id>`. |
| `kind` | `str` | `state_core_action_intent_candidate`. |
| `created_at_utc` | `str` | Creation timestamp. |
| `proposal_id` | `str` | Source proposal id. |
| `source_proposal_receipt_ref` | `str` | Current proposal receipt consumed by the write. |
| `source_revision_receipt_ref` | `str \| None` | Optional proposal revision receipt consumed by the write. |
| `action_intent` | `ActionIntent` | Candidate-only future capital action intent. |
| `governance.execution_allowed` | `bool` | Always false. |
| `governance.authority_transition` | `bool` | Always false. |
| `governance.candidate_only` | `bool` | True. |
| `governance.not_order` | `bool` | True; not an order ticket. (legacy) |
| `governance.not_advice_not_execution` | `bool` | True. (legacy) |
| `governance.non_claims` | `list[str]` | Explicit action-intent non-claims. |

### Action Intent Authority Binding Receipt

Location: `data/receipts/state-core/action-intent-authority-bindings/`

| Field | Type | Meaning |
| --- | --- | --- |
| `receipt_id` | `str` | `receipt_<binding_id>`. |
| `kind` | `str` | `state_core_action_intent_authority_binding`. |
| `created_at_utc` | `str` | Creation timestamp. |
| `action_intent_id` | `str` | Source action intent id. |
| `source_action_intent_receipt_ref` | `str \| None` | Current action intent receipt consumed by the write. |
| `action_intent_authority_binding` | `ActionIntentAuthorityBinding` | Receipt-backed admission artifact. |
| `binding_result` | `ActionIntentAuthorityBindingResult` | Structured allow/deny result. |
| `binding_result.source.binding` | `list[str]` | Binding-layer deny reasons such as missing grant or author mismatch. |
| `binding_result.source.grant_validation` | `list[str]` | Preserved AgentAuthorityGrant validation deny reasons. |
| `governance_boundary.execution_allowed` | `bool` | Always false. |
| `governance_boundary.authority_transition` | `bool` | Always false. |
| `governance_boundary.authority_admission_only` | `bool` | True; allowed only admits the intent into downstream checks. |
| `governance_boundary.not_action_preflight` | `bool` | It is not preflight. |
| `governance_boundary.not_trade_plan_approval` | `bool` | It does not approve a trade plan. |
| `governance_boundary.not_order_ticket` | `bool` | It is not an order ticket. |
| `governance_boundary.not_broker_submission` | `bool` | It does not submit to a broker. |
| `governance_boundary.not_preflight_bypass` | `bool` | It does not bypass preflight. |
| `governance_boundary.not_execution_authorization` | `bool` | It does not authorize execution. |
| `non_claims` | `list[str]` | Boundary claims carried with the receipt. |

### Action Intent Simulation Report Receipt

Location: `data/receipts/state-core/action-intent-simulations/`

| Field | Type | Meaning |
| --- | --- | --- |
| `receipt_id` | `str` | `receipt_<simulation_report_id>`. |
| `kind` | `str` | `state_core_action_intent_simulation_report`. |
| `created_at_utc` | `str` | Creation timestamp. |
| `action_intent_id` | `str` | Source action intent id. |
| `proposal_id` | `str` | Source proposal id. |
| `source_action_intent_receipt_ref` | `str` | Current action intent receipt consumed by the write. |
| `source_action_preflight_report_hash` | `str` | Current recomputed preflight hash consumed by the write. |
| `source_action_preflight_status` | `str` | Current preflight status. |
| `source_action_preflight_finding_codes` | `list[str]` | Current preflight finding codes. |
| `simulation_report` | `ActionIntentSimulationReport` | Descriptive, preflight-bound downstream report. |
| `preflight_snapshot.status` | `str` | Recomputed preflight status. |
| `preflight_snapshot.report_hash` | `str` | Recomputed preflight report hash. |
| `preflight_snapshot.finding_codes` | `list[str]` | Recomputed preflight finding codes. |
| `preflight_snapshot.impact_summary` | `dict[str, Any]` | Qualitative impact summary used by the report. |
| `governance.execution_allowed` | `bool` | Always false. |
| `governance.authority_transition` | `bool` | Always false. |
| `governance.preflight_bound` | `bool` | True. |
| `governance.not_order_ticket` | `bool` | True. |
| `governance.not_execution_authorization` | `bool` | True. |
| `governance.not_investment_advice` | `bool` | True. |
| `governance.non_claims` | `list[str]` | Explicit simulation-report non-claims. |

### Trade Plan Candidate Receipt

Location: `data/receipts/state-core/trade-plan-candidates/`

| Field | Type | Meaning |
| --- | --- | --- |
| `receipt_id` | `str` | `receipt_<trade_plan_candidate_id>`. |
| `kind` | `str` | `state_core_trade_plan_candidate`. |
| `created_at_utc` | `str` | Creation timestamp. |
| `trade_plan_candidate_id` | `str` | Candidate id. |
| `action_intent_id` | `str` | Source action intent id. |
| `simulation_report_id` | `str` | Source simulation report id. |
| `proposal_id` | `str` | Source proposal id. |
| `source_action_intent_receipt_ref` | `str` | Current action intent receipt consumed by the write. |
| `source_action_preflight_report_hash` | `str` | Current recomputed preflight hash consumed by the write. |
| `source_simulation_report_receipt_ref` | `str` | Current simulation report receipt consumed by the write. |
| `source_action_preflight_status` | `str` | Current preflight status. |
| `source_action_preflight_finding_codes` | `list[str]` | Current preflight finding codes. |
| `acknowledged_preflight_warning_codes` | `list[str]` | Caller-acknowledged warn findings. |
| `plan_scope_snapshot` | `dict[str, Any]` | Direction, target/account/instrument scope, caps, constraints, and required authority level. |
| `candidate_status` | `str` | Local candidate status. |
| `validation_findings` | `list[str]` | Validation notes generated during the write. |
| `trade_plan_candidate` | `TradePlanCandidate` | Candidate-only pre-trade plan payload. |
| `preflight_snapshot.status` | `str` | Recomputed preflight status. |
| `preflight_snapshot.report_hash` | `str` | Recomputed preflight report hash. |
| `preflight_snapshot.warning_codes` | `list[str]` | Non-blocking warn codes present at write time. |
| `preflight_snapshot.finding_codes` | `list[str]` | Recomputed preflight finding codes. |
| `governance.execution_allowed` | `bool` | Always false. |
| `governance.authority_transition` | `bool` | Always false. |
| `governance.submitted_to_broker` | `bool` | Always false. |
| `governance.candidate_only` | `bool` | True. |
| `governance.not_order_ticket` | `bool` | True. |
| `governance.not_broker_instruction` | `bool` | True. |
| `governance.not_execution_authorization` | `bool` | True. |
| `governance.requires_authority_contract` | `bool` | True for any future execution path. |
| `governance.non_claims` | `list[str]` | Explicit trade-plan non-claims. |

### Capital Objective Fit Receipts

Location: `data/receipts/state-core/capital-objective-fits/`

| Field | Type | Meaning |
| --- | --- | --- |
| `receipt_id` | `str` | `receipt_<capital_objective_fit_id>`. |
| `kind` | `str` | `state_core_capital_objective_fit`. |
| `created_at_utc` | `str` | Creation timestamp. |
| `capital_objective_fit_id` | `str` | Objective-fit id. |
| `trade_plan_candidate_id` | `str` | Source candidate id. |
| `action_intent_id` | `str` | Source action intent id. |
| `simulation_report_id` | `str` | Source simulation report id. |
| `proposal_id` | `str` | Source proposal id. |
| `source_trade_plan_candidate_receipt_ref` | `str` | Current trade plan candidate receipt consumed by the write. |
| `source_action_intent_receipt_ref` | `str` | Current action intent receipt consumed by the write. |
| `source_action_preflight_report_hash` | `str` | Current recomputed preflight hash consumed by the write. |
| `source_simulation_report_receipt_ref` | `str` | Current simulation report receipt consumed by the write. |
| `objective_alignment` | `str` | `aligned`, `unclear`, or `conflicted`. |
| `objective_basis` | `dict[str, Any]` | Objective/mandate/IPS context cited by the fit. |
| `benefit_thesis` | `str` | Human-readable thesis for how the candidate may help or fail the objective. |
| `risk_budget_impact` | `dict[str, Any]` | Risk-budget impact summary. |
| `liquidity_impact` | `dict[str, Any]` | Liquidity impact summary. |
| `concentration_impact` | `dict[str, Any]` | Concentration impact summary. |
| `reversibility` | `dict[str, Any]` | Reversibility / staged-path assessment. |
| `opportunity_cost` | `dict[str, Any]` | Costs of acting, waiting, or choosing another path. |
| `alternatives_considered` | `list[dict[str, Any]]` | Safer or competing paths considered. |
| `major_uncertainties` | `list[str]` | Main unresolved uncertainties. |
| `user_questions` | `list[str]` | Questions for human review. |
| `recommended_next_safe_path` | `str` | Constructive next step that does not bypass governance. |
| `capital_objective_fit` | `CapitalObjectiveFit` | Objective-fit payload. |
| `evidence_snapshot` | `dict[str, Any]` | Candidate status, current receipts, simulation status, and preflight hash. |
| `governance.execution_allowed` | `bool` | Always false. |
| `governance.authority_transition` | `bool` | Always false. |
| `governance.submitted_to_broker` | `bool` | Always false. |
| `governance.creates_order_ticket` | `bool` | Always false. |
| `governance.suitability_certified` | `bool` | Always false. |
| `governance.approval_granted` | `bool` | Always false. |
| `governance.objective_fit_only` | `bool` | True. |
| `governance.not_investment_advice` | `bool` | True. |
| `governance.not_trade_plan_approval` | `bool` | True. |
| `governance.not_order_ticket` | `bool` | True. |
| `governance.not_broker_submission` | `bool` | True. |
| `governance.not_execution_authorization` | `bool` | True. |
| `governance.not_suitability_certification` | `bool` | True. |
| `governance.non_claims` | `list[str]` | Explicit objective-fit non-claims. |

### Trade Plan Review Gate Receipts

Location: `data/receipts/state-core/trade-plan-review-gates/`

| Field | Type | Meaning |
| --- | --- | --- |
| `receipt_id` | `str` | `receipt_<review_gate_id>`. |
| `kind` | `str` | `state_core_trade_plan_review_gate`. |
| `created_at_utc` | `str` | Creation timestamp. |
| `review_gate_id` | `str` | Review gate id. |
| `trade_plan_candidate_id` | `str` | Reviewed candidate id. |
| `action_intent_id` | `str` | Source action intent id. |
| `simulation_report_id` | `str` | Source simulation report id. |
| `proposal_id` | `str` | Source proposal id. |
| `source_trade_plan_candidate_receipt_ref` | `str` | Current trade plan candidate receipt consumed by the write. |
| `source_action_intent_receipt_ref` | `str` | Current action intent receipt consumed by the write. |
| `source_action_preflight_report_hash` | `str` | Current recomputed preflight hash consumed by the write. |
| `source_simulation_report_receipt_ref` | `str` | Current simulation report receipt consumed by the write. |
| `review_decision` | `str` | `allow_order_ticket_candidate_staging` or `deny_order_ticket_candidate_staging`. |
| `reviewer.reviewer_type` | `str` | `human` in v0. |
| `reviewer.reviewer_id` | `str` | Human reviewer identifier. |
| `review_context` | `dict[str, Any]` | Review context with order-ready/broker/execution fields rejected. |
| `review_findings` | `list[dict[str, Any]]` | Non-blocking review notes/findings. |
| `deny_reasons` | `list[str]` | Structured denial reasons when denied. |
| `candidate_validation_finding_codes` | `list[str]` | Warning/validation codes carried by the candidate. |
| `may_enter_order_ticket_candidate_staging` | `bool` | True only for an allowed gate; this is staging eligibility only. |
| `trade_plan_review_gate` | `TradePlanReviewGate` | Review-gate payload. |
| `evidence_snapshot` | `dict[str, Any]` | Candidate status, current receipts, and preflight hash. |
| `governance.execution_allowed` | `bool` | Always false. |
| `governance.authority_transition` | `bool` | Always false. |
| `governance.submitted_to_broker` | `bool` | Always false. |
| `governance.creates_order_ticket` | `bool` | Always false. |
| `governance.may_enter_order_ticket_candidate_staging` | `bool` | Mirrors staging eligibility. |
| `governance.review_gate_only` | `bool` | True. |
| `governance.not_order_ticket` | `bool` | True. |
| `governance.not_broker_submission` | `bool` | True. |
| `governance.not_execution_authorization` | `bool` | True. |
| `governance.not_suitability_certification` | `bool` | True. |
| `governance.not_authority_contract` | `bool` | True. |
| `governance.non_claims` | `list[str]` | Explicit review-gate non-claims. |

## Historical Live-Trading Experiment Receipts

The following receipts are retained to read archived OKX/Alpaca/market-access
experiments. They are not current mainline command paths and do not authorize
future delegated authority.

### OKX Live Attempt Receipt

Location: `data/receipts/okx-live/`

| Field | Type | Meaning |
| --- | --- | --- |
| `receipt_id` | `str` | OKX live attempt receipt id. |
| `kind` | `str` | `okx_live_order_attempt`. |
| `created_at_utc` | `str` | Creation timestamp. |
| `outcome` | `str` | `executed`, `blocked`, or `error`. |
| `request.module` | `str` | OKX CLI module. |
| `request.action` | `str` | OKX CLI action. |
| `request.args` | `list[str]` | Operator-supplied command args. |
| `request.attester` | `str` | Human attester. |
| `request.reason` | `str` | Written reason or plan ref. |
| `request.has_written_thesis` | `bool` | Whether operator asserted a written thesis exists. |
| `request.request_limit` | `float` | Per-request notional limit; can only tighten the governed ceiling. |
| `decision.allowed` | `bool` | Whether the live gate allowed the request. |
| `decision.guard_level` | `str` | Behavioral guard state. |
| `decision.notional` | `float | None` | Computed order notional. |
| `decision.configured_ceiling` | `float | None` | Human-owned default ceiling for live notional. |
| `decision.effective_ceiling` | `float | None` | Ceiling after traceable `ceiling.*` rule changes or owner certifications. |
| `decision.ceiling_provenance` | `dict[str, Any] | None` | Rule-change or owner-certification source that set the effective ceiling. |
| `decision.ignored_ceiling_changes` | `list[str]` | Ceiling changes ignored because they were not valid governed sources. |
| `decision.request_limit` | `float` | Per-request tightening limit. |
| `decision.enforced_cap` | `float | None` | Actual cap used for the live notional check: `min(request_limit, effective_ceiling)`. |
| `decision.request_limit_clamped_to_ceiling` | `bool` | Whether the request tried to exceed the effective ceiling and was clamped. |
| `decision.cap_invariant_holds` | `bool` | Always expected true: `enforced_cap <= effective_ceiling`. |
| `decision.market_access_cap` | `dict[str, Any] | None` | Governed aggregate market-access ceiling evidence. |
| `decision.market_access` | `MarketAccessDecision | None` | Aggregate daily limit decision; never execution authority. |
| `decision.blocking_reasons` | `list[str]` | Gate blockers. |
| `decision.guard_reasons` | `list[str]` | Behavioral guard reasons. |
| `okx_result_ref` | `str | None` | Future external result ref placeholder. |
| `market_access_entry_id` | `str | None` | Consumption entry id when the live write proceeded past the gate. |
| `error` | `str | None` | Error text for errored attempts. |
| `content_hash` | `str` | Hash of the receipt payload. |

### Alpaca Paper Strategy Receipt

Location: `data/receipts/alpaca-paper/`

| Field | Type | Meaning |
| --- | --- | --- |
| `timestamp_utc` | `str` | Receipt timestamp. |
| `dry_run` | `bool` | Whether no paper order was attempted. |
| `broker` | `str` | `alpaca`. |
| `environment` | `str` | `paper`. |
| `plan` | `StrategyOrderPlan` object | Written paper workflow plan. |
| `pre_trade.account_status` | `str | None` | Alpaca account status. |
| `pre_trade.trading_blocked` | `bool | None` | Broker trading-block flag. |
| `pre_trade.account_blocked` | `bool | None` | Broker account-block flag. |
| `pre_trade.positions_count_unknown_in_this_receipt` | `bool` | Explicit limitation. |
| `pre_trade.open_orders_before` | `int` | Open order count before attempt. |
| `risk_gate` | `GuardDecision` object | Behavioral guard decision. |
| `market_access` | `MarketAccessDecision`-like object | Aggregate paper limit decision and entry id; never execution authority. |
| `execution.attempted` | `bool` | Whether paper order was attempted. |
| `execution.order` | `dict | None` | Broker order response. |
| `execution.fetched` | `dict | None` | Broker order fetch response. |
| `execution.canceled` | `dict | None` | Broker cancel response. |
| `execution.open_orders_after` | `int | None` | Open order count after cancel. |
| `post_trade_assessment.workflow_passed` | `bool` | Whether paper workflow passed local checks. |
| `post_trade_assessment.not_investment_advice` | `bool` | Non-advice flag. |
| `post_trade_assessment.not_alpha_validation` | `bool` | Non-alpha-validation flag. |

### Market Access Consumption Receipt

Location: `data/receipts/market-access-ledger/`

| Field | Type | Meaning |
| --- | --- | --- |
| `receipt_id` | `str` | `receipt_<entry_id>`. |
| `kind` | `str` | `market_access_consumption`. |
| `created_at_utc` | `str` | Receipt timestamp. |
| `entry.entry_id` | `str` | Ledger entry id. |
| `entry.window_id` | `str` | UTC daily window id. |
| `entry.key.environment` | `Literal["paper", "live"]` | Environment bucket. |
| `entry.key.venue` | `str` | Venue/adaptor bucket, e.g. `okx`, `alpaca`, or `paper_review`. |
| `entry.key.operator` | `str` | Operator/attester identity used for the limit bucket. |
| `entry.key.account` | `str` | Account bucket. |
| `entry.key.symbol` | `str` | Symbol/instrument bucket. |
| `entry.notional` | `float` | Consumed notional. |
| `entry.source_ref` | `str | None` | Source order/request reference if available. |
| `ledger_ref` | `str` | Persisted ledger JSON path. |
| `window_usage_after.used_notional` | `float` | Aggregate notional after this entry. |
| `window_usage_after.used_order_count` | `int` | Aggregate order count after this entry. |
| `window_usage_after.remaining_notional` | `float | None` | Remaining configured notional after this entry. |
| `window_usage_after.remaining_orders` | `int | None` | Remaining configured order count after this entry. |
| `limit` | `MarketAccessLimit | None` | Limit used when recording the receipt. |
| `limit_evidence.configured_ceiling` | `float | None` | Human-owned default aggregate notional ceiling. |
| `limit_evidence.effective_ceiling` | `float | None` | Aggregate ceiling after traceable `ceiling.*` rule changes or owner certifications. |
| `limit_evidence.provenance` | `dict[str, Any] | None` | Rule-change or owner-certification source for the effective aggregate ceiling. |
| `limit_evidence.request_limit` | `float | None` | Per-request aggregate limit; can only tighten. |
| `limit_evidence.enforced_cap` | `float | None` | Actual aggregate notional cap used by the ledger. |
| `limit_evidence.cap_invariant_holds` | `bool | None` | Expected true when present: `enforced_cap <= effective_ceiling`. |
| `not_claimed` | `list[str]` | Explicit non-claims: no execution authorization, no compliance certification, no investment advice. |
| `execution_allowed` | `bool` | Always `false`; the ledger never grants order authority. |
| `content_hash` | `str` | Hash of the receipt payload. |

### Lesson Draft Receipt

Location: `data/receipts/lessons/`

The persisted JSON is a `LessonDraft` model.

| Field | Type | Meaning |
| --- | --- | --- |
| `draft_id` | `str` | Draft id. |
| `created_at_utc` | `str` | Draft timestamp. |
| `window_days` | `int` | Receipt lookback window. |
| `receipts_scanned` | `int` | Count of scanned receipts. |
| `sources` | `list[str]` | Receipt source directories scanned. |
| `status_counts` | `dict[str, int]` | Counts by source receipt status. |
| `quality_failure_count` | `int` | Count of quality failures seen. |
| `top_blocking_reasons` | `list[tuple[str, int]]` | Most common blocking reasons. |
| `observations` | `list[str]` | Deterministic draft observations. |
| `proposed_rule_changes` | `list[str]` | Draft rule-change seeds; not applied. |
| `llm_narrative` | `str | None` | Optional LLM-drafted narrative. |
| `llm_provider` | `str | None` | Drafting provider if LLM-assisted. |
| `receipt_refs` | `list[str]` | Receipt refs supporting the draft. |
| `promotion_state` | `str` | Draft promotion state, default `draft`. |
| `promotion_rule` | `str` | Text reminder that a human must promote or reject. |

### Rule Change Promotion Receipt

Location: `data/receipts/rule-changes/`

| Field | Type | Meaning |
| --- | --- | --- |
| `receipt_id` | `str` | `receipt_<rule_change_id>`. |
| `kind` | `str` | `rule_change_promotion`. |
| `created_at_utc` | `str` | Rule-change creation timestamp. |
| `rule_change.rule_change_id` | `str` | Rule change id. |
| `rule_change.rule_target` | `str` | Target rule/checklist/threshold path. |
| `rule_change.change_kind` | `Literal["threshold", "checklist", "allowlist", "prompt_template"]` | Change category. |
| `rule_change.old_value` | `Any` | Previous value if supplied. |
| `rule_change.new_value` | `Any` | New value. |
| `rule_change.rationale` | `str` | Human-written rationale. |
| `rule_change.attester` | `str` | Human attester. |
| `rule_change.lesson_draft_id` | `str | None` | Source lesson draft id. |
| `rule_change.lesson_doc_ref` | `str | None` | Promoted lesson doc ref. |
| `rule_change.receipt_refs` | `list[str]` | Source receipts inherited from the lesson. |
| `rule_change.status` | `Literal["active", "reverted"]` | Rule change status. |
| `lineage.lesson_draft_id` | `str | None` | Source lesson draft id. |
| `lineage.lesson_doc_ref` | `str | None` | Source lesson doc ref. |
| `lineage.receipt_count` | `int` | Count of source receipts. |

### Control Owner Certification Receipt

Location: `data/receipts/control-certifications/`

| Field | Type | Meaning |
| --- | --- | --- |
| `receipt_id` | `str` | `receipt_<certification_id>`. |
| `kind` | `str` | `control_owner_certification`. |
| `created_at_utc` | `str` | Certification attempt timestamp. |
| `certification.certification_id` | `str` | Control certification id. |
| `certification.control_owner` | `str` | Named human control owner; never empty. |
| `certification.review_cadence_days` | `int` | Review cadence in days. |
| `certification.next_review_due_utc` | `str` | Next due date for owner review. |
| `certification.controls_in_force` | `list[str]` | Baseline invariant ids/titles. |
| `certification.authorized_ceilings` | `dict[str, float]` | Optional explicit `ceiling.*` values authorized by this named-owner receipt. |
| `certification.baseline_passed` | `bool` | Whether the baseline guard tests passed. |
| `certification.baseline_evidence` | `dict[str, Any]` | Test modules, counts, return code, and output tails. |
| `certification.status` | `Literal["certified", "not_certified"]` | Honest certification status. |
| `certification.non_certification_statement` | `str` | Disclaimer: not legal/compliance/release/live authorization. |
| `lineage.baseline_test_modules` | `list[str]` | Test modules used as evidence. |
| `lineage.baseline_returncode` | `int` | Baseline subprocess return code. |
| `lineage.control_count` | `int` | Number of baseline invariants listed. |
| `not_claimed` | `list[str]` | Explicit non-claims. |

### Governance And Hardening Receipts

Locations:

```text
data/receipts/repo-intelligence/
data/receipts/quality-governance/
data/receipts/release-preflight/
data/receipts/governance-dashboard/
data/receipts/hardening/
data/receipts/receipt-usage-audit/
```

These receipts are direct JSON payloads. They are release/governance evidence,
not trading authority.

| Receipt family | Key fields |
| --- | --- |
| Repo intelligence | `workflow`; `generated_at`; `source`; `file_inventory`; `inventory_summary`; `task_graph`; `import_graph`; `test_map`; `blast_radius`; `security_surface`; `execution_allowed` |
| Quality governance | `workflow`; `generated_at`; `source`; `check_results`; `repo_intelligence`; `security_gate`; `redteam_gate`; `performance_baseline`; `release_decision` |
| Release preflight | `workflow`; `generated_at`; `source`; `quality`; `supply_chain`; `release_gate` |
| Governance dashboard | `workflow`; `generated_at`; `source`; `dashboard_status`; `receipt_refs`; `repo_intelligence`; `quality_governance`; `hardening_gate`; `redteam_boundary`; `release_preflight`; `performance_baseline`; `execution_allowed`; `requires_human_review` |
| Hardening gate | `workflow`; `generated_at`; `execution_allowed`; `release_blocked`; `checks` |
| pip-audit summary | `dependency_count`; `vulnerability_count`; `vulnerable_package_count`; `vulnerable_packages`; `vulnerabilities` |
| gitleaks/trivy summaries | Tool-specific redacted scanner fields plus vulnerability/secret counts where available. |
| Receipt usage audit | `generated_at`; `receipt_roots`; `audited_count`; `durable_consumed_receipts`; `candidate_or_draft_receipts`; `generated_runtime_or_unlinked_receipts`; `missing_references`; `limitations` |

### Other Runtime Direct JSON Receipts

Locations:

```text
data/receipts/market-cockpit/
data/receipts/project-governance-adapter/
data/receipts/repository-governance/
data/receipts/engineering-delivery/
data/receipts/alpaca-paper-dca/
data/receipts/alpaca-paper-langgraph/
data/receipts/rust/
```

These receipts are runtime, governance, paper-trading, or legacy evidence. They
do not grant live trading authority.

| Receipt family | Key fields |
| --- | --- |
| Market cockpit | `workflow`; `generated_at`; `source`; `symbols`; `config`; `receipt_surface`; `review_queue`; `broken_paths`; `degraded_paths`; `execution_allowed` |
| Project governance adapter | `workflow`; `generated_at`; `source`; `project`; `status`; `stage_statuses`; `claims`; `not_claimed`; `remaining_debt`; `quality_summary`; `delivery_summary`; `cognitive_summary`; `compatibility_contract`; `receipt_ref`; `draft` |
| Repository governance | `workflow`; `generated_at`; `repository`; `default_branch`; `viewer_permission`; `branch_protection_enabled`; `rulesets_configured`; `security_policy_enabled`; `dependabot_config_present`; `codeql_workflow_present`; `scorecard_workflow_present`; `license_configured`; `decision`; `notes`; `execution_allowed` |
| Engineering delivery | `workflow`; `timestamp_utc`; `receipt_id`; `status`; `snapshot`; `lineage`; `remaining_debt` |
| Engineering delivery `snapshot` | `snapshot_id`; `timestamp_utc`; `workflow`; `goal`; `scope`; `non_goals`; `source_ref`; `proposal_ref`; `module_refs`; `planned_files`; `changed_files`; `change_type`; `docs_updated`; `checks`; `design_gate`; `quality_gate`; `success_criteria`; `output_hash`; `execution_allowed` |
| Engineering delivery `lineage` | `source_ref`; `proposal_ref`; `module_refs`; `transform_version` |
| Alpaca paper DCA | `timestamp_utc`; `dry_run`; `broker`; `environment`; `market_open`; `plan`; `pre_trade`; `risk_gate`; `execution` |
| Alpaca paper DCA `plan` | `schedule_id`; `symbol`; `side`; `qty`; `order_type`; `latest_price`; `method`; `thesis`; `invalidation`; `not_investment_advice` |
| Alpaca paper DCA `pre_trade` | `account_status`; `buying_power`; `trading_blocked` |
| Alpaca paper DCA `risk_gate` | `level`; `reasons`; `required_actions`; `trade_allowed` |
| Alpaca paper DCA `execution` | `attempted`; `order`; `error` |
| Alpaca paper LangGraph | `workflow`; `timestamp_utc`; `market_data_summary`; `state` |
| Alpaca paper LangGraph `market_data_summary` | `provider`; `symbols`; `rows`; `last_close` |
| Alpaca paper LangGraph `state` | `universe`; `research`; `order_plan`; `order_qty`; `risk_gate`; `account`; `execute`; `execution` |
| Legacy rust receipt | `timestamp_unix`; `kind`; `symbol`; `status`; `writer` |

## Layer Receipt Locations

| Layer/surface | Normalized output | Receipt output | Notes |
| --- | --- | --- | --- |
| Market data | `data/normalized/market-data/` | `data/receipts/market-data/` | Captures raw/normalized hashes and quality backend. |
| State Core IPS | n/a | `data/receipts/state-core/ips/` | Current user-owned policy statement evidence. |
| Capital mandates | n/a | `data/receipts/state-core/capital-mandates/` | Current human-attested policy domain; not authority. |
| Action intents | n/a | `data/receipts/state-core/action-intents/` | Current candidate-only capital action bridge. |
| Action intent simulations | n/a | `data/receipts/state-core/action-intent-simulations/` | Current preflight-bound descriptive simulation evidence. |
| Trade plan candidates | n/a | `data/receipts/state-core/trade-plan-candidates/` | Current candidate-only pre-trade plan evidence. |
| Lesson drafts | `docs/lessons/drafts/` | `data/receipts/lessons/` | Drafts only; human promotion required. |
| Rule changes | `data/state/rule-changes/` | `data/receipts/rule-changes/` | Human-promoted lesson-to-rule lineage. |
| Market cockpit | n/a | `data/receipts/market-cockpit/` | Operator dashboard evidence only. |
| Project governance adapter | n/a | `data/receipts/project-governance-adapter/` | Project-governance compatibility evidence. |
| Repository governance | n/a | `data/receipts/repository-governance/` | Repository safety/governance evidence. |
| Engineering delivery | n/a | `data/receipts/engineering-delivery/` | Delivery receipts for scoped engineering work. |
| Indicators | `data/normalized/indicators/` | `data/receipts/indicators/` | Historical ten-layer feature evidence. |
| Events | `data/normalized/events/` | `data/receipts/events/` | Historical ten-layer event evidence. |
| Interpretation | `data/normalized/interpretations/` | `data/receipts/interpretations/` | Historical ten-layer interpretation evidence. |
| Hypotheses | `data/normalized/hypotheses/` | `data/receipts/hypotheses/` | Historical ten-layer hypothesis evidence. |
| Validation | `data/normalized/validations/` | `data/receipts/validations/` | Historical ten-layer validation evidence. |
| Proposal | `data/normalized/proposals/` | `data/receipts/proposals/` | Historical ten-layer proposal evidence. |
| Risk Gate | `data/normalized/risk-gates/` | `data/receipts/risk-gates/` | Historical ten-layer risk-gate evidence. |
| Execution | `data/normalized/executions/` | `data/receipts/executions/` | Historical ten-layer order lifecycle evidence. |
| Post trade | `data/normalized/post-trade/` | `data/receipts/post-trade/` | Historical ten-layer reconciliation evidence. |
| Daily evidence | `data/normalized/daily-evidence/` | `data/receipts/daily-evidence/` | Historical ten-layer bundle evidence. |
| OKX live attempts | n/a | `data/receipts/okx-live/` | Archived live-trading experiment evidence. |
| Alpaca paper DCA | n/a | `data/receipts/alpaca-paper-dca/` | Archived paper DCA workflow evidence. |
| Alpaca paper LangGraph | n/a | `data/receipts/alpaca-paper-langgraph/` | Archived paper LangGraph workflow evidence. |
| Legacy rust receipt | n/a | `data/receipts/rust/` | Archived Rust-era receipt shape; retained for audit history. |

## Receipt Reading Checklist

When reviewing a receipt, check:

- Which upstream `receipt_ref` or `payload_ref` it consumed.
- Whether `quality.ok` or equivalent quality status is true.
- Whether `execution_allowed` is false or absent because the surface is not an
  execution authority.
- Which backend/tool/version produced the evidence.
- Whether the receipt lists limitations, review questions, or forbidden outputs.
- Whether a human attester is present where a rule change or live mutation is
  involved.

## Red Lines

- A receipt is not a trading signal.
- A receipt is not proof of profitable alpha.
- A receipt is not an authorization to bypass Risk Gate.
- A generated lesson draft receipt is not a promoted rule.
- An external provenance store may index receipts later, but it must not replace
  FinHarness receipt semantics.
