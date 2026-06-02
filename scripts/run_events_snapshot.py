"""Run the third-layer SEC EDGAR events snapshot workflow."""

from __future__ import annotations

import argparse
import json

from finharness.events import DEFAULT_FORMS, DEFAULT_UNIVERSE
from finharness.events_graph import run_events_graph


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", default=",".join(DEFAULT_UNIVERSE))
    parser.add_argument("--forms", default=",".join(DEFAULT_FORMS))
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--timeout", type=float, default=20.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    universe = [symbol.strip().upper() for symbol in args.universe.split(",") if symbol.strip()]
    forms = [form.strip().upper() for form in args.forms.split(",") if form.strip()]
    result = run_events_graph(
        universe=universe,
        forms=forms,
        per_symbol_limit=args.limit,
        timeout=args.timeout,
    )
    print(json.dumps(result["final"], ensure_ascii=False, indent=2))
    return 0 if result["final"]["receipt_ref"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
