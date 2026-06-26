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
# as opposed to *candidates* for a future archive/delete decision. ``downgraded`` marks an
# asset whose graph shape has been replaced by a plain pipeline after an authorized R2
# downgrade (repo_intelligence, R2): it still exists and is still consumed, it is simply no
# longer graph-orchestrated.
STATUSES = frozenset(
    {
        "keep",
        "headless_keep",
        "downgrade_candidate",
        "downgraded",
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


# --- Headless Domain Graphs --------------------------------------------------------------
# Retired 2026-06-26: the old ten-layer trading/research signal chain
# (market_data -> indicators -> events -> interpretation -> hypotheses -> validation ->
# proposal -> risk_gate -> execution -> post_trade, plus the ten_layer orchestrator) was
# removed wholesale. It made a trading pipeline the system's spine, which conflicts with
# the product north star ("trading can be subsumed, but is never the centre"). The new
# spine is the eight-layer Capital OS (docs/architecture/capital-os-layering.md). These
# assets now live in ``_ARCHIVED`` below.
_HEADLESS_DOMAIN: tuple[GraphAsset, ...] = ()

# --- Support / Governance Graphs (audit §Support / Governance Graphs) --------------------
# Most likely over-structured; useful but may not need to be graphs. R2 piloted (and, for
# repo_intelligence, executed) a downgrade. NOTE: downgrade_candidate is a review flag, NOT
# a deletion/downgrade authorization — quality_governance / release_preflight stay frozen.
_SUPPORT_GOVERNANCE: tuple[GraphAsset, ...] = (
    GraphAsset(
        id="repo_intelligence",
        module="src/finharness/repo_intelligence_graph.py",
        task="repo:intelligence",
        consumer_class="governance",
        graph_needed_reason="none",
        status="downgraded",
        owner="eos",
        review_due="2026-08-15",
        evidence="R2 downgrade executed: StateGraph replaced by a plain linear pipeline, "
        "graph semantics removed; output contract, task repo:intelligence, and CLI entry "
        "unchanged. Linear equivalence proven in PR #44; downgrade authorized and shipped "
        "in #46. consumers: task repo:intelligence, quality governance, dashboard.",
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
)

# --- Already Archived / Do Not Resurrect ------------------------------------------------
# finance_graph / trade_graph were deleted in an earlier repo prune (commit 2166bba). The
# ten-layer trading chain + daily_evidence bundler were retired 2026-06-26 (see the
# Headless Domain note above and docs/archive/ten-layer-trading-chain/). All record the
# true state: deleted, no module file, no active task — design history only.
def _archived(graph_id: str, evidence: str) -> GraphAsset:
    return GraphAsset(
        id=graph_id,
        module=None,
        task=None,
        consumer_class="historical",
        graph_needed_reason="none",
        status="archived",
        owner="archive",
        review_due="n/a",
        evidence=evidence,
    )


_CHAIN_RETIRED_NOTE = (
    "Retired 2026-06-26 with the ten-layer trading chain "
    "(docs/architecture/capital-os-layering.md). Deleted module + task; design history "
    "only — do not resurrect via Taskfile, scripts, tests, or cockpit."
)

_ARCHIVED: tuple[GraphAsset, ...] = (
    _archived(
        "finance_graph",
        "audit §Already Archived. No docs/archive/legacy-graphs/ file exists; deleted in "
        "repo prune (commit 2166bba). Design history only — do not resurrect.",
    ),
    _archived(
        "trade_graph",
        "audit §Already Archived. No docs/archive/legacy-graphs/ file exists; deleted in "
        "repo prune (commit 2166bba). Design history only — do not resurrect.",
    ),
    _archived(
        "market_data",
        _CHAIN_RETIRED_NOTE
        + " The shared market_data.py types module (MarketDataSnapshot etc.) is NOT this "
        "graph and stays.",
    ),
    _archived("indicator", _CHAIN_RETIRED_NOTE),
    _archived("events", _CHAIN_RETIRED_NOTE),
    _archived("interpretation", _CHAIN_RETIRED_NOTE),
    _archived("hypotheses", _CHAIN_RETIRED_NOTE),
    _archived("validation", _CHAIN_RETIRED_NOTE),
    _archived(
        "proposal",
        _CHAIN_RETIRED_NOTE
        + " (signal-proposal layer, distinct from statecore governed proposals, which stay.)",
    ),
    _archived("risk_gate", _CHAIN_RETIRED_NOTE),
    _archived("execution", _CHAIN_RETIRED_NOTE),
    _archived("post_trade", _CHAIN_RETIRED_NOTE),
    _archived("ten_layer", _CHAIN_RETIRED_NOTE),
    _archived(
        "daily_evidence",
        _CHAIN_RETIRED_NOTE + " (it bundled the first evidence layers.)",
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
