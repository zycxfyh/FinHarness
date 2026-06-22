# Backend And Frontend Guidance

Author: Codex
Parallel agent: Claude
Status: draft
Date: 2026-06-15
Evidence policy: primary-source-first

This guidance should constrain future PRDs, tech specs, and UI specs. It is not
an implementation and does not approve any dependency.

## Backend Guidance

Future backend work should expose FinHarness evidence without creating trading
authority.

### Interface Rules

- Start schema-first: draft OpenAPI and JSON Schema before choosing a web stack.
- First surface is read-only: snapshots, receipts, cockpit state, review queue,
  module metadata, source docs.
- No endpoint may place orders, size trades, authorize live mode, raise limits,
  modify broker state, or weaken `risk_gate`.
- If a future review-write endpoint exists, it must be idempotent, scoped,
  receipt-backed, and human-attested.
- Every response that contains recommendation-like content must include
  evidence refs, assumptions, rejected alternatives, risks, non-claims, and
  authority state.

### Data And Receipt Rules

- Receipts remain the durable evidence root.
- OpenTelemetry traces, backend logs, and UI events may index receipts but do
  not replace them.
- OpenLineage-style exports may map jobs and datasets, but must preserve
  receipt refs and non-claims.
- Any missing data-quality or research-rung limitation must travel with the
  response.
- Backend responses should prefer stable identifiers over file-path coupling
  when a product interface is designed.

### Security Rules

- No secret files, tokens, account keys, private keys, or decrypted env values in
  docs, responses, receipts, or UI payloads.
- ASVS is a checklist source, not a compliance claim.
- Mutating actions, if ever designed, require explicit authorization model,
  idempotency, audit receipt, and human review. They are out of scope for the
  read-only phase.
- Backend must fail closed when authority state is missing or ambiguous.

### Backend PRD Checklist

| Question | Required answer |
| --- | --- |
| What exact evidence is exposed? | Snapshot/receipt/cockpit/review resource names. |
| What is explicitly not exposed? | Order entry, live authorization, broker mutation, secret material. |
| Which schema owns the response? | JSON Schema/OpenAPI draft path. |
| What is the authority state? | Usually `execution_allowed=false`, plus non-claim text. |
| How is it reviewed? | Tests, docs check, security review, human review for authority changes. |

## Frontend Guidance

Future frontend work should make evidence easier to inspect and authority harder
to confuse.

### Product Shape

- First UI: read-only evidence cockpit.
- Second UI: human review queue and annotation surface.
- Later UI: mobile/tablet thin client only after the web review flow is stable.
- The UI is a window, not a trigger.

### Required Views

| View | Must show | Must not show |
| --- | --- | --- |
| Watchlist/cockpit | Data freshness, quality status, broken/degraded paths, receipt refs. | Buy/sell/order controls. |
| Feature snapshot | Feature values, backend/tool version, lineage, `execution_allowed=false`. | Signal language that implies authority. |
| Validation | Research rung, OOS/walk-forward/trial count if available, data limitations, non-claims. | "Edge proven" or "safe to trade" language. |
| Proposal/risk | Evidence summary, risk decision, blocking reasons, human review state. | Controls to override caps or live blocks. |
| Execution/post-trade | Paper/dry-run lifecycle, TCA limitations, receipts. | Live submit/cancel controls. |
| Lessons/rules | Lesson source receipts, promotion state, human attester, rule diff. | Auto-promote controls. |

### Interaction Rules

- Make authority boundaries visible in the first viewport of any review page.
- Use slow, explicit language for review/attestation actions.
- Keep dangerous verbs out of the UI unless the action is truly safe and
  receipt-backed. For this roadmap, order verbs are not allowed.
- Show non-claims near evidence, not buried in a footer.
- Provide receipt drill-down before any review attestation.
- Support keyboard navigation and readable contrast following WCAG 2.2.

### Frontend PRD Checklist

| Question | Required answer |
| --- | --- |
| What decision does this page help a human make? | Review, learn, annotate, or inspect evidence. |
| What could a user wrongly infer? | Name the overclaim and how the UI prevents it. |
| Which receipt refs are visible? | Every evidence card or row has a path/id. |
| Where are non-claims shown? | Same page section as evidence. |
| What actions are impossible? | Order entry, live mode, cap override, auto rule promotion. |

## AI Guidance

AI may assist research and drafting, but must not own authority.

| AI seat | Allowed | Not allowed |
| --- | --- | --- |
| Generator | Draft hypotheses, summaries, review prompts, lesson candidates. | Declare evidence true, approve trades, promote rules. |
| Evaluator | Only if calibrated against local ground truth; otherwise programmatic/human evaluator wins. | LLM judging LLM output as final authority. |
| Interface assistant | Explain receipts, find evidence, summarize limitations. | Hide non-claims, create orders, bypass review. |
| Planner | Propose roadmaps and specs. | Approve dependencies, close debt, certify compliance. |

Every AI output shown in a backend/frontend product surface must carry:

- source refs;
- confidence or limitation note;
- non-claim;
- human review condition;
- no execution authority.

## Design Review Gate

Before any backend or frontend implementation starts, the spec should pass:

- no mutation endpoint or UI action unless explicitly approved;
- no path from AI output to broker action;
- `risk_gate`, `trading_guard`, human confirmation, live block,
  lesson-to-rule, and receipts are preserved;
- schemas include non-claims and receipt refs;
- security review covers secrets, access, logging, and redaction;
- accessibility review covers keyboard, contrast, focus, and error states.

## Non-Claims

- This guidance does not implement backend or frontend work.
- This guidance does not approve a web framework or runtime dependency.
- This guidance does not authorize live trading.
- This guidance does not certify WCAG, ASVS, SSDF, OpenAPI, JSON Schema,
  OpenTelemetry, or OpenLineage conformance.
