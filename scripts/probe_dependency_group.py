#!/usr/bin/env python3
"""Probe that a specific dependency group's packages are importable.

Usage: python scripts/probe_dependency_group.py <group>

Run in an environment with only that group's dependencies installed.
"""

from __future__ import annotations

import sys

GROUP_IMPORTS: dict[str, list[str]] = {
    "data": ["yfinance", "pandera", "beancount", "beanquery", "nautilus_trader"],
    "research": ["backtrader", "quantstats", "riskfolio", "scipy", "vectorbt"],
    "agent": ["langgraph", "agents"],
    "eval": ["deepeval"],
}


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: probe_dependency_group.py <group>", file=sys.stderr)
        return 1

    group = sys.argv[1]
    if group not in GROUP_IMPORTS:
        print(f"PASS: group {group} has no import requirements (empty group OK)")
        return 0

    expected = GROUP_IMPORTS[group]
    errors = []
    for module in expected:
        try:
            __import__(module)
        except ImportError:
            errors.append(module)

    if errors:
        for module in errors:
            print(f"FAIL: group={group} cannot import {module}", file=sys.stderr)
        return 1

    print(f"PASS: group={group} — all {len(expected)} packages importable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
