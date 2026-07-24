#!/usr/bin/env python3
"""Print the fixed multilingual Agent Shell provider-redline evaluation."""

from __future__ import annotations

import json

from finharness.agent_shell_provider_redline_eval import evaluate_provider_redline


def main() -> int:
    report = evaluate_provider_redline()
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
