#!/usr/bin/env python3
"""Probe that a specific dependency group's packages are importable.

Usage: python scripts/probe_dependency_group.py <group>

Run in an environment with only that group's dependencies installed.
"""

from __future__ import annotations

import importlib
import sys

GROUP_IMPORTS: dict[str, list[str]] = {
    "data": ["yfinance", "pandera", "beancount", "beanquery", "nautilus_trader"],
    "research": ["backtrader", "quantstats", "riskfolio", "scipy", "vectorbt"],
    "agent": ["langgraph", "agents"],
    "eval": ["deepeval"],
}

GROUP_PROJECT_IMPORTS: dict[str, list[str]] = {
    "data": [
        "finharness.api.app",
        "finharness.beancount_adapter",
        "finharness.market_data",
    ],
    "research": [
        "finharness.metrics",
        "finharness.portfolio_risk",
        "finharness.research_rigor",
    ],
    "agent": [
        "finharness.agent_tools",
        "finharness.cognitive_graph",
    ],
    "eval": [],
    "paper": [],
    "security": [],
}


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: probe_dependency_group.py <group>", file=sys.stderr)
        return 1

    group = sys.argv[1]
    if group not in GROUP_PROJECT_IMPORTS:
        print(f"FAIL: unknown dependency group: {group}", file=sys.stderr)
        return 1

    expected = [*GROUP_IMPORTS.get(group, []), *GROUP_PROJECT_IMPORTS[group]]
    errors = []
    for module in expected:
        try:
            importlib.import_module(module)
        except Exception as exc:
            errors.append(f"{module} ({type(exc).__name__}: {exc})")

    if errors:
        for error in errors:
            print(f"FAIL: group={group} cannot import {error}", file=sys.stderr)
        return 1

    if group == "data":
        from finharness.api.app import app

        paths = set(app.openapi()["paths"])
        if "/data/catalog" not in paths or not app.state.data_surface_available:
            print("FAIL: data group installed but data API surface is unavailable", file=sys.stderr)
            return 1

    print(f"PASS: group={group} — all {len(expected)} packages importable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
