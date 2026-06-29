# 08 Plugin / MCP Supply Chain

Hermes treats external capabilities as a supply chain. Plugins, MCP servers, model providers, platform adapters, skills, hooks, middleware, and memory providers all enter through governed contracts.

For FinHarness, this means external finance capabilities should expand evidence, not authority.

## Hermes Pattern

Hermes distinguishes:

- bundled plugins;
- user plugins;
- project plugins that require opt-in;
- pip entry-point plugins.

Discovery is not enablement. Plugins are enabled through allowlists and can be suppressed by denylist or safe mode.

Hermes also classifies plugin kind:

- standalone;
- backend;
- exclusive;
- platform;
- model-provider.

Different kinds receive different loading and override rules.

## FinHarness Mapping

Future providers should be supply-chain objects:

| Kind | Allowed role |
| --- | --- |
| `evidence-provider` | market/research data, evidence-only |
| `document-parser` | extract bounded facts from files |
| `simulation-backend` | produce hypothetical reports |
| `report-renderer` | format outputs |
| `broker-read-provider` | read-only account evidence |
| `policy-extension` | highly restricted, probably built-in first |
| `governance-core` | not externally replaceable |
| `broker-write-provider` | unsupported |

Principles:

- discovered provider does not mean enabled provider;
- enabled provider does not mean authoritative provider;
- evidence provider does not create action authority.

## Facade Rule

External code should register through a narrow host-defined facade:

```text
register_evidence_provider
register_document_parser
register_simulation_backend
register_report_renderer
```

It should not receive direct access to:

- receipt writer internals;
- StateCore write internals;
- attestation creation;
- execution toggles;
- policy override functions.

## Override Rule

External providers must not shadow governance names:

- `write_receipt`
- `approve_proposal`
- `create_attestation`
- `execute_order`
- `transfer_funds`
- `ips_check`

External tools should use provider-qualified names such as `sec_edgar.fetch_filing` or `pdf_parser.extract_tables`.

## MCP Boundary

MCP-style external servers are higher risk because their tool names, descriptions, schemas, and errors enter the model-visible tool surface.

Future FinHarness MCP/provider support should require:

- explicit enablement;
- safe environment baseline;
- per-provider env allowlist;
- credential redaction in errors;
- tool description injection scan;
- timeout and connect timeout;
- failure isolation;
- no override of governance-core capabilities.

Safe mode should disable external providers and leave built-in read-only diagnostics available.
