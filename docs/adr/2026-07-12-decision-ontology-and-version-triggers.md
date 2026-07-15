# Decision Ontology and Version-Trigger Matrix

Status: accepted

Date: 2026-07-12

Issue: #255

Case/Scenario direction was superseded by #403. The canonical direction is
`DecisionCaseVersion -> ScenarioVersion`; runtime correction remains owned by
#392.

## Decision

FinHarness separates the following identities and responsibilities:

- `Proposal` is a proposed answer or action; `DecisionProblem` is the stable
  question and owner context. They are not interchangeable.
- `DecisionCaseVersion` freezes the decision basis. `ReviewStateVersion`
  records review progress against one frozen case version.
- `DecisionRecord` is an append-only human decision event.
  `DecisionValidity` is the independently recomputable current validity of
  that record across evidence, policy, and authority axes.
- `Scenario.scenario_id` is logical identity;
  `ScenarioVersion.scenario_version_id` identifies immutable inputs/results.

`DecisionCaseVersion` contains only references that can change the basis:
the DecisionProblem, ProposalVersion, EvidenceSetVersion, adopted
CapitalStateVersion, and effective PolicyVersion identities. A
`ScenarioVersion` binds one exact `DecisionCaseVersion`; it never enters the
Case basis.
ReviewEvent, Attestation, ReviewStateVersion, and DecisionRecord are forbidden
case-basis inputs.

## Identity and integrity

Version identity is RFC 9562 UUIDv7. It is unique and time ordered. UUIDv7
generation is delegated to the maintained `uuid6` package because the current
Python 3.12 standard library does not provide it. Upgrade to Python 3.14 is the
removal trigger: replace the adapter import with `uuid.uuid7` and remove the
dependency after clean-environment parity tests.

The canonical SHA-256 basis hash is an integrity/deduplication aid only. It is
not version identity. Reverting to earlier content therefore produces the same
basis hash but a distinct, later UUIDv7.

## Version-trigger matrix

| Event | New DecisionCaseVersion? | Reason |
| --- | --- | --- |
| Proposal revision | yes | Candidate answer changed |
| Evidence admission | yes | Adopted basis changed |
| Evidence withdrawal | yes | Previously adopted basis is no longer available |
| Adopted CapitalStateVersion change | yes | Financial truth basis changed |
| Effective PolicyVersion change | yes | Governing constraints changed |
| ScenarioVersion add/recalculation/removal | no | Scenario evaluates an existing CaseVersion and cannot rewrite its basis |
| ReviewEvent | no | Review state only |
| Attestation | no | Review evidence only |
| DecisionRecord | no | Decision event over an existing case version |
| ReviewStateVersion | no | Derived review progress only |

The executable matrix is total over `CaseVersionTrigger`; adding an event
without classifying it fails the invariant contract.

## Lifecycle

The canonical case-review lifecycle is:

```text
draft -> evidence_open -> review_ready -> decided -> superseded
                       ^        |
                       +--------+
```

`review_ready -> evidence_open` is the explicit reopen path. A draft cannot
skip directly to decided. A basis-changing event creates a new case version;
it does not mutate the decided version.

## Design-spike disposition

PRs #247, #248, and #249 remain closed design spikes. They are evidence for
decomposition, not merge candidates and not the canonical model. Their useful
pieces must enter through leaf Issues blocked by #255 and conform to this ADR.

## Consequences and non-goals

This ADR unlocks the ProposalVersion resolver, EvidenceSet versions,
DecisionCase resolver, Scenario identity/version, and DecisionRecord/Validity
work. It does not add persistence, migrations, APIs, frontend surfaces, or
decision authority. Those remain separate auditable leaf Issues.
