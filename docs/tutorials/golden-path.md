# Golden Path Tutorial

This is the supported first-run path for FinHarness. It is written as a tutorial,
not an architecture essay: run the commands in order, compare the output shape,
and notice which safety boundary each step proves.

The path below was dogfooded from `/root/projects/finharness` on 2026-06-15.
Output ids and receipt filenames change on every run; the important fields are
called out under each step.

## Before You Start

Use the project task entry points:

```bash
cd /root/projects/finharness
task --list
```

If this is a fresh checkout, `task setup` syncs dependencies from lockfiles. That
can install or update local packages, so run it deliberately. The golden path
itself does not need a live brokerage account or API key.

## What This Path Proves

By the end, you should have seen:

- mature finance libraries load locally;
- real SPY feature snapshots produced through mature indicators and data-quality
  checks;
- validation evidence recorded without becoming a trade recommendation;
- Risk Gate keeping mandate/cap/live boundaries in place;
- Execution refusing to create an order request by default;
- live mode explicitly blocked before submit;
- lessons drafted from receipts without auto-promoting a rule;
- security and agent-tool checks producing bounded evidence.

It does not prove profitable alpha, live-trading authority, broker compliance,
best execution, tax/accounting correctness, or institutional-grade data quality.

## Step 1 - Check Mature Wheels

```bash
task wheels:check
```

Expected shape:

```text
installed_core_wheels
backtrader=1.9.78.123
pandas=2.3.3
yfinance=1.4.0
agents=Agent/Runner/function_tool
deepeval=LLMTestCase
openbb=App

target_top_wheels
vectorbt=installed
nautilus_trader=installed
riskfolio=installed
quantstats=installed
```

Boundary proven: FinHarness is using mature wheels for heavy mechanics. This
does not make any wheel an authority to trade.

## Step 2 - Build Feature Snapshots

Run MACD:

```bash
task feature:macd
```

Expected shape:

```text
symbol=SPY
indicator=macd
rows=121
output_path=data/features/spy_macd_snapshot.json
execution_allowed=false
```

Run Squeeze:

```bash
task feature:squeeze
```

Expected shape:

```text
symbol=SPY
indicator=squeeze
rows=121
output_path=data/features/spy_squeeze_snapshot.json
execution_allowed=false
```

Boundary proven: indicators produce evidence snapshots only. The feature layer
does not authorize orders, sizing, or live execution.

## Step 3 - Run Validation Evidence

```bash
task validation:graph
```

Expected shape:

```json
{
  "workflow": "langgraph_validation_v1",
  "job_count": 10,
  "result_count": 100,
  "quality_ok": true,
  "execution_allowed": false,
  "proposal_handoff": [
    "human review required before proposal."
  ],
  "consumer_handoff": {
    "forbidden_outputs": [
      "orders",
      "position sizing",
      "broker instructions",
      "execution permission",
      "trade recommendation"
    ]
  }
}
```

Boundary proven: vectorbt/backtest-style research can enter the flow as evidence,
but validation still says `execution_allowed=false` and requires human review
before proposal promotion.

## Step 4 - Run Risk Gate

```bash
task risk-gate:graph
```

Expected shape:

```json
{
  "workflow": "langgraph_risk_gate_v1",
  "candidate_count": 10,
  "decision_count": 10,
  "quality_ok": true,
  "execution_allowed": false,
  "consumer_handoff": {
    "forbidden_outputs": [
      "orders",
      "live execution approval",
      "final sizing",
      "broker instructions"
    ]
  },
  "review_questions": [
    "Did any decision imply live execution authority?"
  ]
}
```

Boundary proven: Risk Gate records review decisions, checks mandate/caps, and
keeps live approval and final sizing out of scope.

## Step 5 - Run Execution Graph

```bash
task execution:graph
```

Expected shape:

```json
{
  "workflow": "langgraph_execution_v1",
  "mode": "dry_run",
  "intent_count": 0,
  "order_request_count": 0,
  "event_count": 1,
  "final_status": "blocked_before_submit",
  "quality_ok": true,
  "execution_allowed": false
}
```

Boundary proven: the normal execution path does not silently create an order. It
produces a receipt and review questions instead.

## Step 6 - Prove Live Mode Is Blocked

This command deliberately asks for live mode. A non-zero exit is expected because
the graph refuses the live path.

```bash
uv run python scripts/run_execution_graph.py --live --execute --attest-human-review
```

Expected shape:

```json
{
  "mode": "live",
  "order_request_count": 0,
  "event_count": 1,
  "final_status": "blocked_before_submit",
  "quality_ok": false,
  "execution_allowed": false
}
```

The generated execution snapshot should include:

```text
blocked_before_submit {'reason': 'live execution is blocked in Layer 9 MVP'}
```

Boundary proven: even with `--live`, `--execute`, and human-review attestation
flags, this MVP execution graph blocks before submit and creates no live order
request.

## Step 7 - Draft Lessons From Receipts

```bash
task lessons:draft
```

Expected shape:

```json
{
  "draft_id": "lesson_draft_...",
  "receipts_scanned": 4422,
  "quality_failure_count": 217,
  "doc_ref": "docs/lessons/drafts/2026-06-15-lesson_draft_....md",
  "receipt_ref": "data/receipts/lessons/lesson_draft_....json"
}
```

Boundary proven: Loop 4 can mine receipts for lesson candidates, but this creates
a draft only. A rule change still needs a human promotion through the
lesson-to-rule ledger.

## Step 8 - Run Security Audit

```bash
task security:audit
```

Expected shape:

```json
{
  "workflow": "finharness_hardening_gate_v1",
  "execution_allowed": false,
  "release_blocked": false,
  "checks": [
    {
      "tool": "pip-audit",
      "returncode": 0,
      "vulnerability_count": 0,
      "release_blocked": false
    }
  ]
}
```

Boundary proven: security checks produce release and evidence signals, not
trading authority.

## Step 9 - Inspect Agent Tools

```bash
task agent:describe
```

Expected shape:

```json
{
  "agent": "Finance Research Harness Agent",
  "tools": [
    "get_quote_snapshot",
    "get_historical_risk_metrics",
    "evaluate_latest_risk_note"
  ]
}
```

Boundary proven: agent tooling is present, but tools are bounded research and
risk-note tools. They are not order-entry tools.

## Step 10 - Optional Full Local Check

```bash
task check
```

Use this before handing changes to another reviewer. It is necessary, but not
sufficient: dogfood matters because it walks the real workflow and reads the
receipts, while `task check` mostly proves tests and standard experiments pass.

## What To Read Next

- Policy rules: [Policy Contract](../architecture/policy-contract.md)
- Receipt/provenance surface: [Evidence Inventory](../architecture/evidence-inventory.md)
- Mature-wheel replacement plan: [Mature Wheel Control Plane](../architecture/mature-wheel-control-plane.md)
- Full ten-layer map: [Ten Layer LangGraph Map](../architecture/ten-layer-langgraph-map.md)

## Completion Checklist

- [ ] I saw mature wheels import successfully.
- [ ] I saw feature snapshots keep `execution_allowed=false`.
- [ ] I saw validation require human review before proposal.
- [ ] I saw Risk Gate forbid orders, live approval, and final sizing.
- [ ] I saw execution produce `blocked_before_submit`.
- [ ] I explicitly checked live mode and saw it blocked.
- [ ] I understand lesson drafts are not automatic rule changes.
- [ ] I understand passing this tutorial is evidence, not trading permission.
