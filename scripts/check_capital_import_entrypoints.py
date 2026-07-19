# ruff: noqa: C901
"""Validate production capital-import adapters and operator exposures — repository scanner."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any

from finharness.capital_import_registry import (
    PRODUCTION_CAPITAL_IMPORT_ADAPTERS,
    PRODUCTION_CAPITAL_IMPORT_EXPOSURES,
    PRODUCTION_CAPITAL_IMPORT_MATERIALIZED_SOURCES,
    PRODUCTION_CAPITAL_IMPORT_SOURCE_KINDS,
    registry_projection,
)
from finharness.project_paths import ROOT

DEFAULT_PROJECTION = ROOT / "docs" / "governance" / "capital-import-entrypoints.json"
REQUIRED_RESULT_FIELDS = {"batch_id", "manifest_id"}
REQUIRED_ENVELOPE_CALLS = {"prepare_import", "materialize_import_batch"}
FORBIDDEN_GENERIC_WRITES = {"write_records", "upsert_records"}
ALL_PRODUCTION_MARKERS = (
    PRODUCTION_CAPITAL_IMPORT_SOURCE_KINDS | PRODUCTION_CAPITAL_IMPORT_MATERIALIZED_SOURCES
)
IMPORTER_SIGNAL_SUFFIXES = (
    "_import", "_ledger", "_read",
    "_export", "_imports", "_importer",
)


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _call_names(tree_or_node: ast.AST) -> set[str]:
    return {
        name
        for node in ast.walk(tree_or_node)
        if isinstance(node, ast.Call) and (name := _call_name(node)) is not None
    }


def _function_nodes(
    tree: ast.Module,
) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _reachable_function_nodes(
    tree: ast.Module,
    root_symbol: str,
) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    fn_map = _function_nodes(tree)
    root = fn_map.get(root_symbol)
    if root is None:
        return []
    visited: set[str] = set()
    stack = [root]
    result: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    while stack:
        fn = stack.pop()
        if fn.name in visited:
            continue
        visited.add(fn.name)
        result.append(fn)
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                callee = fn_map.get(node.func.id)
                if callee is not None and callee.name not in visited:
                    stack.append(callee)
    return result


def _function_node(
    tree: ast.Module,
    symbol: str,
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    return _function_nodes(tree).get(symbol)


def _class_fields(tree: ast.Module, symbol: str) -> set[str] | None:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == symbol:
            return {
                item.target.id
                for item in node.body
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
            }
    return None


# ---------------------------------------------------------------------------
# Module I/O
# ---------------------------------------------------------------------------

def _module_path(module_name: str, *, root: Path = ROOT) -> Path:
    return root / "src" / Path(*module_name.split(".")).with_suffix(".py")


def _python_files(root: Path) -> list[Path]:
    excluded_dirs = {"__pycache__", ".venv", ".git", "node_modules"}
    files: list[Path] = []
    for top in ("src", "scripts"):
        top_dir = root / top
        if not top_dir.is_dir():
            continue
        for path in sorted(top_dir.rglob("*.py")):
            parts = set(path.parts)
            if parts & excluded_dirs:
                continue
            if "tests" in parts:
                continue
            files.append(path)
    return files


# ---------------------------------------------------------------------------
# Bypass detection
# ---------------------------------------------------------------------------

def _is_production_capital_marker(value: str) -> bool:
    return (
        value in ALL_PRODUCTION_MARKERS
        or any(value.endswith(suffix) for suffix in IMPORTER_SIGNAL_SUFFIXES)
    )


def find_generic_write_bypasses(
    source: str,
    *,
    registered_source_kinds: set[str] | frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    """Find functions that call generic writes with unregistered import markers."""
    findings: list[dict[str, Any]] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return findings
    all_markers = registered_source_kinds | PRODUCTION_CAPITAL_IMPORT_MATERIALIZED_SOURCES
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        writers = sorted(_call_names(node) & FORBIDDEN_GENERIC_WRITES)
        if not writers:
            continue
        strings = {
            value.value
            for value in ast.walk(node)
            if isinstance(value, ast.Constant) and isinstance(value.value, str)
        }
        candidates = sorted(
            value for value in strings if _is_production_capital_marker(value)
        )
        unregistered = [value for value in candidates if value not in all_markers]
        if not unregistered:
            continue
        # Also catch explicit source_kind / payload["source"] patterns
        source_kind_candidates: set[str] = set()
        for sub_node in ast.walk(node):
            if not isinstance(sub_node, ast.Assign):
                continue
            for target in (
                sub_node.targets
                if isinstance(sub_node.targets, list)
                else [sub_node.targets]
            ):
                tgt_id = target.id if isinstance(target, ast.Name) else None
                if tgt_id is not None and tgt_id in (
                    "source_kind", "materialized_source", "kind",
                ):
                    v = sub_node.value
                    if isinstance(v, ast.Constant) and isinstance(v.value, str):
                        source_kind_candidates.add(v.value)
        more_unregistered = sorted(
            v for v in source_kind_candidates if v not in all_markers
        )
        if unregistered or more_unregistered:
            findings.append(
                {
                    "code": "unregistered_production_capital_import",
                    "function": node.name,
                    "writers": writers,
                    "source_kinds": sorted(set(unregistered) | set(more_unregistered)),
                }
            )
    return findings


def _repository_bypass_findings(*, root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for path in _python_files(root):
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        hits = find_generic_write_bypasses(
            source, registered_source_kinds=PRODUCTION_CAPITAL_IMPORT_SOURCE_KINDS,
        )
        for hit in hits:
            findings.append({**hit, "path": str(path.relative_to(root))})
    return findings


# ---------------------------------------------------------------------------
# Adapter contract (symbol-rooted reachable graph)
# ---------------------------------------------------------------------------

def _adapter_contract_findings(spec: Any, *, root: Path) -> list[dict[str, Any]]:
    path = _module_path(spec.module, root=root)
    if not path.is_file():
        return [
            {
                "code": "adapter_module_missing",
                "adapter_id": spec.adapter_id,
                "path": str(path),
            }
        ]
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    findings: list[dict[str, Any]] = []
    function = _function_node(tree, spec.symbol)
    if function is None:
        findings.append(
            {
                "code": "adapter_symbol_missing",
                "adapter_id": spec.adapter_id,
                "symbol": spec.symbol,
            }
        )
    # Symbol-rooted reachable call graph
    reachable = _reachable_function_nodes(tree, spec.symbol)
    reachable_calls: set[str] = set()
    for fn_node in reachable:
        reachable_calls |= _call_names(fn_node)
    if function is not None:
        reachable_calls |= _call_names(function)
    missing_calls = sorted(REQUIRED_ENVELOPE_CALLS - reachable_calls)
    if missing_calls:
        findings.append(
            {
                "code": "adapter_missing_canonical_envelope",
                "adapter_id": spec.adapter_id,
                "missing_calls": missing_calls,
            }
        )
    if function is not None:
        forbidden = sorted(_call_names(function) & FORBIDDEN_GENERIC_WRITES)
        if forbidden:
            findings.append(
                {
                    "code": "adapter_direct_generic_write",
                    "adapter_id": spec.adapter_id,
                    "writers": forbidden,
                }
            )
    result_fields = _class_fields(tree, spec.result_type)
    if result_fields is None:
        findings.append(
            {
                "code": "adapter_result_type_missing",
                "adapter_id": spec.adapter_id,
                "result_type": spec.result_type,
            }
        )
    else:
        missing_fields = sorted(REQUIRED_RESULT_FIELDS - result_fields)
        if missing_fields:
            findings.append(
                {
                    "code": "adapter_result_missing_identity",
                    "adapter_id": spec.adapter_id,
                    "missing_fields": missing_fields,
                }
            )
    return findings


def _adapter_findings(*, root: Path = ROOT) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    adapter_ids: set[str] = set()
    source_kinds: set[str] = set()
    for spec in PRODUCTION_CAPITAL_IMPORT_ADAPTERS:
        if spec.adapter_id in adapter_ids:
            findings.append({"code": "duplicate_adapter_id", "value": spec.adapter_id})
        adapter_ids.add(spec.adapter_id)
        if spec.source_kind in source_kinds:
            findings.append({"code": "duplicate_source_kind", "value": spec.source_kind})
        source_kinds.add(spec.source_kind)
        findings.extend(_adapter_contract_findings(spec, root=root))
    if source_kinds != set(PRODUCTION_CAPITAL_IMPORT_SOURCE_KINDS):
        findings.append(
            {
                "code": "source_kind_projection_mismatch",
                "registry": sorted(source_kinds),
                "constant": sorted(PRODUCTION_CAPITAL_IMPORT_SOURCE_KINDS),
            }
        )
    return findings


# ---------------------------------------------------------------------------
# Exposure discovery
# ---------------------------------------------------------------------------

def _discover_exposures(*, root: Path) -> set[tuple[str, str]]:
    discovered: set[tuple[str, str]] = set()

    # --- Task ---
    taskfile = root / "Taskfile.yml"
    if taskfile.is_file():
        content = taskfile.read_text(encoding="utf-8")
        for spec in PRODUCTION_CAPITAL_IMPORT_EXPOSURES:
            if spec.exposure_kind == "task" and f"{spec.exposure_ref}:" in content:
                discovered.add(("task", spec.exposure_ref))

    # --- Script ---
    scripts_dir = root / "scripts"
    if scripts_dir.is_dir():
        for script_path in sorted(scripts_dir.glob("*.py")):
            try:
                source = script_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            tree = ast.parse(source, filename=str(script_path))
            calls = _call_names(tree)
            for adapter in PRODUCTION_CAPITAL_IMPORT_ADAPTERS:
                if adapter.symbol in calls:
                    discovered.add(("script", str(script_path.relative_to(root))))
                    break
            # Check for daily_change_brief runner
            if "run_daily_change_brief" in calls:
                discovered.add(("script", str(script_path.relative_to(root))))

    # --- Function ---
    for py_path in _python_files(root):
        rel_str = str(py_path.relative_to(root))
        if not rel_str.startswith("src/"):
            continue
        try:
            source = py_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        tree = ast.parse(source, filename=str(py_path))
        fn_map = _function_nodes(tree)
        for fn_name in fn_map:
            for spec in PRODUCTION_CAPITAL_IMPORT_EXPOSURES:
                if spec.exposure_kind != "function":
                    continue
                ref = spec.exposure_ref
                if "." in ref:
                    mod_name, _, sym = ref.rpartition(".")
                    mod_path = root / "src" / Path(*mod_name.split(".")).with_suffix(".py")
                    if mod_path.resolve() == py_path.resolve() and fn_name == sym:
                        discovered.add(("function", ref))

    # --- API ---
    for py_path in _python_files(root):
        try:
            source = py_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        tree = ast.parse(source, filename=str(py_path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                decorator_str = ast.unparse(decorator) if hasattr(ast, "unparse") else ""
                if not decorator_str:
                    continue
                if any(pat in decorator_str for pat in (".post", ".put", ".patch")):
                    calls = _call_names(node) | _call_names(tree)
                    for adapter in PRODUCTION_CAPITAL_IMPORT_ADAPTERS:
                        if adapter.symbol in calls:
                            mod_rel = py_path.relative_to(root)
                            mod_name = str(mod_rel.with_suffix("")).replace("/", ".")
                            discovered.add(("api", f"{mod_name}.{node.name}"))

    # --- Agent ---
    for py_path in _python_files(root):
        try:
            source = py_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        tree = ast.parse(source, filename=str(py_path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Name) and "tool" in decorator.id.lower():
                    calls = _call_names(node)
                    for adapter in PRODUCTION_CAPITAL_IMPORT_ADAPTERS:
                        if adapter.symbol in calls:
                            mod_rel = py_path.relative_to(root)
                            mod_name = str(mod_rel.with_suffix("")).replace("/", ".")
                            discovered.add(("agent", f"{mod_name}.{node.name}"))

    return discovered


# ---------------------------------------------------------------------------
# Function exposure existence check
# ---------------------------------------------------------------------------

def _function_exposure_exists(exposure_ref: str, *, root: Path) -> bool:
    module_name, _, symbol = exposure_ref.rpartition(".")
    path = _module_path(module_name, root=root)
    if not path.is_file():
        return False
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return _function_node(tree, symbol) is not None


# ---------------------------------------------------------------------------
# Exposure findings
# ---------------------------------------------------------------------------

def _exposure_findings(
    *, root: Path = ROOT, discovered: set[tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
    if discovered is None:
        discovered = _discover_exposures(root=root)
    findings: list[dict[str, Any]] = []
    adapter_ids = {spec.adapter_id for spec in PRODUCTION_CAPITAL_IMPORT_ADAPTERS}
    exposure_ids: set[str] = set()
    taskfile = (root / "Taskfile.yml").read_text(encoding="utf-8")

    registered = {
        (spec.exposure_kind, spec.exposure_ref)
        for spec in PRODUCTION_CAPITAL_IMPORT_EXPOSURES
    }

    for spec in PRODUCTION_CAPITAL_IMPORT_EXPOSURES:
        if spec.exposure_id in exposure_ids:
            findings.append({"code": "duplicate_exposure_id", "value": spec.exposure_id})
        exposure_ids.add(spec.exposure_id)
        if spec.adapter_id not in adapter_ids:
            findings.append(
                {
                    "code": "exposure_unknown_adapter",
                    "exposure_id": spec.exposure_id,
                    "adapter_id": spec.adapter_id,
                }
            )
        elif spec.exposure_kind == "task" and f"{spec.exposure_ref}:" not in taskfile:
            findings.append(
                {"code": "task_exposure_missing", "exposure_id": spec.exposure_id}
            )
        elif spec.exposure_kind == "script" and not (root / spec.exposure_ref).is_file():
            findings.append(
                {"code": "script_exposure_missing", "exposure_id": spec.exposure_id}
            )
        elif spec.exposure_kind == "function" and not _function_exposure_exists(
            spec.exposure_ref, root=root,
        ):
            findings.append(
                {"code": "function_exposure_missing", "exposure_id": spec.exposure_id}
            )
        if spec.exposure_kind in ("api", "agent"):
            registered_key = (spec.exposure_kind, spec.exposure_ref)
            if registered_key not in discovered:
                findings.append(
                    {
                        "code": f"registered_{spec.exposure_kind}_exposure_not_discovered",
                        "exposure_id": spec.exposure_id,
                    }
                )

    # Discovered but unregistered
    for kind, ref in sorted(discovered - registered):
        code = f"unregistered_{kind}_capital_import_exposure"
        findings.append(
            {"code": code, "exposure_kind": kind, "exposure_ref": ref}
        )

    # Registered but undiscovered
    for kind, ref in sorted(registered - discovered):
        if kind in ("api", "agent"):
            findings.append(
                {
                    "code": f"registered_{kind}_capital_import_exposure_not_discovered",
                    "exposure_kind": kind,
                    "exposure_ref": ref,
                }
            )
        else:
            findings.append(
                {
                    "code": "registered_capital_import_exposure_not_discovered",
                    "exposure_kind": kind,
                    "exposure_ref": ref,
                }
            )

    return findings


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------

def _projection_findings(path: Path) -> list[dict[str, Any]]:
    try:
        actual = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [
            {
                "code": "projection_unreadable",
                "path": str(path),
                "message": str(exc),
            }
        ]
    if actual != registry_projection():
        return [{"code": "projection_drift", "path": str(path)}]
    return []


# ---------------------------------------------------------------------------
# Full validator
# ---------------------------------------------------------------------------

def validate_capital_import_entrypoints(
    *,
    root: Path = ROOT,
    projection_path: Path | None = None,
) -> dict[str, Any]:
    projection = projection_path or root / DEFAULT_PROJECTION.relative_to(ROOT)
    discovered = _discover_exposures(root=root)
    findings = [
        *_adapter_findings(root=root),
        *_exposure_findings(root=root, discovered=discovered),
        *_repository_bypass_findings(root=root),
        *_projection_findings(projection),
    ]
    return {
        "schema": "finharness.capital_import_entrypoint_check.v1",
        "ok": not findings,
        "production_source_kinds": sorted(PRODUCTION_CAPITAL_IMPORT_SOURCE_KINDS),
        "adapter_count": len(PRODUCTION_CAPITAL_IMPORT_ADAPTERS),
        "exposure_count": len(PRODUCTION_CAPITAL_IMPORT_EXPOSURES),
        "discovered_exposures": sorted(
            [list(item) for item in discovered],
            key=lambda x: (x[0], x[1]),
        ),
        "findings": findings,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--projection", type=Path, default=DEFAULT_PROJECTION)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = validate_capital_import_entrypoints(projection_path=args.projection)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
