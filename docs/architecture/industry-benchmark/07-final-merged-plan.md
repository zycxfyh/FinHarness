# Final Merged Plan (Authoritative)

Author: Claude + Codex (reconciled)
Status: draft, authoritative synthesis
Date: 2026-06-15
Evidence policy: primary-source-first

This is the single authoritative output of the industry-benchmark effort. It
merges the Codex benchmark series (00–06) with Claude's parallel root analysis
(state, gap, solution, roadmap). The parallel Claude root documents were folded
in here and removed to keep one source of truth. Where the two converged, treat
it as settled; the convergence of two independent analyses is itself the
strongest signal in this folder, and a partial answer to the meta-governance gap
(no independent reviewer) the critique raised.

This is a planning artifact. It does not authorize code, dependencies, live
trading, or compliance.

## 1. Strategic verdict (the "why")

FinHarness has **A-grade engineering discipline applied to a product whose value
is not yet proven.** The machinery (governance, receipts, ten layers, loops) is
more sophisticated than the finance substance it governs.

The reframe that matters: **the control plane is not over-engineering.** Its
shape — `execution_allowed=false` by default, human-set caps, fail-closed gates,
receipts, brakes kept in-house — is a primitive but *correct* version of what SEC
Rule 15c3-5 (the Market Access Rule) legally requires of professionals. The
instinct is right; the gaps are elsewhere.

The job now, in order: **earn trustworthy research → close the accountability
hole → open the product hinge (API) → build a read-only surface — and never let
the surface weaken the brakes.**

## 2. Canonical gaps

The canonical gap list is the Codex register **G01–G15** in
[03-gap-register](03-gap-register-codex.md) (more complete and evidence-linked
than the Claude root version). Reconciliation decisions:

- **Adopted:** G06 aggregate market-access limits is **HIGH**, not medium. SEC
  15c3-5(i) requires *aggregate* pre-set credit/capital limits across all access,
  not per-order caps. Claude's earlier "medium" under-weighted this.
- **Folded in from Claude:** the strategic value-question framing (§1, §5) and
  the "controls are primitive-correct 15c3-5" reframe.

Priority bands (merged):

| Band | Gaps | Why |
| --- | --- | --- |
| **Now** | G01 research rigor · G02 data validity · G05 control owner · G06 aggregate limits | value, safety, accountable-control shape |
| **Next** | G03 trial accounting · G04 TCA · G07 operator/account · G08 restricted-symbol · G09 ceiling-vs-request · G10 read-only backend | deepen loops, open the product hinge |
| **Later** | G11 frontend · G12 observability · G13 lineage export · G14 records integrity | product/frontend maturity, external auditability |
| **Hold** | G15 governance over-investment | do not add governance breadth before substance deepens |

## 3. The plan — Now / Next / Later

### Now — close value and safety
1. **Research rigor ladder (G01, CRITICAL).** OOS → walk-forward → trial-count +
   Deflated-Sharpe discount in `validation.py` / `BacktestEvidenceProvider`.
   Hard rule: **no `supported` above the rung actually climbed**; receipts record
   rung + trial count. *This phase decides whether the project has value.*
2. **Data validity labels (G02).** Corporate-action adjustment disclosure, a
   second-vendor reconciliation note, and a `data_bias_uncontrolled` stamp on
   research receipts until point-in-time/survivorship is solved.
3. **Control-owner accountability (G05).** A named human + periodic certification
   receipt tied to the discipline-baseline tests (the 15c3-5 CEO-cert analog).
   Closes the meta-governance hole. Cheap, high leverage.
4. **Aggregate market-access limit ledger (G06).** One shared limit model
   (account/operator/environment/venue/symbol/request/remaining) consumed by
   *every* mutation-capable path; receipts record remaining limit.

*Not in this phase:* new venues/asset classes, live/autonomous execution,
frontend polish, new governance graphs.

### Next — build the product hinge safely
5. **Read-only backend interface spec (G10).** OpenAPI/JSON Schema for
   snapshots/receipts/cockpit/review-queue. **No mutation/order/sizing/authority
   endpoint.** Requires user approval for `fastapi`/`uvicorn` before any build.
6. **Trial accounting + TCA (G03, G04).** Record trials + discounted metric;
   add implementation-shortfall (arrival-price) TCA on paper fills and deeper
   intended/submitted/filled/canceled/rejected reconciliation.
7. **Operator/account + restricted-symbol + ceiling-vs-request (G07, G08, G09).**
   Typed runtime authorization (no secrets), restricted-list + fat-finger checks,
   and a hard split between configured ceiling and per-request limit so a CLI flag
   can never silently override a cap.

### Later — frontend and external compatibility
8. **Read-only evidence dashboard (G11).** Web UI over the read-only API;
   WebSocket refresh; dumb chart/table components.
9. **Review & annotation surface.** Human decisions become receipt-backed
   evidence — still no execution path. This is where the value moment becomes
   measurable.
10. **Observability + lineage/records (G12, G13, G14).** OpenTelemetry trace IDs
    that index (not replace) receipts; OpenLineage-style export; checksum/append-
    only manifest for live-adjacent receipts.

## 4. Frontend doctrine (non-negotiable)

From [06-backend-frontend-guidance](06-backend-frontend-guidance-codex.md):

- The UI is a **window and a review queue, never a trigger.** No order entry, no
  sizing, no "go live", no cap override, no auto rule-promotion — anywhere.
- **Per-view rule:** every evidence view must show its receipts, rung, trial
  count, assumptions, and **non-claims beside the evidence** (not in a footer);
  must not show "edge proven" / "safe to trade" language.
- Use **slow, explicit language** for review/attestation; make the human better
  informed and *slower*, not faster to act.
- Brakes live in the backend; the UI can display a boundary, never relax it.
- Accessibility: WCAG 2.2 (keyboard, contrast, focus, error states).
- **AI-seat governance:** generator drafts, evaluator only if calibrated to
  local ground truth, no "LLM judging LLM as final authority"; every AI output on
  a product surface carries source refs, a limitation note, a non-claim, and the
  human-review condition.

## 5. The value loop (how we will know it worked)

Judge by externalized decision quality, not graph/receipt count:

1. A research result survives a higher rung (OOS + Deflated-Sharpe discount)
   without overclaim — the first *honest* evidence of any edge.
2. A named human can see what controls were in force, on a date, with evidence.
3. Post-trade receipts show whether decisions/executions actually improved.
4. After the review surface exists, **count the real decisions a human made
   through the system and review their outcomes** — the first measurable answer to
   "did this help me trade better / lose less?"

## 6. Dependencies needing user approval (before any build)

| Dependency | For | Phase |
| --- | --- | --- |
| `fastapi` + `uvicorn` | read-only backend | Next (G10) |
| `mlfinlab` or equivalent (CPCV) | top research rung | Next/Later (G01) |
| OpenTelemetry / OpenLineage SDKs | observability / lineage export | Later (G12/G13) |

The base research-rigor ladder, data labels, control owner, aggregate-limit
ledger, TCA, and authorization models are designable with the current
dependency set.

## 7. What this does not change

- Still **not authorized for live or autonomous trading**; this deepens evidence
  and controls only.
- Still **one user**; institutional *shape* is not institutional *validation*.
- The **value question stays open** — Step 1 (research rigor) is the only honest
  road to answering it. Industry-standard controls around toy research still
  govern toy research.
- This plan does not certify compliance with SEC, FINRA, ASVS, WCAG, or any
  external standard.
