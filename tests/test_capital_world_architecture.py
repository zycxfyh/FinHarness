from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONSUMERS = (
    "src/finharness/exposure.py",
    "src/finharness/daily_brief.py",
    "src/finharness/allocation.py",
    "src/finharness/agent_context.py",
    "src/finharness/readiness.py",
    "src/finharness/api/routes_cockpit.py",
)


def test_product_consumers_do_not_select_latest_portfolio_snapshot() -> None:
    violations: list[str] = []
    for relative in CONSUMERS:
        path = ROOT / relative
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=relative)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                "latest_portfolio_snapshot" in node.name
            ):
                violations.append(f"{relative}:{node.lineno}:private latest selector")
            if isinstance(node, ast.Call):
                name = ""
                if isinstance(node.func, ast.Name):
                    name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                if name == "latest_portfolio_snapshot":
                    violations.append(f"{relative}:{node.lineno}:latest selector call")
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "limit" or len(node.args) != 1:
                continue
            limit = node.args[0]
            segment = ast.get_source_segment(text, node) or ""
            if (
                isinstance(limit, ast.Constant)
                and limit.value == 1
                and "Snapshot" in segment
                and "as_of_utc" in segment
            ):
                violations.append(f"{relative}:{node.lineno}:direct current Snapshot selection")
    assert violations == []


def test_capital_consumers_bind_the_resolved_world() -> None:
    required = {
        "src/finharness/exposure.py": "resolve_capital_world",
        "src/finharness/daily_brief.py": "resolve_capital_world",
        "src/finharness/readiness.py": "resolve_capital_world",
        "src/finharness/api/routes_cockpit.py": "resolve_capital_world",
        "src/finharness/agent_context.py": "world_id",
        "src/finharness/allocation.py": "capital_world_id",
    }
    for relative, marker in required.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert marker in text, f"{relative} does not bind the Capital World"
