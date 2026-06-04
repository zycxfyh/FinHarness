# SBOM And Provenance Baseline

Date: 2026-06-04
Status: RC0.2 local baseline

FinHarness now has a local software bill of materials and provenance baseline
task. This is a governance artifact, not a formal CycloneDX/SPDX/SLSA
attestation.

## Command

```text
task security:sbom
```

Outputs:

```text
data/security/sbom/finharness-sbom.json
data/security/provenance/finharness-provenance-baseline.json
```

## Inputs

The baseline reads committed manifests and lockfiles:

```text
pyproject.toml
uv.lock
package.json
pnpm-lock.yaml
Cargo.lock
crates/finharness-cli/Cargo.toml
```

## Current Boundary

The SBOM baseline records:

- local root packages
- Python packages from `uv.lock`
- npm packages from `pnpm-lock.yaml`
- Rust packages from `Cargo.lock`
- source manifest hashes for a provenance baseline

The provenance baseline records:

- current git head
- source material file hashes
- the local builder task and script
- non-claims that it is not signed SLSA provenance

## Non-Claims

- This is not a signed SLSA attestation.
- This is not a complete packaged-artifact provenance statement.
- This is not a legal or compliance certification.
- This does not authorize live trading or provider mutation.

## RC0.2 Next Steps

1. Decide whether to add a mature SBOM generator such as Syft or CycloneDX.
2. Decide whether release artifacts will be packages, containers, or source-only
   tags.
3. Add signed provenance only after the release artifact shape exists.
4. Keep `task security:sbom` inside release evidence even before formal
   attestation exists.

