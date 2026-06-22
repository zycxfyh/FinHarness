"""Draft lesson candidates from recent receipts (Loop 4 v0).

The output is a DRAFT under docs/lessons/drafts/ plus a JSON receipt. A human
reviews, edits or rejects, and promotes accepted drafts into docs/lessons/.
"""

from __future__ import annotations

import argparse
import json

from finharness.lesson_loop import draft_lessons, persist_lesson_draft


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window-days", type=int, default=14)
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Ask hermes-agent for narrative lesson candidates (drafting only).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    draft = draft_lessons(window_days=args.window_days, use_llm=args.llm)
    refs = persist_lesson_draft(draft)
    print(
        json.dumps(
            {
                "draft_id": draft.draft_id,
                "receipts_scanned": draft.receipts_scanned,
                "quality_failure_count": draft.quality_failure_count,
                "llm_provider": draft.llm_provider,
                **refs,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
