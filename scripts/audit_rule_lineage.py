"""Audit B4 lineage: list recorded rule changes and flag untraceable ones.

A non-empty untraceable list is a governance failure — a rule changed without
lineage to a lesson and receipts. Exit code is non-zero in that case so the
audit is usable as a gate.
"""

from __future__ import annotations

import json
import sys

from finharness.rule_change_ledger import audit_untraceable, is_traceable, load_rule_changes


def main(argv: list[str]) -> int:
    changes = load_rule_changes()
    untraceable = audit_untraceable()
    print(
        json.dumps(
            {
                "rule_changes": [
                    {
                        "id": c.rule_change_id,
                        "target": c.rule_target,
                        "kind": c.change_kind,
                        "lesson_draft_id": c.lesson_draft_id,
                        "traceable": is_traceable(c),
                    }
                    for c in changes
                ],
                "count": len(changes),
                "untraceable_ids": untraceable,
                "b4_lineage_ok": not untraceable,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not untraceable else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
