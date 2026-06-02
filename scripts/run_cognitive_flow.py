"""Run the LangGraph cognitive engineering workflow."""

from __future__ import annotations

import argparse
import json

from finharness.cognitive_graph import run_cognitive_project_flow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--thought", default=None)
    parser.add_argument("--layer", default="cognitive-engineering")
    parser.add_argument("--source", default="cli")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_cognitive_project_flow(
        topic=args.topic,
        raw_thought=args.thought,
        layer=args.layer,
        source=args.source,
    )
    print(json.dumps(result["final"], ensure_ascii=False, indent=2))
    return 0 if result["final"].get("receipt_path") else 1


if __name__ == "__main__":
    raise SystemExit(main())
