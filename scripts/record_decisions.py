"""Scan the exposure map and record capital-allocation candidates as governed proposals.

Read-only: candidates carry no execution authority and surface through the existing
``/proposals`` review path. Idempotent per as-of date and detector kind.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from finharness.allocation import record_allocation_candidates
from finharness.research_enrichment import NoopResearchEnricher, ResearchEnricher
from finharness.statecore.store import init_state_core, state_core_db_path


def _build_enricher(with_research: bool) -> ResearchEnricher:
    """Default is no-op (offline, no network). ``--with-research`` opts into the RE2
    historical risk-profile provider, which may reach the network via market_data."""
    if not with_research:
        return NoopResearchEnricher()
    from finharness.research_enrichment import ProviderResearchEnricher
    from finharness.research_history_provider import (
        HistoricalRiskProfileProvider,
        MarketDataHistorySource,
    )

    return ProviderResearchEnricher(
        provider=HistoricalRiskProfileProvider(source=MarketDataHistorySource())
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record capital-allocation candidates as governed proposals (read-only)."
    )
    parser.add_argument("--db-path", type=Path, default=None)
    parser.add_argument("--receipt-root", type=Path, default=None)
    parser.add_argument(
        "--with-research",
        action="store_true",
        help=(
            "Opt in to historical research enrichment (RE2 provider; may reach the "
            "network). Off by default: the scan stays offline and deterministic."
        ),
    )
    args = parser.parse_args()
    enricher = _build_enricher(args.with_research)
    engine = init_state_core(state_core_db_path(args.db_path))
    try:
        if args.receipt_root is None:
            report, writes = record_allocation_candidates(engine, enricher=enricher)
        else:
            report, writes = record_allocation_candidates(
                engine, receipt_root=args.receipt_root, enricher=enricher
            )
    finally:
        engine.dispose()
    print(
        json.dumps(
            {
                "ok": True,
                "as_of_date": report.as_of_date,
                "candidate_count": len(writes),
                "candidates": [
                    {
                        "kind": write.proposal.kind,
                        "proposal_id": write.proposal.proposal_id,
                        "claim": write.proposal.claim,
                        "receipt_ref": write.receipt_ref,
                    }
                    for write in writes
                ],
                "execution_allowed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
