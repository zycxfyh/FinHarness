# Property And Fuzz-Style Baseline

FinHarness RC0.1 adds lightweight property-style tests without introducing a new
fuzzing dependency.

## Scope

The current baseline covers governance invariants:

- A failed required quality check always blocks release.
- Repo intelligence excludes `.env` files and generated receipts.
- High-risk security/trading surfaces never set `execution_allowed`.
- Risk gate decisions never default to live execution authority.

## Task Entry

```bash
task test:properties
```

`task check` also runs this task.

## Why No Heavy Fuzzer Yet

OpenSSF Scorecard's Fuzzing check is oriented toward OSS-Fuzz,
ClusterFuzzLite, Go fuzzing, and a few language-specific property frameworks.
FinHarness is Python-heavy and currently gains more from explicit governance
invariants than from a heavy fuzzing service. A later phase can evaluate
Hypothesis or ClusterFuzzLite if the target surface becomes parser-heavy or
externally exposed.

## Non-Goals

- No live exchange fuzzing.
- No provider credential fuzzing.
- No generated payloads that include secrets or account data.
- No autonomous execution behavior.
