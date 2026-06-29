# 10 Model / Context Budget

Hermes normalizes model/provider differences and treats context budget as runtime governance. It does not assume one infinite-context model, one API shape, or one retry behavior.

For FinHarness, this means model choice and context projection must not weaken capital governance boundaries.

## Hermes Pattern

Hermes supports multiple API modes and maps them into internal runtime objects. It also uses a context engine for compression, token tracking, fallback behavior, and session lifecycle.

The most important compression rule is that historical summaries are reference-only:

```text
past summary != current instruction
summary != authority
latest user message wins
```

Hermes also protects head and tail context:

- head: system identity and invariant rules;
- tail: latest task state and recent tool results;
- middle: compressible history.

## FinHarness Mapping

FinHarness should converge provider-specific behavior into internal objects:

- `AgentIntent`
- `ToolCall`
- `ToolResult`
- `ContextPack`
- `ProposalDraft`
- `Receipt`
- `GuardrailFinding`

Provider weakness must not loosen governance:

- if strict schema is unsupported, runtime validators still apply;
- if image input is unsupported, use source ref plus text projection;
- if context is small, shrink projection rather than omit boundaries;
- if provider fails, do not mark business object complete.

## Capital Context Engine

A future `CapitalContextEngine` should decide:

- which context packs enter the Agent;
- max chars/tokens per pack;
- which fields must remain exact;
- which history becomes summary only;
- which data stays as `source_ref`;
- which evidence must refresh from current source.

Context is not “more is better”. It is a budgeted evidence projection.

## Deterministic Projection First

Before LLM summarization, prefer deterministic projection:

- proposal timeline -> key events and latest state;
- receipt history -> recent bounded events plus status;
- market data -> normalized metrics, not raw dump;
- PDF/report -> source ref, bounded excerpt, data gaps;
- simulation output -> impact summary and artifact ref.

LLM summaries should never be the only stored state.

## Error Taxonomy

FinHarness needs structured error classes:

- `SOURCE_UNAVAILABLE`
- `SOURCE_STALE`
- `RECEIPT_WRITE_FAILED`
- `STATECORE_LOCKED`
- `PROFILE_NOT_ALLOWED`
- `MISSING_SOURCE_REFS`
- `HIGH_RISK_COUNTER_EVIDENCE_MISSING`
- `DUPLICATE_PROPOSAL`
- `SIMULATION_BACKEND_UNAVAILABLE`
- `BROKER_WRITE_UNSUPPORTED`

Each error should carry a recovery hint: retry, ask human, return data gap, block proposal, switch evidence provider, render partial surface, or abort write.
