# Property And Fuzz Baseline

FinHarness RC0.2 has two lightweight boundary-testing layers without introducing
a new fuzzing dependency.

## Scope

The property baseline covers governance invariants:

- A failed required quality check always blocks release.
- Repo intelligence excludes `.env` files and generated receipts.
- High-risk security/trading surfaces never set `execution_allowed`.
- Risk gate decisions never default to live execution authority.

The deterministic fuzz baseline exercises malformed and generated inputs across:

- behavioral trading guard states
- security-surface path classification
- research asset id resolution and layer context handoff

## Task Entry

```bash
task test:integration
task test:properties
task security:fuzz
```

`task check` runs `task test:integration`, which includes this property baseline
alongside the slower graph integration checks. `task test:properties` remains as
a focused compatibility entry for the property baseline alone. The fuzz baseline
is separate so it can write a report without making every local check mutate
generated evidence.

## Fuzz Corpus And Report

```text
data/security/fuzzing/corpus.json
data/security/fuzzing/latest.json
```

`task security:fuzz` combines the fixed corpus with deterministic generated
cases. It passes only when every case preserves the core governance invariants:
no live execution authority, no unknown asset authority, and no high-risk path
classified as ordinary.

## Why No Heavy Fuzzer Yet

OpenSSF Scorecard's Fuzzing check is oriented toward OSS-Fuzz,
ClusterFuzzLite, Go fuzzing, and a few language-specific property frameworks.
FinHarness is Python-heavy and currently has more security value in explicit
governance-boundary fuzzing than in a heavy fuzzing service. A later phase can
evaluate Hypothesis, Atheris, or ClusterFuzzLite if the target surface becomes
parser-heavy or externally exposed.

## Scorecard Boundary

This baseline may not close OpenSSF Scorecard's Fuzzing alert because it is not
OSS-Fuzz or ClusterFuzzLite. The project records it anyway because it gives a
repeatable local control for the current MVP attack surface.

## Non-Goals

- No live exchange fuzzing.
- No provider credential fuzzing.
- No generated payloads that include secrets or account data.
- No autonomous execution behavior.
