"""C3 opt-in live smoke for the --with-research enrichment path.

Manual / on-demand / **network** harness. NOT part of `task check`,
`task check`, or `task test:*` — it exercises the real RE2 provider
(OpenBB/yfinance via market_data) end to end against an **isolated synthetic sample**
(a tempdir state core + a synthetic SPY concentration position). It never touches the
operator's real ledger.

It prints a **bounded** JSON summary (which detector fired, whether the provider was
attempted, whether a research item or a data gap came back, the lineage fields present,
the receipt ref) — never the raw provider payload, the real ledger, or a stack trace.
The artifact root is **retained** (not auto-deleted) so the receipt stays readable for
audit; the summary carries ``artifact_root`` / ``receipt_exists`` / ``cleanup_hint`` and
the operator deletes it via the hint.

Exit code semantics (see the C3 mini-RFC):
- Pipeline working but provider offline / bad symbol / failure -> exit 0 with a
  sanitized data_gap (the enricher already collapses provider failures to a gap).
- Only harness / setup / schema / import failure -> non-zero.
"""

from __future__ import annotations

import json
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from finharness.allocation import record_allocation_candidates
from finharness.research_enrichment import ProviderResearchEnricher
from finharness.research_history_provider import (
    HistoricalRiskProfileProvider,
    MarketDataHistorySource,
    MarketHistory,
)
from finharness.statecore.models import Account, Position, Snapshot
from finharness.statecore.store import init_state_core, write_records

_SAMPLE_AS_OF = date(2026, 6, 20)
_LINEAGE_FIELDS = ("provider", "source", "as_of", "reconciliation")


class _AttemptRecordingSource:
    """Thin wrapper: records that a real fetch was attempted, then delegates to the
    live ``MarketDataHistorySource``. Proves the provider was actually reached."""

    def __init__(self) -> None:
        self._inner = MarketDataHistorySource()
        self.attempts: list[str] = []

    def history(self, symbol: str, *, lookback_days: int) -> MarketHistory:
        self.attempts.append(symbol)
        return self._inner.history(symbol, lookback_days=lookback_days)


def _seed_synthetic_concentration(engine: Any) -> None:
    """Write a synthetic, single-name-heavy portfolio so concentration_high fires.

    Public symbol only (SPY); no real account data.
    """
    account = Account(account_id="smoke", kind="broker", venue="synthetic", display_name="Smoke")
    snapshot = Snapshot(snapshot_id="s", kind="portfolio", as_of_utc="2026-06-19T00:00:00+00:00")
    positions = [
        Position(
            position_id="spy",
            snapshot_id="s",
            account_id="smoke",
            symbol="SPY",
            quantity=Decimal("90"),
            market_value=Decimal("9000"),
        ),
        Position(
            position_id="aapl",
            snapshot_id="s",
            account_id="smoke",
            symbol="AAPL",
            quantity=Decimal("5"),
            market_value=Decimal("1000"),
        ),
    ]
    write_records([account, snapshot, *positions], engine=engine)


def _bounded_summary(
    evidence: dict[str, Any], receipt_ref: str, attempted: bool, root: Path
) -> dict[str, Any]:
    items = evidence.get("research_evidence") or []
    first = items[0] if items else {}
    lineage = first.get("lineage") or {}
    return {
        "ok": True,
        "detector": "concentration_high",
        "provider_attempted": attempted,
        "research_item_count": len(items),
        "value_keys": sorted((first.get("value") or {}).keys()),
        "data_gaps_present": bool(evidence.get("research_evidence_gaps")),
        "lineage_fields_present": [f for f in _LINEAGE_FIELDS if f in lineage],
        "source_refs_count": len(first.get("source_refs") or []),
        "receipt_ref": receipt_ref,
        # The artifact root is retained (not auto-deleted) so a reviewer can actually
        # open the receipt after the run; receipt_exists proves it is readable now.
        "artifact_root": str(root),
        "receipt_exists": bool(receipt_ref) and Path(receipt_ref).exists(),
        "cleanup_hint": f"rm -rf {root}",
        "execution_allowed": False,
    }


def main() -> int:
    # mkdtemp (not TemporaryDirectory): keep the artifact root after the run so the
    # printed receipt_ref stays readable for audit. The operator deletes it via the
    # cleanup_hint. Synthetic sample only, so nothing sensitive is retained.
    root = Path(tempfile.mkdtemp(prefix="finharness-research-smoke-"))
    try:
        engine = init_state_core(root / "state-core.sqlite")
        try:
            _seed_synthetic_concentration(engine)
            source = _AttemptRecordingSource()
            enricher = ProviderResearchEnricher(
                provider=HistoricalRiskProfileProvider(source=source)
            )
            _report, writes = record_allocation_candidates(
                engine,
                receipt_root=root / "receipts",
                as_of_date=_SAMPLE_AS_OF,
                enricher=enricher,
            )
        finally:
            engine.dispose()

        concentration = next(
            (w for w in writes if w.proposal.kind == "concentration_high"), None
        )
        if concentration is None:
            # Synthetic seed should always trigger concentration_high; if not, the
            # harness/setup is wrong, not the pipeline.
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "synthetic sample did not trigger detector",
                        "artifact_root": str(root),
                    }
                )
            )
            return 1

        summary = _bounded_summary(
            concentration.proposal.evidence,
            concentration.receipt_ref,
            bool(source.attempts),
            root,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:  # harness/setup/schema/import failure -> non-zero
        # Sanitized: type name only, never the raw message/stack/provider payload.
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"smoke harness failure: {type(exc).__name__}",
                    "artifact_root": str(root),
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
