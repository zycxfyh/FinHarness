# Review: FinHarness C1-C4 B4 Loop Execution

Date: 2026-06-14
Status: DEGRADED evidence-bound execution receipt
Scope: C1-C4 follow-up after B4 lineage, effective guard thresholds, validation metrics, and receipt usage audit

## ABC Frame

```text
A:
  The B4 machinery existed, but rules:audit had 0 rule changes, effective guard
  provenance was empty, validation had no cached price history, and receipt
  usage audit only reported consumed/unreferenced status.

B:
  Run one real loop: lesson draft -> human-promoted rule change -> effective
  guard behavior; give validation real cached price data; classify the receipt
  surface into durable/draft/runtime/missing layers.

C:
  C1 promote a real lesson into a traceable guard-threshold rule change.
  C2 verify that the promoted rule changes a guard decision.
  C3 generate cached price history and verify realized-move validation on it.
  C4 add evidence-surface layering to receipt usage audit.

R:
  Commands and artifacts below.
```

## C1: Lesson Promotion

Generated a current lesson draft:

```text
task lessons:draft -- --window-days 60
draft_id: lesson_draft_31f5846e7aa9
receipts_scanned: 747
quality_failure_count: 37
doc_ref: docs/lessons/drafts/2026-06-13-lesson_draft_31f5846e7aa9.md
receipt_ref: data/receipts/lessons/lesson_draft_31f5846e7aa9.json
```

Promoted the draft into a dated lesson:

```text
docs/lessons/2026-06-14-loss-cooldown-tightening.md
```

Promoted rule change:

```text
rule_change_id: rulechg_20260613T165140Z_ecd766ed
rule_target: guard.min_minutes_between_trades_after_loss
change_kind: threshold
old_value: 30
new_value: 45
attester: operator-chat-2026-06-14
lesson_doc_ref: docs/lessons/2026-06-14-loss-cooldown-tightening.md
receipt_refs: 100
traceable: true
```

The rule change is conservative: it extends the cooldown after a losing trade.
It does not authorize trading.

## C2: Guard Effect

`task rules:audit` reported:

```text
count: 1
untraceable_ids: []
b4_lineage_ok: true
```

The promoted rule changed a concrete guard decision:

```text
state:
  drawdown_pct: 0
  consecutive_losses: 1
  minutes_since_last_trade: 40
  planned_trade_has_written_thesis: true

default threshold:
  min_minutes_between_trades_after_loss: 30
  level: clear
  trade_allowed: true

effective threshold:
  min_minutes_between_trades_after_loss: 45
  provenance:
    min_minutes_between_trades_after_loss: rulechg_20260613T165140Z_ecd766ed
  level: caution
  trade_allowed: false
  reason: only 40 minutes since a losing trade; minimum is 45
```

`task trading:reset-check -- --consecutive-losses 1 --minutes-since-last-trade 40 --thesis`
exited non-zero as a gate and printed the effective threshold plus provenance.
That non-zero exit is the expected blocking behavior.

## C3: Validation Data

Generated cached price history through the project data-entry path:

```text
task data:entry -- --symbol NVDA --start 2025-01-01 --end 2025-06-30
history_rows: 121
history_path: data/cache/nvda_history.csv
risk_eval_ok: true
data_source: OpenBB:yfinance quote + yfinance/Yahoo Finance history
```

Using the existing full hypothesis receipt
`data/receipts/hypotheses/receipt_hyps_20260613T163634Z_f09e67ae.json`,
validation produced:

```text
jobs: 2
results: 18
quality_ok: true
event_reaction method: realized_move_over_window
event_reaction count: 2
result: inconclusive
disconfirms_hypothesis: false
price_count: 121
```

Degradation note:

```text
task validation:graph -- --symbols SPY --max-records 2 --max-hypotheses 1
task validation:graph -- --symbols NVDA --max-records 3 --max-hypotheses 1
```

Both graph invocations produced 0 validation jobs because the fresh graph run
did not produce hypotheses for those inputs. C3 therefore proves the validation
metric and bundle path with cached data, not that every fresh graph invocation
will produce a hypothesis to validate.

## C4: Receipt Surface

Receipt usage audit now includes `evidence_layer` and
`summary.evidence_surface_counts`.

Current audit output:

```text
task receipt:usage-audit
receipt_count: 1441
durable_consumed: 33
candidate_or_draft: 30
generated_runtime_or_unlinked: 1378
missing_reference: 41
```

This is a classification for cleanup planning. It is not a deletion decision.

## Non-Claims

```text
No live trade was authorized.
No alpha or profitability claim is made.
The promoted rule only tightens an existing behavioral guard threshold.
Validation on cached prices does not prove mechanism or edge.
Receipt usage layering does not prove receipt correctness.
```

## Remaining Debt

```text
- Risk-gate thresholds/checklists still do not read from the rule-change ledger.
- Fresh validation graph invocations can still produce 0 hypotheses/jobs.
- Cached market data under data/cache/ is runtime evidence, not durable source.
- Generated runtime receipts still dominate the local receipt surface.
```
