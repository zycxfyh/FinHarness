# FinHarness Post-MVP Maturity Roadmap

> DEMOTED 2026-06-13 to keep-warm backlog by
> docs/adr/2026-06-13-target-state-b-is-the-governing-roadmap.md.
> The governing roadmap is docs/think/2026-06-12-target-state-b-and-loop-
> topology.md (north star: B4). This document's RC0.3 priorities optimize
> governance maturity — which the 2026-06-12 audit named as a category error
> ("governance compounds; judgment does not"). Of the RC0.3 list, only two
> items survive the B-doc razor: validation depth (#5) and "defer live-write
> expansion" (#7). The rest are frozen, not deleted. Keep security/CI running;
> do not add new governance graphs. Useful below as an external-bar reference
> (SSDF/SLSA/DORA), not as the active plan.

Date: 2026-06-04
Status: keep-warm backlog (demoted from planning baseline 2026-06-13)

This document compares FinHarness after the ten-layer MVP with mature software,
security, and platform practices used by strong engineering organizations and
top open-source projects.

It is not a production-readiness certification. It is a planning map for moving
from a working research MVP to a repeatable, auditable, safer engineering
system.

## Executive Judgment

FinHarness has completed a credible research MVP:

- ten-layer LangGraph chain exists
- research asset library exists
- quality, release preflight, repo intelligence, and engineering delivery
  graphs exist
- local hardening, red-team boundary checks, deterministic fuzz baseline,
  SBOM/provenance baseline, threat model, SSDF map, CODEOWNERS, and security
  response runbook exist
- live trading remains unauthorized by design

Under a strict top-company standard, the project is not yet a production trading
system and should not be described as one. The next phase should focus on
maturity loops: review enforcement, formal release artifacts, recurring security
review, performance observability, stronger validation evidence, and staged
paper/live-read gates.

## What Strong Teams Usually Do After MVP

| Maturity area | Mature practice | Meaning after MVP |
| --- | --- | --- |
| Product boundary | Turn MVP claims into explicit supported and non-supported claims | Avoid saying a research harness is a live trading platform |
| Quality system | Keep a fast local gate plus deeper CI gates | Developers get quick feedback, release branches get stricter checks |
| Review discipline | Require review for sensitive paths | Workflows, execution, risk, provider, and security config do not change alone |
| Supply chain | Produce SBOM, signed provenance, pinned CI, dependency review | Builds can be traced to source, inputs, and workflow |
| Security maturity | Use SSDF/SAMM-like control maps | Security becomes a program, not a one-time scan |
| Fuzz and adversarial testing | Make fuzzing repeatable and visible in CI | Boundary failures become regression tests |
| Reliability | Track release, rollback, and recovery signals | DORA-style metrics reveal whether speed is coming with stability |
| Incident response | Maintain private reporting, triage, rotation, and postmortems | Vulnerabilities have an owner, severity, timeline, and evidence trail |
| Architecture intelligence | Keep dependency and ownership maps current | Teams understand blast radius before changes land |
| Domain validation | Separate engineering readiness from financial correctness | Passing CI does not imply alpha, best execution, or compliance |

## FinHarness Compared With That Bar

| Area | Current FinHarness posture | Strict rating | Next gap |
| --- | --- | --- | --- |
| MVP scope | Ten-layer research chain is implemented and documented | strong MVP | Keep non-claims visible in every release document |
| Local quality | `task check`, property tests, hardening gate, release preflight | strong for MVP | Add timing trends and failure history |
| Remote CI | security, fuzz, Scorecard workflows pass or report posture | good | Treat Scorecard governance alerts as recurring backlog |
| Review ownership | CODEOWNERS exists | partial | Rulesets do not require code-owner review yet |
| Branch protection | main medium, release strict, admin bypass allowed | partial | Decide when main becomes PR-only or release-only strict |
| Security scanning | CodeQL, Gitleaks, Trivy, Dependabot enabled | good | Add recurring review receipts for open/deferred findings |
| Threat model | FinHarness threat model exists | good | Refresh on every provider/live-surface expansion |
| SSDF mapping | SSDF control map exists | partial | Convert high-priority gaps into tracked tasks |
| SBOM/provenance | Local baseline exists | partial | Upgrade to formal CycloneDX/SPDX and signed SLSA-style attestation when package artifact exists |
| Fuzzing | Deterministic local fuzz baseline exists | partial | Not yet recognized by Scorecard as formal fuzzing |
| Security response | SECURITY.md and runbook exist | good | Add recurring security review cadence and incident lesson template |
| Trading validation | Boundary validation report exists | good MVP | No profit, alpha, best execution, fill model, tax, accounting, or compliance proof |
| Runtime observability | Receipts and dashboards exist | partial | No DORA-style trend history or latency/performance budget |
| Release artifact | Receipts exist | partial | No signed release notes, checksums, or immutable receipt verification |

## The Next Planning Shape

Do not add an eleventh trading layer. The next work should strengthen four
systems around the ten-layer chain.

### 1. Governance Closure

Goal: every release claim has evidence and an owner.

Recommended work:

- require `task release:preflight` before release claims
- add recurring security review receipt, even when there are no new alerts
- require human review for changes under `.github/`, `Taskfile.yml`,
  execution, risk gate, provider adapters, and security config
- decide whether release branches require code-owner review before main does

Why this matters:

FinHarness now has governance graphs. The next maturity step is to make them
routine, not optional.

### 2. Supply Chain And Release Integrity

Goal: release artifacts can be traced and verified.

Recommended work:

- keep current local SBOM/provenance baseline
- choose a formal SBOM generator only when package artifacts are clear
- add signed checksums or provenance for packaged releases
- record the build workflow, commit, dependencies, generated receipts, and
  non-claims in each release note

Why this matters:

Top projects do not rely only on source code being present. They also explain
what was built, where it was built, and what inputs were used.

### 3. Validation Depth

Goal: move from "workflow correctness" toward "research correctness" without
overclaiming live trading.

Recommended work:

- connect L5-L10 to research asset ids more deeply
- require StrategySpec, MathMethodSpec, and ReferenceCard lineage in validation
  and risk receipts
- expand validation beyond input availability into return windows, cost
  assumptions, drawdown behavior, robustness checks, and attribution
- keep execution paper/fake-first until validation and risk evidence mature

Why this matters:

The current MVP proves that the chain preserves boundaries. It does not prove
that a strategy works.

### 4. Engineering Health Observability

Goal: know whether the project is getting faster or more fragile.

Recommended work:

- record check duration from `task check`, `task security:scan`, and
  `task release:preflight`
- record failure counts and recovery time for failed checks
- add a simple monthly dashboard for quality, security, and release health
- classify slow or flaky checks as engineering debt

Why this matters:

Mature teams track both speed and stability. A fast project that silently
weakens gates is worse than a slower project with explicit evidence.

## Should Tests Become LangGraph Visible Graphs?

Yes, but only for governance visibility, not as a replacement for ordinary
test runners.

Recommended model:

```text
quality_governance_graph
  local checks -> property checks -> hardening checks -> docs drift -> receipt

release_preflight_graph
  required docs -> branch/security posture -> supply-chain posture -> release gate

security_review_graph
  alerts -> severity triage -> required checks -> closure receipt -> lesson

validation_governance_graph
  StrategySpec -> MathMethodSpec -> dataset freshness -> validation receipt
```

The graph should answer "what evidence exists and what is blocked?" The tests
should still run through normal tools such as unittest, ruff, CodeQL, Trivy,
Gitleaks, and future fuzz tooling.

## Proposed RC0.3 Priorities

1. Add a recurring security review graph or task.
2. Add a monthly governance dashboard with check duration and open-risk history.
3. Make release branches require code-owner review before making main PR-only.
4. Add formal release note/checksum policy.
5. Expand L6/L8/L10 validation around StrategySpec and MathMethodSpec lineage.
6. Decide whether formal fuzzing is worth the maintenance cost.
7. Defer live-write expansion until dual-control, provider-specific runbooks,
   and paper/live-read evidence are strong.

## Acceptance Criteria For The Next Phase

FinHarness should be able to answer these questions without relying on chat
history:

- What changed since the last release candidate?
- Which checks passed, failed, or were deferred?
- Which security findings are open, closed, or intentionally accepted?
- Which asset ids shaped a hypothesis, validation, risk gate, execution, and
  post-trade review?
- Which evidence proves live trading stayed unauthorized?
- Which artifacts can be rebuilt and verified from source?
- What got slower, flakier, or riskier this month?

## Non-Claims

- This roadmap does not certify production readiness.
- This roadmap does not authorize autonomous or live trading.
- This roadmap does not claim SSDF, SAMM, SLSA, GIPS, FINRA, broker, exchange,
  accounting, tax, custody, or best-execution compliance.
- This roadmap does not replace human review for release or live-provider
  boundary decisions.

## External Reference Anchors

- NIST SSDF: https://csrc.nist.gov/pubs/sp/800/218/final
- SLSA levels: https://slsa.dev/spec/v1.0/levels
- OpenSSF Scorecard: https://github.com/ossf/scorecard
- GitHub security features: https://docs.github.com/code-security/getting-started/github-security-features/
- OWASP SAMM: https://owasp.org/www-project-samm/
- DORA metrics: https://dora.dev/guides/dora-metrics/
- Google SRE release engineering: https://sre.google/sre-book/release-engineering/
