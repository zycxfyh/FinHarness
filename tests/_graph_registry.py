"""Graph asset registry (R1) — the Graph Rationalization Audit as a checked artifact.

The audit (``docs/architecture/graph-rationalization-audit.md``) classified the repo's
graph-shaped modules in prose. R1 turns that prose into a discoverable, reviewable
registry: one ``GraphAsset`` per graph with ``id / module / task / consumer_class /
graph_needed_reason / status / owner / review_due / evidence``.

This registry is a **judgment artifact, not a deletion authorization**. A
``downgrade_candidate`` / ``archive_candidate`` / ``delete_candidate`` status records a
review decision to make later (after a usage audit, per the audit's R0/R5 rules); it does
not license removing or downgrading anything. No graph behavior changes here.

Deliberately a Python registry (like ``_policy_registry.py``), not OPA/Backstage/Temporal.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

# Closed sets — the tests assert every entry uses only these.
CONSUMER_CLASSES = frozenset(
    {"product", "ci", "headless", "docs_only", "historical", "governance"}
)
GRAPH_NEEDED_REASONS = frozenset(
    {"branching", "interrupt", "orchestration", "lineage", "provider_boundary", "none"}
)
# ``archived`` extends the audit's R1 enum for assets that are already retired (deleted),
# as opposed to *candidates* for a future archive/delete decision. finance_graph /
# trade_graph are in this state.
STATUSES = frozenset(
    {
        "keep",
        "headless_keep",
        "downgrade_candidate",
        "archive_candidate",
        "delete_candidate",
        "archived",
    }
)


@dataclass(frozen=True)
class GraphAsset:
    id: str
    module: str | None  # repo-relative path; None only for deleted/historical assets
    task: str | None  # Taskfile task that consumes it; None if no active task
    consumer_class: str
    graph_needed_reason: str
    status: str
    owner: str
    review_due: str  # ISO date for active assets; "n/a" for retired ones
    evidence: str


# --- Headless Domain Graphs (audit §Headless Domain Graphs) ------------------------------
# Keep headless and opt-in; they encode the institutional research/trading chain and must
# not be promoted into the personal cockpit.
_HEADLESS_DOMAIN: tuple[GraphAsset, ...] = (
    GraphAsset(
        id="market_data",
        module="src/finharness/market_data_graph.py",
        task="market-data:graph",
        consumer_class="headless",
        graph_needed_reason="provider_boundary",
        status="headless_keep",
        owner="headless-engine",
        review_due="2026-12-31",
        evidence="audit §Headless Domain Graphs: real adapter/provider boundary; "
        "consumers: task market-data:graph, indicator graph, market cockpit.",
    ),
    GraphAsset(
        id="indicator",
        module="src/finharness/indicator_graph.py",
        task="indicators:graph",
        consumer_class="headless",
        graph_needed_reason="lineage",
        status="headless_keep",
        owner="headless-engine",
        review_due="2026-12-31",
        evidence="audit §Headless Domain Graphs: derived evidence layer; may later become a "
        "plain feature command if too linear. consumers: task indicators:graph, daily evidence.",
    ),
    GraphAsset(
        id="events",
        module="src/finharness/events_graph.py",
        task="events:snapshot",
        consumer_class="headless",
        graph_needed_reason="lineage",
        status="headless_keep",
        owner="headless-engine",
        review_due="2026-12-31",
        evidence="audit §Headless Domain Graphs: event evidence layer; consumers: task "
        "events:snapshot, interpretation, daily evidence.",
    ),
    GraphAsset(
        id="interpretation",
        module="src/finharness/interpretation_graph.py",
        task="interpretation:graph",
        consumer_class="headless",
        graph_needed_reason="lineage",
        status="headless_keep",
        owner="headless-engine",
        review_due="2026-12-31",
        evidence="audit §Headless Domain Graphs: source-backed interpretation layer; "
        "consumers: task interpretation:graph, hypotheses, daily evidence.",
    ),
    GraphAsset(
        id="hypotheses",
        module="src/finharness/hypotheses_graph.py",
        task="hypotheses:graph",
        consumer_class="headless",
        graph_needed_reason="lineage",
        status="headless_keep",
        owner="headless-engine",
        review_due="2026-12-31",
        evidence="audit §Headless Domain Graphs: candidate hypothesis layer; consumers: "
        "task hypotheses:graph, validation.",
    ),
    GraphAsset(
        id="validation",
        module="src/finharness/validation_graph.py",
        task="validation:graph",
        consumer_class="headless",
        graph_needed_reason="provider_boundary",
        status="headless_keep",
        owner="headless-engine",
        review_due="2026-12-31",
        evidence="audit §Headless Domain Graphs: research validation boundary; important "
        "non-claim discipline. consumers: task validation:graph, proposal.",
    ),
    GraphAsset(
        id="proposal",
        module="src/finharness/proposal_graph.py",
        task="proposal:graph",
        consumer_class="headless",
        graph_needed_reason="lineage",
        status="headless_keep",
        owner="headless-engine",
        review_due="2026-12-31",
        evidence="audit §Headless Domain Graphs: trading/research proposal path, separate "
        "from personal-finance proposals. consumers: task proposal:graph, risk gate.",
    ),
    GraphAsset(
        id="risk_gate",
        module="src/finharness/risk_gate_graph.py",
        task="risk-gate:graph",
        consumer_class="headless",
        graph_needed_reason="interrupt",
        status="headless_keep",
        owner="headless-engine",
        review_due="2026-12-31",
        evidence="audit §Deletion Test Findings: earns graph shape — explicit gates, "
        "interactive/interrupt path, safety semantics. consumers: task risk-gate:graph, execution.",
    ),
    GraphAsset(
        id="execution",
        module="src/finharness/execution_graph.py",
        task="execution:graph",
        consumer_class="headless",
        graph_needed_reason="interrupt",
        status="headless_keep",
        owner="headless-engine",
        review_due="2026-12-31",
        evidence="audit §Headless Domain Graphs: safety-critical; keep isolated from "
        "cockpit. consumers: task execution:graph, post-trade.",
    ),
    GraphAsset(
        id="post_trade",
        module="src/finharness/post_trade_graph.py",
        task="post-trade:graph",
        consumer_class="headless",
        graph_needed_reason="lineage",
        status="headless_keep",
        owner="headless-engine",
        review_due="2026-12-31",
        evidence="audit §Headless Domain Graphs: review/reconciliation layer; candidate for "
        "later simplification if linear. consumers: task post-trade:graph.",
    ),
    GraphAsset(
        id="ten_layer",
        module="src/finharness/ten_layer_graph.py",
        task="ten-layer:graph",
        consumer_class="headless",
        graph_needed_reason="orchestration",
        status="headless_keep",
        owner="headless-engine",
        review_due="2026-12-31",
        evidence="audit §Deletion Test Findings: coordinates freshness/reuse across ten "
        "evidence layers — orchestration earns the shape. consumer: task ten-layer:graph.",
    ),
)

# --- Support / Governance Graphs (audit §Support / Governance Graphs) --------------------
# Most likely over-structured; useful but may not need to be graphs. R2 will pilot a
# downgrade on repo_intelligence. NOTE: a downgrade_candidate is a review flag, NOT a
# deletion/downgrade authorization.
_SUPPORT_GOVERNANCE: tuple[GraphAsset, ...] = (
    GraphAsset(
        id="repo_intelligence",
        module="src/finharness/repo_intelligence_graph.py",
        task="repo:intelligence",
        consumer_class="governance",
        graph_needed_reason="none",
        status="downgrade_candidate",
        owner="eos",
        review_due="2026-08-15",
        evidence="audit §Support/Governance + R2 pilot: report/receipt flow, not graph "
        "semantics. consumers: task repo:intelligence, quality governance, dashboard. "
        "Downgrade is a later decision after usage evidence; not authorized here.",
    ),
    GraphAsset(
        id="quality_governance",
        module="src/finharness/quality_governance_graph.py",
        task="quality:governance",
        consumer_class="governance",
        graph_needed_reason="none",
        status="downgrade_candidate",
        owner="eos",
        review_due="2026-08-15",
        evidence="audit §Support/Governance: linear report builder; plain "
        "quality_governance_report(checks, repo_intelligence) likely better. consumers: "
        "task quality:governance, release preflight, integration tests.",
    ),
    GraphAsset(
        id="release_preflight",
        module="src/finharness/release_preflight_graph.py",
        task="release:preflight",
        consumer_class="governance",
        graph_needed_reason="none",
        status="downgrade_candidate",
        owner="eos",
        review_due="2026-08-15",
        evidence="audit §Support/Governance: graph shape not obviously earning keep; plain "
        "release_preflight_report(quality, supply_chain) likely better. consumers: task "
        "release:preflight, governance dashboard.",
    ),
    GraphAsset(
        id="governance_dashboard",
        module="src/finharness/governance_dashboard_graph.py",
        task="governance:dashboard",
        consumer_class="governance",
        graph_needed_reason="none",
        status="downgrade_candidate",
        owner="eos",
        review_due="2026-08-15",
        evidence="audit §Support/Governance: likely linear dashboard report writer. "
        "consumer: task governance:dashboard.",
    ),
    GraphAsset(
        id="engineering_delivery",
        module="src/finharness/engineering_delivery_graph.py",
        task="workflow:engineering-delivery",
        consumer_class="governance",
        graph_needed_reason="none",
        status="archive_candidate",
        owner="eos",
        review_due="2026-08-15",
        evidence="audit §Support/Governance + §Unclear active value: EOS docs + gate "
        "receipts now carry most of this value; keep only if humans actively use it. "
        "consumers: task workflow:engineering-delivery, docs.",
    ),
    GraphAsset(
        id="cognitive",
        module="src/finharness/cognitive_graph.py",
        task="workflow:cognitive",
        consumer_class="governance",
        graph_needed_reason="none",
        status="archive_candidate",
        owner="eos",
        review_due="2026-08-15",
        evidence="audit §Support/Governance + §Unclear active value: useful as idea-capture "
        "history but likely not needed in the core engineering path; prove by use. "
        "consumers: task workflow:cognitive, docs.",
    ),
    GraphAsset(
        id="daily_evidence",
        module="src/finharness/daily_evidence_graph.py",
        task="workflow:daily-evidence",
        consumer_class="governance",
        graph_needed_reason="orchestration",
        status="downgrade_candidate",
        owner="eos",
        review_due="2026-08-15",
        evidence="audit §Support/Governance: bundles multiple evidence layers; 'keep or "
        "downgrade after review' — may earn orchestration shape if used operationally. "
        "consumers: task workflow:daily-evidence, tests.",
    ),
)

# --- Already Archived / Do Not Resurrect (audit §Already Archived) -----------------------
# REGISTRY CORRECTION: the audit says these live at docs/archive/legacy-graphs/, but that
# path does not exist — the files were deleted in the repo prune (commit 2166bba), not
# archived to disk. The registry records the true state: deleted, no module file.
_ARCHIVED: tuple[GraphAsset, ...] = (
    GraphAsset(
        id="finance_graph",
        module=None,
        task=None,
        consumer_class="historical",
        graph_needed_reason="none",
        status="archived",
        owner="archive",
        review_due="n/a",
        evidence="audit §Already Archived. CORRECTION: no docs/archive/legacy-graphs/ "
        "file exists; deleted in repo prune (commit 2166bba). Design history only — do "
        "not resurrect via Taskfile, scripts, tests, or cockpit.",
    ),
    GraphAsset(
        id="trade_graph",
        module=None,
        task=None,
        consumer_class="historical",
        graph_needed_reason="none",
        status="archived",
        owner="archive",
        review_due="n/a",
        evidence="audit §Already Archived. CORRECTION: no docs/archive/legacy-graphs/ "
        "file exists; deleted in repo prune (commit 2166bba). Design history only — do "
        "not resurrect.",
    ),
)


GRAPHS: tuple[GraphAsset, ...] = _HEADLESS_DOMAIN + _SUPPORT_GOVERNANCE + _ARCHIVED


def list_graphs() -> list[dict[str, str | None]]:
    """Discoverable view of the registry (one dict per graph asset)."""
    return [
        {
            "id": g.id,
            "module": g.module,
            "task": g.task,
            "consumer_class": g.consumer_class,
            "graph_needed_reason": g.graph_needed_reason,
            "status": g.status,
            "owner": g.owner,
            "review_due": g.review_due,
            "evidence": g.evidence,
        }
        for g in GRAPHS
    ]


if __name__ == "__main__":
    print(json.dumps(list_graphs(), indent=2, ensure_ascii=False))
