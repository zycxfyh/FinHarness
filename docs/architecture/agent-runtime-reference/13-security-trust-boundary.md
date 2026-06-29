# 13 Security / Trust Boundary

Hermes is explicit about security posture: prompt rules, approval gates, redaction, pattern scanners, and tool allowlists are useful, but they are not hard adversarial boundaries. The hard boundary is operating-system or process isolation.

FinHarness needs the same honesty for capital governance.

## Boundary Types

FinHarness true boundaries should include:

- OS/process/credential isolation;
- StateCore write transaction;
- receipt immutability;
- human authentication and attestation;
- surface authorization;
- broker write absence.

Helpful but not hard boundaries:

- prompt instructions;
- natural-language disclaimers;
- redaction;
- regex guards;
- source summaries;
- model confidence;
- context pack summaries;
- profile text.

Semi-boundaries:

- profile tool exposure;
- runtime validators;
- guardrail findings;
- queue checks;
- context budgets;
- provider `check_fn`;
- surface policy.

## Core Security Statements

FinHarness should preserve these invariants:

- FinHarness is not an execution system.
- FinHarness does not expose broker write, order placement, or fund transfer tools.
- Agent-created proposals are review objects, not decisions.
- Agent summaries are not evidence unless backed by source refs.
- Evidence is not authority.
- Receipts record events; they do not prove correctness.
- Human attestation is required for decision-of-record transitions.
- No model output can create execution authority.

## Threat Surfaces

Input surfaces include:

- user input;
- market data providers;
- broker read-only APIs;
- PDFs, CSVs, screenshots;
- external research notes;
- LLM-generated summaries;
- session history;
- plugins/future providers;
- Notion/Drive/GitHub-style connectors;
- Cockpit/API/review surfaces.

Each surface should eventually be classified by trust, authority, mutability, prompt visibility, receipt visibility, PII risk, and freshness requirement.

## In Scope

Security issues should include:

- unauthorized capital state or receipt payload access;
- Agent-created object marked as human-attested;
- proposal draft bypassing human review into decision-of-record;
- receipt rewrite or deletion;
- broker write tool registered or exposed;
- plugin overriding governance core;
- source summary treated as authority;
- surface authorization bypass;
- credential leakage into model/tool result/receipt/export.

## Out Of Scope / Declared Limitation

Examples that are not automatically boundary violations:

- model generates incorrect analysis without mutating authority state;
- prompt injection makes the Agent say something wrong but no boundary is crossed;
- external provider gives bad data that remains evidence-only;
- operator intentionally exposes an unauthenticated surface;
- user stores live credentials in an unsafe location outside FinHarness controls.

The practical rule:

```text
wrong output != security boundary crossing
authority boundary crossing ~= security issue
```
