"""Human action: promote a persisted lesson draft into a recorded rule change.

This is the B4 closing step. AI drafts lessons (task lessons:draft); a human
reviews and runs this to record the rule/threshold/checklist change the lesson
justifies, with lineage back to the lesson and its receipts.

    uv run python scripts/promote_lesson.py \
        --draft-receipt data/receipts/lessons/<draft_id>.json \
        --rule-target guard.hard_stop_consecutive_losses --change-kind threshold \
        --old-value 3 --new-value 2 --rationale "..." --attester "you" \
        --lesson-doc docs/lessons/2026-06-13-<slug>.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from finharness.lesson_loop import LessonDraft
from finharness.project_paths import ROOT
from finharness.rule_change_ledger import (
    RuleChangePromotionError,
    promote_lesson_to_rule_change,
    trace_rule_change,
)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Promote a lesson draft to a rule change (B4)")
    p.add_argument("--draft-receipt", required=True)
    p.add_argument("--rule-target", required=True)
    p.add_argument(
        "--change-kind",
        required=True,
        choices=["threshold", "checklist", "allowlist", "prompt_template"],
    )
    p.add_argument("--new-value", required=True)
    p.add_argument("--old-value", default=None)
    p.add_argument("--rationale", required=True)
    p.add_argument("--attester", required=True)
    p.add_argument("--lesson-doc", required=True)
    ns = p.parse_args(argv)

    path = Path(ns.draft_receipt)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        print(json.dumps({"ok": False, "error": f"draft receipt not found: {path}"}))
        return 1
    draft = LessonDraft.model_validate(json.loads(path.read_text(encoding="utf-8")))

    try:
        change = promote_lesson_to_rule_change(
            lesson_draft=draft,
            rule_target=ns.rule_target,
            change_kind=ns.change_kind,
            new_value=ns.new_value,
            old_value=ns.old_value,
            rationale=ns.rationale,
            attester=ns.attester,
            lesson_doc_ref=ns.lesson_doc,
        )
    except RuleChangePromotionError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "rule_change_id": change.rule_change_id,
                "trace": trace_rule_change(change.rule_change_id),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
