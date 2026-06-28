# Policy Contract Inventory

> Historical / superseded reference (2026-06-28): this policy inventory was for
> the retired ten-layer execution/risk-gate/live-trading stack. Current machine
> policy rules live in `tests/_policy_registry.py` and are listed by
> `task governance:policies`.

This document is the Phase 5 PolicyInterface contract. It inventories the
discipline rules already enforced in code so they can be reviewed in one place.
It is not an execution authority. If this document and code disagree, code is
the authority and this document must be corrected before any policy-engine work
is considered.

## Scope

Policy rules here cover behavior stops, mandate checks, permission boundaries,
human attestation, live-write gates, order-language restrictions, and
lesson-to-rule lineage. Mature policy engines may help express or audit these
rules later, but they must not replace `trading_guard`, `risk_gate`, human
attestation, receipts, or the live-execution block.

## Rule Inventory

| Rule id | Source | Check | Fail-closed default | Change authority |
| --- | --- | --- | --- | --- |
| TG-001 | `src/finharness/trading_guard.py:12`, `src/finharness/trading_guard.py:48`, `src/finharness/trading_guard.py:89` | Hard-stop drawdown breaches stop new trades and require review actions. | `trade_allowed=False` when hard stop is breached. | Human attester through reviewed code or promoted rule change. |
| TG-002 | `src/finharness/trading_guard.py:16`, `src/finharness/trading_guard.py:61`, `src/finharness/trading_guard.py:89` | Consecutive losses at the hard threshold stop new trades. | `trade_allowed=False` when loss count reaches the hard stop. | Human attester through reviewed code or promoted rule change. |
| TG-003 | `src/finharness/trading_guard.py:18`, `src/finharness/trading_guard.py:74`, `src/finharness/trading_guard.py:105` | After a losing trade, a cooldown breach blocks trading until review/cooldown actions are satisfied. | Caution returns `trade_allowed=False`. | Human attester through reviewed code or promoted rule change. |
| TG-004 | `src/finharness/trading_guard.py:21`, `src/finharness/trading_guard.py:85`, `src/finharness/trading_guard.py:105` | A planned trade needs a written thesis. | Missing thesis returns caution with `trade_allowed=False`. | Human attester; AI can draft but cannot attest. |
| RG-001 | `src/finharness/risk_gate.py:83`, `src/finharness/risk_gate.py:410`, `src/finharness/risk_gate.py:516` | A mandate id and mandate text must exist before a risk-gate decision can approve paper review. | Missing mandate is a blocking failed check. | Human owner of mandate text; changes require review. |
| RG-002 | `src/finharness/risk_gate.py:90`, `src/finharness/risk_gate.py:103`, `src/finharness/risk_gate.py:417` | Symbol and action type must be allowlisted. | Non-allowlisted symbol/action is a blocking failed check. | Human owner of allowlist; no optimizer may expand it. |
| RG-003 | `src/finharness/risk_gate.py:111`, `src/finharness/risk_gate.py:427`, `src/finharness/risk_gate.py:581` | Risk Gate cannot grant live execution authority. | `live_execution_allowed=False`; live-mode request blocks. | Human policy change only; not a model or adapter decision. |
| RG-004 | `src/finharness/risk_gate.py:115`, `src/finharness/risk_gate.py:437`, `src/finharness/risk_gate.py:527` | Requested notional must stay within the configured paper cap. | Over-cap request is a blocking failed check. | Human-set mandate/config cap; tools may request, never widen. |
| RG-005 | `src/finharness/risk_gate.py:117`, `src/finharness/risk_gate.py:444`, `src/finharness/portfolio_risk.py:27` | Riskfolio allocation weight may populate requested concentration only; the mandate cap stays in `RiskGateContext`. | Over-cap concentration is a blocking failed check. | Human-set concentration cap; Riskfolio is evidence, not authority. |
| RG-006 | `src/finharness/risk_gate.py:120`, `src/finharness/risk_gate.py:464`, `src/finharness/risk_gate.py:527` | Drawdown and consecutive-loss state must not trip the risk hard stop. | Hard-stop state is a blocking failed check. | Human rule owner; thresholds may change only through reviewed policy/rule-change flow. |
| RG-007 | `src/finharness/risk_gate.py:124`, `src/finharness/risk_gate.py:481`, `src/finharness/risk_gate.py:527` | Behavior reset state must stop the workflow. | `behavior_reset_required=True` is a blocking failed check. | Human clears reset; AI cannot clear it. |
| RG-008 | `src/finharness/risk_gate.py:125`, `src/finharness/risk_gate.py:488`, `src/finharness/risk_gate.py:539` | Scenario notes and review context must be present. | Missing scenario evidence downgrades to more-evidence review, not approval. | Human reviewer controls acceptance. |
| RG-009 | `src/finharness/risk_gate.py:39`, `src/finharness/risk_gate.py:495`, `src/finharness/risk_gate.py:650` | Risk-gate output and candidate rationale must not contain direction, routing, final sizing, or execution language. | Blocked language makes quality fail and may block the decision. | Human safety owner; language list changes need review. |
| RG-010 | `src/finharness/risk_gate.py:111`, `src/finharness/risk_gate.py:503`, `src/finharness/risk_gate.py:648` | Human review attestation is mandatory before paper review approval. | Default `human_review_attested=False`; missing attestation returns `needs_human_review`. | Human attester only. |
| OKX-001 | `src/finharness/okx_policy.py:28`, `src/finharness/okx_cli.py:156` | Live reads are restricted to read-only allowlisted module/action pairs. | Unknown or mutating read command raises `OkxCliError`. | Human owner of venue allowlist. |
| OKX-002 | `src/finharness/okx_policy.py:51`, `src/finharness/okx_cli.py:99`, `src/finharness/okx_cli.py:174` | Mutating OKX commands require explicit mutation approval path. | Mutation without `allow_mutation=True` raises `OkxCliError`. | Human/operator approval; not available to autonomous flow. |
| OKX-003 | `src/finharness/okx_cli.py:50`, `src/finharness/okx_cli.py:61`, `src/finharness/okx_cli.py:101` | Live writes require two separate environment opt-ins. | Both live mutation env vars default closed. | Human operator arms both controls outside code. |
| OKX-004 | `src/finharness/okx_policy.py:59`, `src/finharness/okx_policy.py:72`, `src/finharness/okx_cli.py:111` | Blocked command tokens and non-allowlisted flags are refused. | Any unknown flag/token raises `OkxCliError`. | Human owner of CLI policy. |
| OKX-005 | `src/finharness/okx_live_gate.py:1`, `src/finharness/okx_live_gate.py:120`, `src/finharness/okx_live_gate.py:240` | Every live OKX mutation must pass persisted behavior state, notional cap, attester, reason, and receipt handling. | Blocked attempts write a receipt and raise `LiveOrderBlocked`. | Human attester/operator; notional cap is operator configured. |
| EX-001 | `src/finharness/execution.py:77`, `src/finharness/execution_graph.py:56`, `src/finharness/execution_graph.py:72` | Execution defaults are dry-run/paper and use the Nautilus paper adapter unless fake is explicitly requested for tests. | Default mode is non-live; fake is not the default. | Human-reviewed code/config only. |
| EX-002 | `src/finharness/execution.py:565`, `src/finharness/execution.py:628`, `src/finharness/execution_graph.py:197` | Live execution is blocked before order submit. | Live mode returns a blocked event and creates no live order request. | Human policy change only; current MVP forbids it. |
| EX-003 | `src/finharness/execution.py:760`, `src/finharness/execution.py:839`, `src/finharness/execution_graph.py:295` | Execution snapshots and receipts must preserve lineage, adapter mode, status, and review questions. | Snapshot records `execution_allowed=False`. | Receipt schema changes require human review. |
| RC-001 | `src/finharness/rule_change_ledger.py:1`, `src/finharness/rule_change_ledger.py:72`, `src/finharness/rule_change_ledger.py:85` | Lesson-to-rule promotion requires lesson lineage, receipt refs, rationale, and a human attester. | Evidence-free or unattested rule changes are refused. | Human attester; AI can draft lessons only. |

## Policy Engine Evaluation

OPA, Cedar, and Casbin are mature policy projects, but the current FinHarness
problem is not lack of a policy language. The higher-value control is the local
discipline encoded above: behavior stops, mandate caps, human confirmation,
receipt lineage, and "no live execution" boundaries.

Recommendation: do not adopt a policy engine in Phase 5. Keep the explicit
contract plus Python checks as the source of enforcement. Re-evaluate only if
policy duplication grows across multiple adapters, operators, venues, or roles.
At that point:

- OPA would be the first candidate for broad policy-as-code and audit reports.
- Cedar would fit only if FinHarness develops a real actor/resource/action
  authorization model.
- Casbin would fit only if the main pain becomes simple RBAC/ABAC across many
  operators or venues.

Any adoption is a separate user-approved production dependency decision. A future
engine may generate an additional verdict, but it must not relax a hard-coded
FinHarness stop. The engine verdict would be reviewed evidence, not authority.

Official references checked for this evaluation:

- OPA: https://www.openpolicyagent.org/docs/
- Cedar: https://docs.cedarpolicy.com/
- Casbin: https://casbin.org/docs/overview/

## Red Lines

- A policy engine cannot widen human-set caps.
- A policy engine cannot clear behavior-reset state.
- A policy engine cannot create live execution authority.
- A policy engine cannot replace human attestation.
- A policy engine cannot replace lesson-to-rule receipt lineage.
