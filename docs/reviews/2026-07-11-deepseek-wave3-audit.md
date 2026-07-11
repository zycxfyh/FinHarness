# DeepSeek Wave 3 Audit Correction

Date: 2026-07-11

Status: actioned

## Scope

Review the merged SEC-02A–D, DEPS-02A–E, and LOOP-01B work against real
repository behavior rather than their PR completion claims.

## Findings

### SEC-02B passed vacuously

The import graph mixed filesystem names such as
`src.finharness.api.routes_paper_validation` with importable names such as
`finharness.api.routes_paper_validation`. Real tests also supplied file paths as
roots. Traversal therefore stopped at the first edge or began from a node that
did not exist. The graph filtered out every third-party import, so the external
network guard could never observe `httpx`, `requests`, `socket`, or provider
wheels.

Once corrected, the real graph exposed a transitive `yfinance` path caused by
base and state-core modules importing `market_data` only for `ROOT` constants.

### DEPS-02C did not prove a FinHarness runtime profile

The original base probe imported third-party packages but no FinHarness module.
It passed while importing the real API failed without the data group. The group
probe likewise imported only wheel names. The Agent group then failed when its
real consumers revealed required data and research capabilities.

The debt verifier checked manifest membership but did not require the manifest's
declared and recommended groups to match `pyproject.toml`. Profile probes were
not part of the merge gate or an Actions matrix.

### LOOP-01B tested fakes instead of production

`RecordingTool` and `ScriptedDecisionPort` were called directly. Neither was
injected into `run_agent_work_loop`. Reading nine scripted stop reasons back
from a list did not exercise nine production reducer branches. The claimed
increase from 4/15 to 7/15 therefore had no production evidence.

## Corrections

- Rebuilt the import graph around canonical module identities, external leaf
  nodes, relative imports, package initialization, and fail-closed missing roots.
- Added negative fixtures for external, relative, transitive, and missing-root
  failures.
- Extracted dependency-free project paths and removed path-only imports of the
  network-capable `market_data` module.
- Made data API routes conditional on the owned data profile; unexpected import
  failures still raise rather than being hidden.
- Upgraded the base probe to import StateCore, paper-validation routes, and the
  real FastAPI application, then inspect its OpenAPI surface.
- Upgraded group probes to import maintained FinHarness consumers. The Agent
  runtime profile now explicitly composes data + research + agent groups.
- Added the base rebuild to `check:ci` and an Actions matrix for all isolated
  profiles.
- Strengthened the debt verifier so actual, declared, and recommended ownership
  must agree and probe contracts must exist.
- Removed the standalone Loop fakes and restored the executable truth to 4/15
  passing and 11 open.

## Result

`ENG-DEBT-0002` and `ENG-DEBT-0005` remain resolved only after their corrected
semantic checks pass. Agent Work Loop remains explicitly scaffolded and is not
renamed or advanced by the rejected fake evidence.

## Follow-up

1. Implement LOOP-02 as a typed production `ToolRequest` carrying arguments.
2. Implement LOOP-03 as a real observation-driven reducer with behavioral stop
   path coverage.
3. Keep dependency profiles distinct from ownership groups; a profile may
   compose several owned groups.
4. Reject future debt closure when a verifier cannot demonstrate a failing
   negative fixture against the same production path.
