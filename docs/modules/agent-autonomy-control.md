# Agent Autonomy Control

Status: current AUT2 foundation (2026-07-11)

## Purpose

Provide the deterministic Harness membrane between Capital Agent intent and an
effective decision or action. The module expresses the world-fidelity and
autonomy ladders, resolves existing authority credentials, and returns a typed
admission report without performing the requested effect.

## Current responsibilities

- define W0-W4 world-fidelity and AUT0-AUT6 autonomy vocabularies;
- classify Agent actions from observation through constitutional change;
- map each action class to its minimum world and autonomy requirements;
- evaluate runtime ceiling, mandate scope, expiry, kill switch, tool, asset,
  and financial-action constraints;
- return `effective`, `candidate`, `escalate`, or `blocked` admission evidence;
- adapt receipt-backed `CapitalMandate` and `AgentAuthorityGrant` records into
  the new runtime vocabulary without inferring authority above AUT3;
- carry autonomy context on `AgentWorkRequest` and `AgentWorkResult`.

## Non-goals

- execute tools, submit orders, move money, or mutate authority;
- claim that AUT2 or any higher autonomy level is operational;
- replace StateCore authority storage in this slice;
- infer human approval, paper authority, or real-world authority from a profile;
- make financial calculations or decide whether an investment is desirable.

An `AutonomyAdmissionReport` is evidence for a later command boundary. Its
`execution_allowed` and `authority_transition` fields are always false. The
Agent Operating Cycle invokes admission before every tool dispatch and links
admitted and denied attempts into its terminal artifacts.

## Typed inputs

- `AgentActionRequest`: objective, action class, requested autonomy, tool,
  arguments, target scope, and effect shape;
- `AutonomyRuntimeState`: current world fidelity, runtime autonomy ceiling,
  world-state reference, and evaluation time;
- `AutonomyMandate`: principal/Agent identity, granted autonomy, allowed
  actions/tools/scopes, limits, expiry, kill switch, and evidence references;
- legacy `CapitalMandate` and `AgentAuthorityGrant` records through the
  StateCore adapter.

## Typed outputs

- `AutonomyAdmissionReport`: disposition, effective flag, required/current/
  granted levels, human-control mode, findings, mandate/world references, and
  effect-admission flags;
- `RuntimeAutonomyMandateResolution`: resolved mandate or closed deny reasons
  and warnings.

## Important files

- `src/finharness/autonomy_control.py`
- `src/finharness/agent_autonomy_adapter.py`
- `src/finharness/agent_work_loop.py`
- `tests/test_autonomy_control.py`
- `tests/test_autonomy_statecore_adapter.py`
- `docs/adr/2026-07-11-agent-native-control-ownership.md`

## Mature wheels / external systems

None in the decision core. Pydantic provides frozen boundary models and
StateCore/SQLModel supplies existing credential persistence. A future policy
engine is justified only if the local rule set becomes difficult to inspect or
test; it must not become the source of financial intent.

## Quality, lineage, and receipt strategy

Admission is pure and deterministic for explicit inputs. Behavioral tests cover
positive and negative W/A combinations, expiry, kill switch, scope mismatch,
constitutional escalation, and the non-execution invariant. StateCore source
and receipt references are preserved in the resolved mandate. This slice does
not persist admission reports; durable linkage belongs to the future work-loop
terminal artifact chain.

## Upgrade log

- 2026-07-11: introduced the W0-W4/AUT0-AUT6 lattice, typed admission report,
  legacy StateCore adapter, and work-request/result autonomy context.

## Open risks

- Admission is called by Agent work dispatch but not by future AUT4/AUT5 effect commands.
- Cross-cycle session/checkpoint/resume semantics are absent.
- Legacy L0-L3 semantics are only a compatibility mapping and cannot represent
  AUT4-AUT6 mandate programs.
- Limit-book contents are carried as constraints but not yet evaluated by
  action-specific deterministic risk gates.
- Agent Operating Cycle v0.1 passes the 15/15 AUT2 foundation gate.

## Next upgrades

1. Bind actual versioned world-state evidence rather than caller-supplied fidelity hints.
2. Add restart/resume only when durable long-running work requires it.
3. Introduce AUT3+ programs only with world-model prerequisites and explicit
   mandate, risk, recovery, revocation, and negative-path tests.
