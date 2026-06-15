# How To Add A Mature-Wheel Adapter

Use this when replacing local heavy logic with a mature library while preserving
FinHarness governance.

## Target Shape

```text
mature wheel does the heavy work
-> FinHarness adapter normalizes input/output
-> FinHarness quality/lineage/receipt records evidence
-> Risk Gate / trading guard / human review keep authority
```

## Steps

1. Identify the local behavior being replaced.
2. Write characterization tests for the current caller contract.
3. Add the smallest adapter around the mature library.
4. Add tests proving the adapter path is exercised.
5. Keep the existing FinHarness public interface stable where possible.
6. Record backend/tool name and version in output or receipt when relevant.
7. Add boundary tests for `execution_allowed=false`, no live authority, no final
   sizing, and no order language where applicable.
8. Update docs:
   - module doc under `docs/modules/`;
   - interface reference in [../reference/interfaces.md](../reference/interfaces.md);
   - how-to if users need a new task recipe;
   - architecture/spec doc if this is a new interface.
9. Run targeted tests first, then `task check` when the blast radius warrants it.

## Adapter Acceptance Checklist

- Existing behavior is characterized.
- Mature library path is used in tests.
- FinHarness still owns quality, lineage, receipt, and permission boundary.
- Human-set caps are not widened by optimizer output.
- Live execution stays blocked unless a separate human-approved policy changes.
- The output names what it is not allowed to do.

## Examples

| Interface | Mature wheel | Local boundary |
| --- | --- | --- |
| DataQualityInterface | Pandera | strict OHLCV validation plus FinHarness soft verdicts |
| ResearchInterface | vectorbt | backtest evidence without proposal authority |
| PortfolioRiskInterface | Riskfolio-Lib | requested concentration only; mandate cap unchanged |
| ExecutionEngineInterface | NautilusTrader | typed paper order shaping; live blocked |

## What Not To Do

- Do not add a production dependency without explicit user approval.
- Do not move caps, permissions, or live gates into the mature library.
- Do not treat successful adapter output as a trade recommendation.
- Do not delete `trading_guard`, `risk_gate`, lesson-to-rule lineage, or
  receipts because a library has similar-sounding features.
