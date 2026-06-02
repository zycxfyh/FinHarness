"""Run the fourth-layer source-backed interpretation LangGraph workflow."""

from __future__ import annotations

import argparse
import json

from finharness.events import DEFAULT_FORMS, DEFAULT_UNIVERSE
from finharness.interpretation_graph import run_interpretation_graph


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", default=",".join(DEFAULT_UNIVERSE))
    parser.add_argument("--forms", default=",".join(DEFAULT_FORMS))
    parser.add_argument("--max-records", type=int, default=30)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    universe = [symbol.strip().upper() for symbol in args.universe.split(",") if symbol.strip()]
    forms = [form.strip().upper() for form in args.forms.split(",") if form.strip()]
    result = run_interpretation_graph(
        universe=universe,
        forms=forms,
        max_records=args.max_records,
    )
    print(json.dumps(result["final"], ensure_ascii=False, indent=2))
    return 0 if result["final"].get("receipt_ref") else 1


if __name__ == "__main__":
    raise SystemExit(main())
