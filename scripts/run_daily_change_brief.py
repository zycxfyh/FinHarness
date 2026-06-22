"""Run the deterministic daily portfolio-change brief loop."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from finharness.config import load_settings
from finharness.daily_change_brief import (
    DEFAULT_MARKDOWN_PATH,
    DailyChangeBriefResult,
    run_daily_change_brief,
)
from finharness.runtime_log import configure_logging
from finharness.statecore.observations import ObservationThresholds
from finharness.statecore.store import StateCoreStoreError, init_state_core, open_state_core


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a governed, deterministic daily portfolio-change brief.",
    )
    parser.add_argument(
        "--portfolio-receipt",
        required=True,
        help="Path to an existing broker-read receipt JSON file.",
    )
    parser.add_argument(
        "--state-db",
        help="State-core SQLite path. Defaults to FINHARNESS_STATE_CORE_DB_PATH or data/state.",
    )
    parser.add_argument(
        "--receipt-root",
        help="Receipt root. Defaults to FINHARNESS_RECEIPT_ROOT or data/receipts.",
    )
    parser.add_argument(
        "--markdown-path",
        default=str(DEFAULT_MARKDOWN_PATH),
        help="Human-readable brief path.",
    )
    parser.add_argument(
        "--create-state",
        action="store_true",
        help="Create the state-core database if it does not exist.",
    )
    parser.add_argument(
        "--min-position-market-value",
        type=float,
        default=ObservationThresholds.min_position_market_value,
    )
    parser.add_argument(
        "--quantity-change-pct",
        type=float,
        default=ObservationThresholds.quantity_change_pct,
    )
    parser.add_argument(
        "--market-value-change-pct",
        type=float,
        default=ObservationThresholds.market_value_change_pct,
    )
    parser.add_argument(
        "--total-exposure-change-pct",
        type=float,
        default=ObservationThresholds.total_exposure_change_pct,
    )
    parser.add_argument(
        "--concentration-pct",
        type=float,
        default=ObservationThresholds.concentration_pct,
    )
    parser.add_argument(
        "--data-gap-min-market-value",
        type=float,
        default=ObservationThresholds.data_gap_min_market_value,
    )
    return parser


def _thresholds(args: argparse.Namespace) -> ObservationThresholds:
    return ObservationThresholds(
        min_position_market_value=args.min_position_market_value,
        quantity_change_pct=args.quantity_change_pct,
        market_value_change_pct=args.market_value_change_pct,
        total_exposure_change_pct=args.total_exposure_change_pct,
        concentration_pct=args.concentration_pct,
        data_gap_min_market_value=args.data_gap_min_market_value,
    )


def _print_result(result: DailyChangeBriefResult) -> None:
    payload = {"ok": True, **result.as_dict()}
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = load_settings()
    configure_logging(json_logs=settings.log_json)
    state_db = Path(args.state_db) if args.state_db else settings.state_core_db_path
    receipt_root = Path(args.receipt_root) if args.receipt_root else settings.receipt_root
    engine = None
    try:
        engine = (
            init_state_core(state_db)
            if args.create_state
            else open_state_core(state_db)
        )
        result = run_daily_change_brief(
            portfolio_receipt=Path(args.portfolio_receipt),
            engine=engine,
            thresholds=_thresholds(args),
            state_core_receipt_root=receipt_root / "state-core",
            brief_receipt_root=receipt_root / "daily-change-brief",
            markdown_path=Path(args.markdown_path),
        )
    except StateCoreStoreError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                    "execution_allowed": False,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    _print_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
