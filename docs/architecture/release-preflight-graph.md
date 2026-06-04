# Release Preflight Graph

`release_preflight_graph` seals quality and supply-chain evidence before a
release or major push.

```text
source
  -> quality
  -> supply_chain
  -> release_gate
  -> receipt
```

## Supply Chain Inputs

- Dependabot configuration.
- CODEOWNERS ownership map in `.github/CODEOWNERS`.
- CodeQL workflow in `.github/workflows/security.yml`.
- OpenSSF Scorecard workflow in `.github/workflows/scorecard.yml`.
- Deterministic fuzz baseline workflow in `.github/workflows/fuzz.yml`.
- GitHub dependency graph expected from committed manifests and lockfiles.

## Local Command

```text
task release:preflight
```

This command runs authoritative local checks through the quality governance
graph and writes:

```text
data/receipts/release-preflight/latest.json
```

## Release Rule

The release gate is ready only when quality governance is not blocked and the
core supply-chain and ownership controls are present.
