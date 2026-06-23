# D7 OpenTelemetry Trace / Receipt Indexing mini-RFC

Status: D7a trace context contract implemented (2026-06-23); D7b OTel dependency
remains gated.

## 1. Change Class

**C2**: cross-cutting observability change across API requests, task runs, logs, and
receipt references. It does not change financial decisions, execution authority, or
default product behavior. Any implementation that adds OpenTelemetry dependencies or
exporters still requires explicit approval before code changes.

## 1b. Module Placement / System Boundary (G5)

Primary system: **EOS Governance / Observability**.

Touched systems in a future implementation:

- **API / Cockpit adapters**: keep `X-FinHarness-Trace-Id` response behavior.
- **Task adapters**: attach a run trace id to bounded task receipts/logs.
- **State Core / receipts**: receipts remain the authority; traces only index them.

No new cockpit tab. No new domain logic. No Review/Decision/Research semantics change.

## 2. Current behavior

Current API observability is hand-rolled and local:

- `api/app.py` generates or accepts `X-FinHarness-Trace-Id`, stores it on
  `request.state.trace_id`, returns the header, and logs `state_api_request`.
- `runtime_log.py` configures structlog JSON logs.
- task runs and receipts are durable evidence, but there is no standard trace id
  linking a task run, API request, receipt path, and later UI/request inspection.
- `module-map.md` and `debt-cleanup-plan.md` both mark D7 as deferred.

## 3. Target behavior

Design target:

- Introduce an OpenTelemetry-compatible trace boundary for local API/task runs.
- Preserve existing `X-FinHarness-Trace-Id` behavior for callers.
- Make trace id usable as an index into logs and receipts.
- Default path has **no network exporter** and no telemetry upload.
- Receipts remain the source of truth; a trace is only an index/correlation handle.

Implementation should be split:

1. **D7a trace context contract**: define how trace id is created, propagated, and
   included in bounded local logs/receipt metadata.
2. **D7b OpenTelemetry adapter**: add approved OTel dependency and local-only SDK
   wiring if D7a proves the contract.
3. **D7c optional exporter**: only if a real consumer exists; this is out of scope
   for this mini-RFC and would be C3 if it adds external network export.

## 4. Surface Inventory

- **Input**:
  - incoming `X-FinHarness-Trace-Id`
  - future W3C `traceparent` if adopted
  - local task invocation context
- **Output**:
  - response `X-FinHarness-Trace-Id`
  - structlog fields
  - optional receipt metadata field or observability receipt that links trace id to
    receipt paths
- **External calls / network**:
  - none by default
  - no OTLP exporter in default `task check`, API serve, or smoke tasks
- **Failure surface**:
  - malformed incoming trace id
  - trace id missing from a receipt-producing task
  - exporter accidentally enabled in default path
  - trace confused with authoritative receipt
- **User-visible surface**:
  - no cockpit UI in D7a/D7b
  - possible future receipt/debug page may show trace id only as provenance
- **Excluded**:
  - no production telemetry platform
  - no metrics dashboard
  - no distributed tracing backend
  - no replacement of receipt/source_refs/content_hash
  - no tracing of secret values or raw payloads

## 5. Default Path Invariant

Current default API behavior:

- request returns `X-FinHarness-Trace-Id`
- response bodies and receipt schemas do not require an OTel span
- `task check` performs no telemetry upload

Future implementation must lock:

- existing API header still exists
- `execution_allowed=false` behavior unchanged
- no default network exporter is configured
- existing domain receipt content hashes do not change unless the slice explicitly
  scopes a new receipt field and updates snapshot tests

D7a keeps existing response/header semantics while moving trace id handling into a
shared contract and adding a separate observability trace-index receipt for task
correlation. It does not add an OTel SDK/exporter or mutate domain receipts.

## 6. Traceability Matrix

| Design promise | Planned code point | Test | Gate probe |
| --- | --- | --- | --- |
| Preserve API trace header | `api/app.py` middleware or `observability.py` helper | API test checks header round trip | governance policy blocks removal of header contract |
| No exporter by default | OTel setup helper defaults to local/noop exporter | unit test with env unset proves no exporter endpoint | grep/AST/env probe for default OTLP endpoint absence |
| Trace indexes receipts, does not replace them | receipt writer/task helper attaches trace ref or emits observability receipt | golden-path-style test replays receipt by path and correlates trace id | test asserts receipt content_hash/source_refs still present |
| Malformed trace input fails soft | trace context parser normalizes or replaces bad id | bad header test returns valid response + safe trace id | no raw header injection into logs |
| No secret/raw payload tracing | logging helper allowlist | red-team/log test with secret-like value | hardening/redline probe if new fields are added |

## 7. Test / Gate Plan

Design gate:

- confirm default path has no exporter/network
- confirm trace is index only, receipt remains authority
- confirm implementation dependency approval is separate from this RFC

Implementation gate for D7a/D7b:

- targeted API header tests
- task/receipt correlation test
- `task governance:check` policy for no default exporter
- `task check`

Independent gate:

- red-team malformed trace header / secret-like trace payload
- verify no raw env/token/payload appears in trace/log fields

## 8. Not claimed / Debt

Not claimed:

- no OpenTelemetry dependency is added by this document
- no external telemetry backend/exporter is configured
- no metrics, DORA dashboard, or production observability claim
- no browser E2E coverage (D8 remains separate)

Debt:

- D7b OpenTelemetry adapter still needs explicit dependency approval before adding
  an SDK/exporter.
- D8 Playwright/browser E2E remains separate.
- If exporter/network telemetry is later requested, it must be a new C3 slice.

## Progress Log

- D7a — implemented dependency-free `observability.py` trace context contract,
  API middleware propagation, fail-soft malformed header handling, an
  `observability_trace_index` receipt for task/receipt correlation, Golden Path
  trace-index coverage, and governance policies for trace contract/no default
  exporter. No OpenTelemetry dependency or exporter added.
