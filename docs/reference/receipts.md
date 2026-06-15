# Receipt Reference

Receipts are durable evidence roots for FinHarness workflows. They record what
was produced, which inputs and tools were used, where artifacts were written, and
what the output does not authorize.

Receipts are evidence, not proof of correctness and not trading permission.

## Common Shape

Most layer receipts follow this pattern:

| Field | Meaning |
| --- | --- |
| `receipt_id` | Stable id for this receipt instance. |
| `created_at_utc` | Creation timestamp in UTC. |
| `kind` | Receipt category, for example `market_data_ingestion` or `execution_processing`. |
| `stage_flow` or map field | Human-readable stage mapping for how the result was produced. |
| `snapshot` | The typed output snapshot for the layer. |
| `status` | Local status such as `ok`, `warning`, or `failed` where present. |

Most snapshots include:

| Field | Meaning |
| --- | --- |
| `*_snapshot_id` | Layer-specific snapshot id. |
| `as_of_utc` | Snapshot timestamp. |
| `quality` | Layer quality gates and notes. |
| `lineage` | Input refs, backend/method, transform version, hashes, output refs. |
| `payload_ref` | Path to normalized output payload. |
| `receipt_ref` | Path to the receipt JSON. |
| `execution_allowed` | Usually `false`; evidence does not become execution authority. |
| `review_questions` | Human review prompts where applicable. |

## Layer Receipt Locations

| Layer/surface | Normalized output | Receipt output | Notes |
| --- | --- | --- | --- |
| Market data | `data/normalized/market-data/` | `data/receipts/market-data/` | Captures raw/normalized hashes and quality backend. |
| Indicators | `data/normalized/indicators/` | `data/receipts/indicators/` | Feature evidence only. |
| Events | `data/normalized/events/` | `data/receipts/events/` | Event evidence only. |
| Interpretation | `data/normalized/interpretations/` | `data/receipts/interpretations/` | Source-backed interpretation only. |
| Hypotheses | `data/normalized/hypotheses/` | `data/receipts/hypotheses/` | Falsifiable hypothesis evidence only. |
| Validation | `data/normalized/validations/` | `data/receipts/validations/` | Proposal handoff still requires human review. |
| Proposal | `data/normalized/proposals/` | `data/receipts/proposals/` | Structured candidates, no execution authority. |
| Risk Gate | `data/normalized/risk-gates/` | `data/receipts/risk-gates/` | Paper review decision, no live authority or final sizing. |
| Execution | `data/normalized/executions/` | `data/receipts/executions/` | Order lifecycle evidence, live blocked in MVP. |
| Post trade | `data/normalized/post-trade/` | `data/receipts/post-trade/` | Reconciliation evidence, no order creation. |
| OKX live attempts | n/a | `data/receipts/okx-live/` | Writes receipts for blocked, errored, and executed attempts. |
| Lesson drafts | `docs/lessons/drafts/` | `data/receipts/lessons/` | Drafts only; human promotion required. |
| Rule changes | `data/state/rule-changes/` | `data/receipts/rule-changes/` | Human-promoted lesson-to-rule lineage. |

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
