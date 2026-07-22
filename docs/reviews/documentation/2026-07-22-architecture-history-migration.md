# Architecture, Report, and Specification History Migration

> **Documentation lifecycle:** `historical`
> **Current authority:** [Documentation Lifecycle Contract](../../architecture/documentation-lifecycle.md)
> **Reason:** Exact #467 migration evidence for the bounded architecture/report/specification family.

Baseline: `main@cf3dfc7026f77d6ca45270c7de6b2401a0ff83d3`  
Issue: #467  
Parent: #452

## Migration Rule

Each authored body moved once into `docs/archive/documentation-lifecycle/`. The old path is now a bounded `superseded` redirect stub with one maintained-authority link and one archived-evidence link. No complete copy remains at the old path.

## Reviewed Outcomes

| Previous path | Preserved evidence | Current authority | Rationale | SHA-256 |
| --- | --- | --- | --- | --- |
| `docs/architecture/documentation-and-onboarding-plan.md` | `docs/archive/documentation-lifecycle/architecture/documentation-and-onboarding-plan.md` | `docs/README.md` | Completed documentation architecture plan; current task navigation and lifecycle governance now exist. | `054a19b26099756f5eb9537f386031c19283058241135a85704eeb0cea9afc96` |
| `docs/architecture/evidence-inventory.md` | `docs/archive/documentation-lifecycle/architecture/evidence-inventory.md` | `docs/architecture/system-map.md` | Historical evidence inventory for retired execution and provenance surfaces. | `ec047175c3c867e699647c1827423aada968bf82efb3fb63877702a4a45bf640` |
| `docs/architecture/policy-contract.md` | `docs/archive/documentation-lifecycle/architecture/policy-contract.md` | `docs/architecture/documentation-fact-governance.md` | Historical policy inventory for the retired ten-layer stack. | `2adcfb48f1247d29a4471bedc7d7517cae8d814d7630b1e17832a9badfed4280` |
| `docs/architecture/agent-native-target-space.md` | `docs/archive/documentation-lifecycle/architecture/agent-native-target-space.md` | `docs/architecture/agent-operating-surface.md` | Wave 0 target-space RFC; current Agent runtime contracts now own shipped behavior. | `f33fd90c8a288419f1d9f53cf791b1a729d06a37a592cc9803b379d37f4dfa17` |
| `docs/architecture/closure-report.md` | `docs/archive/documentation-lifecycle/architecture/closure-report.md` | `docs/architecture/system-map.md` | Point-in-time execution-spine migration closure report. | `2e0eb76f820de22c2dd4821a4ab8505f681627f8d1e209a1f27743f2e22954e2` |
| `docs/architecture/data-quality-interface-plan.md` | `docs/archive/documentation-lifecycle/architecture/data-quality-interface-plan.md` | `docs/architecture/mature-wheel-control-plane.md` | Design plan superseded by the implemented Pandera-backed data-quality path. | `c7e22d00b90575662fb6075e6490f73f2b05841c43d734969fa0fbc9de5ba41e` |
| `docs/architecture/market-access-ledger-spec.md` | `docs/archive/documentation-lifecycle/architecture/market-access-ledger-spec.md` | `docs/architecture/capital-os-layering.md` | Retired live-trading aggregate-limit execution specification. | `2b7b4cf4bd9661d946f8b1da2c2b72862438b2c933f8d0a473d069038d9779d3` |
| `docs/architecture/policy-evidence-interface-plan.md` | `docs/archive/documentation-lifecycle/architecture/policy-evidence-interface-plan.md` | `docs/architecture/documentation-fact-governance.md` | Completed design inventory; current policy and evidence governance now has separate owners. | `811c61ea01f0b00aff30f074efbcb2ec57f4f3b21bb6d4ca5a6ba73b8afb2299` |
| `docs/architecture/post-mvp-maturity-roadmap.md` | `docs/archive/documentation-lifecycle/architecture/post-mvp-maturity-roadmap.md` | `docs/product/product-roadmap.md` | Demoted post-MVP roadmap superseded by the current product roadmap. | `d30114d341a0fa10813fd120cb0fd5397fbe4667f81ebb279f85e41203a5f999` |
| `docs/architecture/research-interface-vectorbt-spec.md` | `docs/archive/documentation-lifecycle/architecture/research-interface-vectorbt-spec.md` | `docs/architecture/mature-wheel-control-plane.md` | Completed vectorbt evidence integration specification. | `f4f75d94e18361d09ea7a2922e12160ce0f7290597c460f178ade6e748041479` |
| `docs/engineering/execution-spine-debt-paydown.md` | `docs/archive/documentation-lifecycle/engineering/execution-spine-debt-paydown.md` | `docs/architecture/finharness-evolution-roadmap.md` | Completed debt-paydown plan; current debt truth is governed elsewhere. | `3261bce0a890f747bd2ffd22a6bfcc40eb825dc721b31732bbc7745a75b1070f` |
| `docs/operations/governance-dashboard-latest.md` | `docs/archive/documentation-lifecycle/operations/governance-dashboard-latest.md` | `docs/architecture/documentation-fact-governance.md` | Point-in-time generated governance dashboard snapshot. | `50e1b3f994576178256418222a4e9b27dccf1507b32ace4ccee0f4ea432181e3` |
| `docs/operations/repository-governance.md` | `docs/archive/documentation-lifecycle/operations/repository-governance.md` | `docs/architecture/documentation-fact-governance.md` | Point-in-time repository-governance audit snapshot. | `85aea459d6c13b60e06ca977e43787c3d48b3036a67be80672756faf4e59e9ec` |
| `docs/reports/trading-validation-report-v1.md` | `docs/archive/documentation-lifecycle/reports/trading-validation-report-v1.md` | `docs/architecture/capital-os-layering.md` | Historical ten-layer research-validation report. | `0e7c678eef4fba4f851643a7547b34bc9a14d7cd01d4f3abd67119b7082e07e3` |
| `docs/security/sbom-and-provenance.md` | `docs/archive/documentation-lifecycle/security/sbom-and-provenance.md` | `docs/security/ssdf-control-map.md` | Historical local SBOM/provenance baseline; current security controls own present posture. | `224c0e387e1a4515ff673f68063ccfd60f8d9e72e13ad5d0f254dcf858a1f088` |
| `docs/architecture/agent-work-loop-plan.md` | `docs/archive/documentation-lifecycle/architecture/agent-work-loop-plan.md` | `docs/architecture/agent-operating-surface.md` | Completed Agent Operating Cycle foundation plan. | `972953b96c5ec537436b628211c7db8a3365043690b599400f4da6a0aa3de748` |
| `docs/architecture/data-quality-interface-pandera-spec.md` | `docs/archive/documentation-lifecycle/architecture/data-quality-interface-pandera-spec.md` | `docs/architecture/mature-wheel-control-plane.md` | Completed Pandera implementation specification. | `bda6e230f6016c0659220f1f7609247ca01b58f0d9cf58a6b260a65a753b8306` |
| `docs/architecture/data-validity-spec.md` | `docs/archive/documentation-lifecycle/architecture/data-validity-spec.md` | `docs/architecture/mature-wheel-control-plane.md` | Completed data-validity implementation specification; current code owns behavior. | `63ca93ec5b9e39f56ee65099f16cfb8738709fa5cc13525078fdc69a9ba351f5` |
| `docs/architecture/graph-rationalization-audit.md` | `docs/archive/documentation-lifecycle/architecture/graph-rationalization-audit.md` | `docs/architecture/system-catalog.yml` | Historical graph-rationalization audit snapshot; current catalog and checks own status. | `8a6794f0b08ae062371dc5f3d82e66a3f672f475801b8ce13f6547ef83162c5a` |

## Owner Decisions

- `agent-work-loop-plan.md` is a completed foundation plan; the Agent Operating Surface and runtime tests own current behavior.
- `data-quality-interface-pandera-spec.md` is a completed implementation specification; current code and the mature-wheel control plane own behavior.
- `data-validity-spec.md` is a completed implementation specification; current market-data code owns adjustment, reconciliation, and bias disclosure.
- `graph-rationalization-audit.md` is a point-in-time audit; the current system catalog and governance checks own current graph status.

## Deferred Boundary Work

Current pages that link to these stable superseded paths are intentionally not rewritten in this slice. The final #452 boundary slice will make every current-to-noncurrent source sentence visibly contextual and add the corresponding machine guard.

No product/runtime behavior, navigation redesign, generated Reference, executable product journey, or publisher change is included.
