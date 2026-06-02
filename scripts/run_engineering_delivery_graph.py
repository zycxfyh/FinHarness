"""Run the FinHarness Engineering Delivery Graph."""

from __future__ import annotations

import argparse
import json

from finharness.engineering_delivery_graph import run_engineering_delivery_graph


def _append(values: list[str] | None) -> list[str]:
    return values or []


def _parse_check(raw: str) -> dict[str, str]:
    if "=" not in raw:
        return {"name": raw, "status": "passed", "detail": ""}
    name, status = raw.split("=", 1)
    return {"name": name.strip(), "status": status.strip(), "detail": ""}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--source-ref", default="manual")
    parser.add_argument("--proposal-ref", default=None)
    parser.add_argument("--module-ref", action="append", default=[])
    parser.add_argument("--change-type", default="workflow")
    parser.add_argument("--scope", default=None)
    parser.add_argument("--non-goal", action="append", default=[])
    parser.add_argument("--success-criterion", action="append", default=[])
    parser.add_argument("--planned-file", action="append", default=[])
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--doc", action="append", default=[])
    parser.add_argument(
        "--check",
        action="append",
        default=[],
        help='Check evidence as "name=passed" or "name=failed".',
    )
    parser.add_argument("--lesson", action="append", default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_engineering_delivery_graph(
        goal=args.goal,
        source_ref=args.source_ref,
        proposal_ref=args.proposal_ref,
        module_refs=_append(args.module_ref),
        change_type=args.change_type,
        scope=args.scope,
        non_goals=_append(args.non_goal),
        success_criteria=_append(args.success_criterion),
        planned_files=_append(args.planned_file),
        changed_files=_append(args.changed_file),
        docs_updated=_append(args.doc),
        checks=[_parse_check(raw) for raw in args.check],
        lessons=_append(args.lesson),
    )
    print(json.dumps(result["final"], ensure_ascii=False, indent=2))
    return 0 if result["final"].get("quality_ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
