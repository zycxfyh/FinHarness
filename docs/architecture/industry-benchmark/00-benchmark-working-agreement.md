# Benchmark Working Agreement

Author: Codex
Parallel agent: Claude
Status: historical reference (downgraded 2026-07-02)
Date: 2026-06-15
Evidence policy: primary-source-first

This agreement governs the industry benchmark series. It exists so Codex and
Claude can work in parallel without confusing authorship, evidence, or authority.

## Goal

Produce a document-only market, product, and architecture benchmark that:

- shows what FinHarness is today;
- compares each plane with mature methods and standards;
- records true gaps with evidence and close criteria;
- designs solution paths without changing code;
- gives backend and frontend guidance for future PRDs, tech specs, and UI specs.

## Non-Goals

- No code, dependency, service, database, or frontend implementation.
- No new live-trading path.
- No legal, regulatory, tax, accounting, broker, exchange, or investment advice.
- No claim that backtests prove future returns.
- No claim that `task check`, receipts, or governance docs certify production
  readiness.
- No replacement of `trading_guard`, `risk_gate`, human confirmation,
  live blocks, lesson-to-rule lineage, or receipts with a mature library.

## Authorship And Collaboration

| Role | Meaning |
| --- | --- |
| `Author: Codex` | Codex drafted the document and is responsible for its evidence trail. |
| `Parallel agent: Claude` | Claude may be writing or reviewing parallel documents; this is not co-authorship unless explicitly stated. |
| Claude root docs | Read as parallel inputs, cited when used, not overwritten. |
| Human operator | Final reviewer and authority for project direction. AI output is proposal only. |

If Codex uses a Claude-authored document, it cites it as `Parallel input`.
If Claude later reviews a Codex document, add a review note rather than changing
the author line.

## Evidence Grades

| Grade | Source type | Use |
| --- | --- | --- |
| E0 | Repo source, tests, Taskfile, receipts, docs | Current FinHarness state. |
| E1 | Official standard, regulator, project, or vendor documentation | Mature method and requirements baseline. |
| E2 | Peer-reviewed or named research paper | Quant research methods and statistical rigor. |
| E3 | Vendor product docs or vendor engineering material | Market practice, with vendor-bias caveat. |
| E4 | Blogs, summaries, newsletters, second-hand articles | Discovery only; do not anchor claims here. |

Primary-source-first means E0/E1/E2 outrank E3/E4. If a second-hand source
contradicts a primary source, the primary source wins.

## Citation Policy

Repo evidence should name a concrete path. External evidence should link to the
official source wherever possible. Examples:

- Repo: [Interface Reference](../../reference/interfaces.md)
- Repo: [Ten Layer LangGraph Map](../ten-layer-langgraph-map.md)
- Primary external: https://spec.openapis.org/oas/v3.2.0.html
- Research paper: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551

Do not quote long passages. Paraphrase and link.

## Debt Classification

Use the A1-A4 taxonomy:

| Class | Meaning | Use in this series |
| --- | --- | --- |
| A1 | Direct fix | Typos, stale links, missing doc entry. |
| A2 | Logic refinement | Local rule or schema should be tightened inside an existing module. |
| A3 | System redesign | A recurring gap needs a new shared module, interface, or workflow. |
| A4 | Formalize | Requires project decision, external dependency, product choice, or human ownership. |

Do not call an A4 gap an A1 fix to make the roadmap look smaller.

## Review Checklist

Every document in this folder should satisfy:

- It has the author, parallel agent, status, date, and evidence-policy header.
- It separates current state from judgment.
- It states non-claims where a reader could overinterpret.
- It does not use receipt/test/dashboard success as trading authority.
- It preserves the project safety boundary: `execution_allowed=false` by default,
  human review, no AI direct order entry, and no live expansion.
