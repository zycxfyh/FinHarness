# Agent Runtime Reference

状态:reference(2026-06-30)。本目录把 Hermes agent 项目的成熟运行时模式整理成
FinHarness 可复用的设计参考。

它不是当前功能清单。当前事实仍以 `system-map.md`、`framework-index.md`、
`system-catalog.yml`、源码和测试为准。本目录只回答一个问题:

> 当 FinHarness 继续推进 Agent L5 时,哪些边界、接口和运行时形状值得参考?

## Reference Layers

| Layer | Hermes mature pattern | FinHarness use |
| --- | --- | --- |
| [Tool Runtime](01-tool-runtime.md) | 工具声明、toolset、availability check、schema patch、dispatch 分层 | 让 Agent 工具从“函数列表”升级为 capability/profile/runtime registry |
| [Prompt / Context Injection](02-prompt-context.md) | stable/context/volatile prompt parts; context file scanning; tool-aware guidance | 把系统提示、context pack、session facts 分层,避免 prompt 漂移和权限暗示 |
| [Approval / Guardrails](03-approval-guardrails.md) | hardline floor、approval-required actions、denial contract、combined guard result | 用 action-level guardrail 替代关键词限制,并暴露审查面 |
| [Review Lifecycle](04-review-lifecycle.md) | Kanban durable task state、handoff、heartbeat、block kinds | 把 proposal review 发展为可查询、可阻塞、可恢复的工作流对象 |
| [Delegation Boundary](05-delegation-boundary.md) | fork-join delegation、restricted child tools、summary is not evidence | 未来子 Agent 只能作为低权限分析者,不能继承审批或执行权 |
| [Memory / Session / Skills](06-memory-session-skills.md) | durable memory、session search、progressively disclosed skills | 区分 user preference、receipt、source evidence、session history 和 procedure |
| [Gateway / Platform Surface](07-gateway-platform-surface.md) | platform adapter registry、task-local session context、async delivery contract | 把 CLI/Cockpit/API/batch 入口转成显式 surface context |
| [Plugin / MCP Supply Chain](08-plugin-mcp-supply-chain.md) | manifest、allowlist、safe mode、facade、MCP env filtering | 外部 provider 可以扩展 evidence,不能替换 governance core |
| [Observability / Diagnostics](09-observability-diagnostics.md) | loop callbacks、tool pipeline、trajectory、cost、iteration budget、loop guardrails | 让 Agent draft/review 过程可解释、可诊断、可复盘 |
| [Model / Context Budget](10-model-context-budget.md) | API normalization、context engine、compression、fallback、error classifier | 把模型差异和 context pack 预算纳入治理对象 |
| [Execution Environment](11-execution-environment.md) | execution backend、workspace scope、env sanitization、timeout、cleanup | 不开放强执行工具,但先建立副作用 scope/atomicity/budget 思维 |
| [Runtime Control Plane](12-runtime-control-plane.md) | config/env separation、profile isolation、safe config recovery、managed mode | profile、provider、StateCore、receipt_root、surface 成为显式控制面 |
| [Security / Trust Boundary](13-security-trust-boundary.md) | OS isolation vs heuristic guardrails、surface auth、plugin trust model | 明确 evidence/authority/attestation/execution 的真实边界 |
| [Lifecycle / Release Governance](14-lifecycle-release-governance.md) | doctor、migration、compatibility、skill/tool/plugin placement、cross-platform rules | 让 Agent L5 能长期演进而不破坏治理状态 |

## Current Direction

The next useful step is managed capability expansion, not static restriction.
Hermes demonstrates that powerful Agent systems stay usable because capabilities
are declared, selected by profile/toolset, checked at runtime, routed through
approval or review surfaces when needed, and diagnosed when they degrade. #68
brings that shape into FinHarness by making evidence provenance reviewable,
testable, and traceable.

That reviewability is an enablement layer:

- expose which profile/tool/context pack/evidence provider shaped an Agent answer;
- surface source references, receipt references, limitations, and guardrail findings;
- keep default profile read/explain first as the baseline, not the ceiling;
- graduate new Agent permissions through explicit profile + tool entry + evidence
  provider + queue/review contract;
- keep broker execution, fund transfer, receipt rewriting, and final authority
  behind separately designed command paths rather than implicit model output.

## Design Rule

Use Hermes as a runtime pattern library for opening capabilities deliberately,
not as a permission ceiling or as an invitation to copy every tool.

FinHarness should copy the useful shape:

- declarative capability records;
- explicit context packages;
- structured runtime availability checks;
- clear denial and review surfaces;
- durable review state;
- evidence-bound receipts;
- explicit surface/session context;
- external capability supply-chain boundaries;
- diagnostics, budgets, and lifecycle receipts.

FinHarness should not copy accidental breadth. New permissions should still pass
through FinHarness-specific evidence, receipt, IPS, and review contracts:

- no unrestricted shell or external execution authority without a purpose-built
  profile, review/approval path, and receipt model;
- no recursive subagent delegation by default;
- no model-visible promise of capabilities that the active profile cannot use;
- no memory or session recall treated as evidence of current portfolio state;
- no external provider/plugin replacing receipt, IPS, attestation, or execution boundaries;
- no prompt/profile/redaction treated as a hard security boundary.

## Suggested L5 Roadmap

This reference supports a staged route:

```text
#62 Agent proposal draft review surface
#63 Proposal draft queue checks
#64 Queue check transition scope
#65 ReviewTask / EvidenceRequest lifecycle
#66 ToolEntry metadata + check_fn
#67 Agent Tool Runtime Pipeline v0
#68 Evidence Provider Registry v0
#69 Capital Context Budget / Projection v0
#70 AgentReviewNoteDraft capability
#71 Review Queue Triage
#72 Risk Register v0
#73 AgentScaffoldRevisionApplyCandidate
#74 Human-confirmed scaffold revision apply
#75 System-recomputed scaffold candidate preflight
#76 Preflight-bound candidate apply
#77 ActionIntent / OrderTicket candidate
#78 Paper autonomous operation under Authority Contract
#79 Event trigger + playbook engine
#80 Runtime Trace / Diagnostics Surface
#81 Control Plane v0
#82 Security / Trust Boundary v0
#83 Lifecycle / Release Governance v0
```

The route should use reviewability and reliability to unlock broader Agent
capability. Every new permission should arrive as an explicit runtime contract,
not as a prompt promise or hidden helper.

The product authority principle is:

```text
Default-deny, user-authorized autonomy.
```

Governance is not capability suppression. Governance is the mechanism by which
Agent authority becomes deployable. FinHarness should not default an Agent into
approval, execution, account-management, or emergency-response authority; it
should let a user grant scoped authority through explicit, revocable, machine-
checkable contracts once the supporting controls exist.

Future high-authority profiles should therefore graduate through an Authority
Contract, not a disclaimer alone. A contract must define account scope, asset
scope, action scope, consequence class, notional caps, turnover caps, risk
budget, drawdown and cooldown triggers, allowed order/action types, leverage and
derivative permissions, emergency playbook permissions, second-confirmation
rules, monitoring, kill switch, receipt requirements, review cadence, and
expiry. The contract is the runtime source of authority; model output remains
content unless a profile, contract, preflight, and command path consume it.

Current mainline has implemented the route through `#75`: Agent tools are
resolved through profile-selected `AgentToolEntry` records, declared evidence
provider ids, profile-aware context projection policies, and a runtime pipeline
that exposes visible/hidden/unavailable tools, structured dispatch results,
structured runtime errors, evidence envelopes, context-budget projection,
result-budget truncation, and authority-boundary metadata. The first stronger
write posture after proposal drafts is `review-note`: it creates typed,
append-only `AgentReviewNoteDraft` artifacts on existing proposals, routed
through the proposal timeline and receipts rather than through approval,
attestation, scaffold revision, or execution. Review queue triage now consumes
those artifacts with proposals, attestations, archived state, receipt index rows,
and proposal queue checks so human reviewers can see priority, triage reasons,
open questions, data gaps, duplicate/stale flags, and next actions. Risk
register v0 then derives read-only `RiskRegisterItem` objects from those queue
signals so evidence gaps, stale context, duplicate proposals, policy mismatch,
counter-evidence needs, Agent-reported risks, and open questions become
comparable review objects. It does not persist risk state, accept/resolve risk,
score risk, generate scenarios, or authorize execution. This is the foundation
for opening stronger Agent permissions in later profiles because the system can
now say which profile, tool, provider, source, receipt, context pack, projection
policy, runtime policy, governance artifact, review operating surface, and risk
object shaped each output.

`#73` opens the next stronger posture without skipping the authority ladder:
`scaffold-candidate` can create append-only
`AgentScaffoldRevisionApplyCandidate` timeline artifacts from active risk
register items. These artifacts include a bounded `scaffold_patch`,
`proposed_scaffold`, `changed_fields`, risk coverage, preflight/rollback
context, and human confirmation requirements. They are system-applicable
candidates, but they do not mutate proposals; human-confirmed apply remains the
next capability layer. In `#73`, preflight, risk coverage, and rollback fields
are explicitly Agent-supplied candidate payload; later system preflight is a
separate capability layer.

`#74` adds the first real apply path for that Agent labor:
`POST /scaffold-revision-candidates/{candidate_id}/apply` requires a human
attester, human reason, expected candidate receipt, expected proposal receipt,
and `explicit_confirmation=true`. The route then calls the existing
`revise_governed_proposal_scaffold(...)` command, writes a normal proposal
revision receipt, and links the revision context back to the candidate receipt
and review event. This is a human-confirmed state transition, not Agent
auto-apply, approval, attestation, or execution authorization.

`#75` adds the first system-recomputed preflight layer for those candidates:
`GET /scaffold-revision-candidates/{candidate_id}/preflight` reads the candidate
review event and current proposal state, then recomputes scaffold forcing,
changed fields, proposal receipt freshness, active risk register basis, risk
coverage completeness, and forbidden authority markers. It returns a
pass/warn/block report with a deterministic `report_hash`. The endpoint is
read-only: it does not apply the patch, attest, approve, reject, or authorize
execution. This follows the Hermes-style guardrail shape: the system produces a
structured readiness decision, and a later runtime/apply layer may consume that
decision explicitly.

`#76` binds human-confirmed apply to that system report. Apply now requires the
caller to present `expected_preflight_report_hash` for the candidate state being
applied. The server recomputes preflight at apply time, rejects mismatched
hashes, rejects `block` reports, permits `warn` reports only when the human
explicitly acknowledges all non-blocking warning codes, and records preflight
hash/status/finding codes/acknowledged warnings in the proposal revision
context. This keeps #74's useful human-confirmed state transition while closing
the time-of-check/time-of-use gap between "human saw a preflight report" and
"system applied the candidate."

After that, stronger autonomy should move through a product authority ladder
rather than a single "Agent can trade" switch:

```text
Mode 0: Explain only
Mode 1: Review + candidate generation
Mode 2: Human-confirmed apply
Mode 3: Paper autonomous operation
Mode 4: Live defensive autonomous operation
Mode 5: Live strategy autonomous operation
Mode 6: Emergency playbook autonomous operation
```

Earlier autonomy should bias toward paper operation, defensive-only actions,
small notional caps, ETF/cash/short-duration instruments, candidate order
tickets, event-triggered alerts, and human-confirmed emergency actions. Later
authority can consider larger live execution, leverage, options, short selling,
margin, illiquid assets, crypto derivatives, naked options, transfers, or cross-
account movement only behind higher Authority Contracts, stronger monitoring,
and explicit revocation paths.
