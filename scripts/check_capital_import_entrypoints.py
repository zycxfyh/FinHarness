# ruff: noqa: C901, SIM102, E501, B905
"""Validate production capital-import adapters and operator exposures — adversarial scanner."""

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

REGISTERED_ADAPTER_SYMBOLS = {
    spec.symbol for spec in PRODUCTION_CAPITAL_IMPORT_ADAPTERS
}
CANONICAL_IMPORT_CALLS = {"prepare_import", "materialize_import_batch"}
CAPITAL_ROOT_CALLS = REGISTERED_ADAPTER_SYMBOLS | CANONICAL_IMPORT_CALLS
ALL_PRODUCTION_MARKERS = (
    PRODUCTION_CAPITAL_IMPORT_SOURCE_KINDS | PRODUCTION_CAPITAL_IMPORT_MATERIALIZED_SOURCES
)
IMPORTER_SIGNAL_SUFFIXES = (
    "_import", "_ledger", "_read", "_export", "_imports", "_importer",
)


# ============================================================================
# AST helpers
# ============================================================================

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


def _reachable_call_names(tree: ast.Module, root_symbol: str) -> set[str]:
    calls: set[str] = set()
    for node in _reachable_function_nodes(tree, root_symbol):
        calls.update(_call_names(node))
    fn = _function_nodes(tree).get(root_symbol)
    if fn is not None:
        calls.update(_call_names(fn))
    return calls


def _reachable_writer_functions(
    tree: ast.Module,
    root_symbol: str,
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for node in _reachable_function_nodes(tree, root_symbol):
        writers = _call_names(node) & FORBIDDEN_GENERIC_WRITES
        if writers:
            result[node.name] = writers
    fn = _function_nodes(tree).get(root_symbol)
    if fn is not None:
        w = _call_names(fn) & FORBIDDEN_GENERIC_WRITES
        if w:
            result[fn.name] = w
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


def _decorator_qualified_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{ast.unparse(node.value)}.{node.attr}" if hasattr(ast, "unparse") else node.attr
    if isinstance(node, ast.Call):
        return _decorator_qualified_name(node.func)
    return ""


# ============================================================================
# Module I/O
# ============================================================================

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


def _py_to_module(py_path: Path, root: Path) -> str:
    rel = py_path.relative_to(root)
    s = str(rel.with_suffix("")).replace("/", ".")
    if s.startswith("src."):
        s = s[4:]
    return s


# ============================================================================
# Structured import marker extraction
# ============================================================================

def _structured_import_markers(node: ast.AST) -> set[str]:
    markers: set[str] = set()
    for sub in ast.walk(node):
        # source_kind = "broker_read" / kind = "personal_finance_export"
        if isinstance(sub, ast.Assign):
            for target in (
                sub.targets if isinstance(sub.targets, list) else [sub.targets]
            ):
                tgt_id = target.id if isinstance(target, ast.Name) else None
                if tgt_id in ("source_kind", "materialized_source", "kind"):
                    v = sub.value
                    if isinstance(v, ast.Constant) and isinstance(v.value, str):
                        if _is_production_capital_marker(v.value):
                            markers.add(v.value)
        # ReceiptIndex(kind="broker_read")
        if isinstance(sub, ast.Call):
            name = _call_name(sub)
            if name == "ReceiptIndex":
                for kw in sub.keywords:
                    if kw.arg == "kind" and isinstance(kw.value, ast.Constant):
                        if isinstance(kw.value.value, str):
                            if _is_production_capital_marker(kw.value.value):
                                markers.add(kw.value.value)
            # Snapshot(payload={"source": "broker_read"})
            if name == "Snapshot":
                for kw in sub.keywords:
                    if kw.arg == "payload" and isinstance(kw.value, ast.Dict):
                        for k, v in zip(kw.value.keys, kw.value.values):
                            if isinstance(k, ast.Constant) and k.value == "source":
                                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                                    if _is_production_capital_marker(v.value):
                                        markers.add(v.value)
    return markers


def _is_production_capital_marker(value: str) -> bool:
    return (
        value in ALL_PRODUCTION_MARKERS
        or any(value.endswith(suffix) for suffix in IMPORTER_SIGNAL_SUFFIXES)
    )


# ============================================================================
# Bypass detection — reports BOTH registered and unregistered marker writes
# ============================================================================

def find_generic_write_bypasses(
    source: str,
    *,
    registered_source_kinds: set[str] | frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
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
        markers = _structured_import_markers(node)
        registered_markers = sorted(markers & all_markers)
        unregistered_markers = sorted(markers - all_markers)
        if registered_markers:
            findings.append({
                "code": "registered_production_import_generic_write",
                "function": node.name,
                "writers": writers,
                "source_kinds": registered_markers,
            })
        if unregistered_markers:
            findings.append({
                "code": "unregistered_production_capital_import",
                "function": node.name,
                "writers": writers,
                "source_kinds": unregistered_markers,
            })
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


# ============================================================================
# Adapter contract (symbol-rooted reachable graph)
# ============================================================================

def _adapter_contract_findings(spec: Any, *, root: Path) -> list[dict[str, Any]]:
    path = _module_path(spec.module, root=root)
    if not path.is_file():
        return [{"code": "adapter_module_missing", "adapter_id": spec.adapter_id, "path": str(path)}]
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    findings: list[dict[str, Any]] = []
    fn = _function_node(tree, spec.symbol)
    if fn is None:
        findings.append({"code": "adapter_symbol_missing", "adapter_id": spec.adapter_id, "symbol": spec.symbol})
    reachable_calls = _reachable_call_names(tree, spec.symbol)
    missing = sorted(REQUIRED_ENVELOPE_CALLS - reachable_calls)
    if missing:
        findings.append({"code": "adapter_missing_canonical_envelope", "adapter_id": spec.adapter_id, "missing_calls": missing})
    writer_map = _reachable_writer_functions(tree, spec.symbol)
    if writer_map:
        findings.append({
            "code": "adapter_direct_generic_write",
            "adapter_id": spec.adapter_id,
            "root_symbol": spec.symbol,
            "writer_functions": {name: sorted(vals) for name, vals in writer_map.items()},
        })
    rf = _class_fields(tree, spec.result_type)
    if rf is None:
        findings.append({"code": "adapter_result_type_missing", "adapter_id": spec.adapter_id, "result_type": spec.result_type})
    else:
        mf = sorted(REQUIRED_RESULT_FIELDS - rf)
        if mf:
            findings.append({"code": "adapter_result_missing_identity", "adapter_id": spec.adapter_id, "missing_fields": mf})
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
        findings.append({"code": "source_kind_projection_mismatch", "registry": sorted(source_kinds), "constant": sorted(PRODUCTION_CAPITAL_IMPORT_SOURCE_KINDS)})
    return findings


# ============================================================================
# Independent exposure discovery — NO dependency on PRODUCTION_CAPITAL_IMPORT_EXPOSURES
# ============================================================================

def _discover_function_exposures(*, root: Path) -> set[tuple[str, str]]:
    discovered: set[tuple[str, str]] = set()
    for py_path in _python_files(root):
        rel_str = str(py_path.relative_to(root))
        if not rel_str.startswith("src/"):
            continue
        try:
            tree = ast.parse(py_path.read_text(encoding="utf-8"), filename=str(py_path))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        fn_map = _function_nodes(tree)
        for fn_name, fn_node in fn_map.items():
            if fn_name.startswith("_"):
                continue
            if fn_name in REGISTERED_ADAPTER_SYMBOLS:
                continue
            calls = _reachable_call_names(tree, fn_name)
            has_capital_root = bool(calls & CAPITAL_ROOT_CALLS)
            has_writer = bool(calls & FORBIDDEN_GENERIC_WRITES)
            markers = _structured_import_markers(fn_node)
            has_production_marker = bool(markers & ALL_PRODUCTION_MARKERS)
            if has_capital_root or (has_writer and has_production_marker):
                mod_name = _py_to_module(py_path, root)
                if mod_name.startswith("scripts.") or "check_" in mod_name:
                    continue
                discovered.add(("function", f"{mod_name}.{fn_name}"))
    return discovered


def _discover_script_exposures(
    *, root: Path, discovered_functions: set[tuple[str, str]] | None = None,
) -> set[tuple[str, str]]:
    discovered: set[tuple[str, str]] = set()
    if discovered_functions is None:
        discovered_functions = _discover_function_exposures(root=root)
    func_refs = {ref for kind, ref in discovered_functions if kind == "function"}
    scripts_dir = root / "scripts"
    if not scripts_dir.is_dir():
        return discovered
    for py_path in sorted(scripts_dir.rglob("*.py")):
        try:
            tree = ast.parse(py_path.read_text(encoding="utf-8"), filename=str(py_path))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        all_calls = _call_names(tree)
        main_calls: set[str] = set()
        main_fn = _function_nodes(tree).get("main")
        if main_fn is not None:
            main_calls = _call_names(main_fn)
        combined = all_calls | main_calls
        if combined & REGISTERED_ADAPTER_SYMBOLS:
            discovered.add(("script", str(py_path.relative_to(root))))
            continue
        if combined & CANONICAL_IMPORT_CALLS:
            discovered.add(("script", str(py_path.relative_to(root))))
            continue
        for call in combined:
            for func_ref in func_refs:
                if func_ref.endswith(f".{call}"):
                    discovered.add(("script", str(py_path.relative_to(root))))
    return discovered


def _task_blocks(text: str) -> dict[str, str]:
    tasks: dict[str, str] = {}
    lines = text.split("\n")
    current_name: str | None = None
    current_block: list[str] = []
    base_indent: int | None = None
    for line in lines:
        if not line.strip() or line.strip().startswith("#"):
            continue
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if stripped.endswith(":") and not stripped.startswith("-") and indent < 4:
            if current_name is not None:
                tasks[current_name] = "\n".join(current_block)
            current_name = stripped.rstrip(":").strip()
            current_block = []
            base_indent = indent + 2
        elif current_name is not None and base_indent is not None:
            current_block.append(line)
    if current_name is not None:
        tasks[current_name] = "\n".join(current_block)
    return tasks


def _discover_task_exposures(
    *, root: Path, discovered_scripts: set[tuple[str, str]] | None = None,
    discovered_functions: set[tuple[str, str]] | None = None,
) -> set[tuple[str, str]]:
    discovered: set[tuple[str, str]] = set()
    taskfile = root / "Taskfile.yml"
    if not taskfile.is_file():
        return discovered
    if discovered_scripts is None:
        discovered_scripts = _discover_script_exposures(root=root)
    if discovered_functions is None:
        discovered_functions = _discover_function_exposures(root=root)
    script_paths = {ref for kind, ref in discovered_scripts if kind == "script"}
    func_refs = {ref for kind, ref in discovered_functions if kind == "function"}
    text = taskfile.read_text(encoding="utf-8")
    blocks = _task_blocks(text)
    task_names = {k for k in blocks if k not in ("version", "tasks")}
    discovered_names: set[str] = set()
    changed = True
    while changed:
        changed = False
        for tname in sorted(task_names - discovered_names):
            block = blocks[tname]
            if any(sp in block for sp in script_paths):
                discovered.add(("task", tname))
                discovered_names.add(tname)
                changed = True
                continue
            if any(sym in block for sym in REGISTERED_ADAPTER_SYMBOLS):
                discovered.add(("task", tname))
                discovered_names.add(tname)
                changed = True
                continue
            if any(fr in block for fr in func_refs if "/" not in fr):
                discovered.add(("task", tname))
                discovered_names.add(tname)
                changed = True
                continue
            if any(f"task {tn}" in block or f"task:{tn}" in block or f"depends: [{tn}]" in block or (tn in block)
                   for tn in discovered_names):
                if tname not in discovered_names:
                    discovered.add(("task", tname))
                    discovered_names.add(tname)
                    changed = True
    return discovered


def _discover_api_exposures(*, root: Path) -> set[tuple[str, str]]:
    discovered: set[tuple[str, str]] = set()
    for py_path in _python_files(root):
        rel_str = str(py_path.relative_to(root))
        if not rel_str.startswith("src/"):
            continue
        try:
            tree = ast.parse(py_path.read_text(encoding="utf-8"), filename=str(py_path))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            is_route = False
            for d in node.decorator_list:
                qn = _decorator_qualified_name(d)
                if any(pat in qn for pat in (".post", ".put", ".patch")):
                    is_route = True
                    break
            if not is_route:
                continue
            calls = _reachable_call_names(tree, node.name)
            has_capital = bool(calls & CAPITAL_ROOT_CALLS)
            has_import_writer = bool(calls & FORBIDDEN_GENERIC_WRITES) and bool(
                _structured_import_markers(node) & ALL_PRODUCTION_MARKERS
            )
            if has_capital or has_import_writer:
                mod_name = _py_to_module(py_path, root)
                discovered.add(("api", f"{mod_name}.{node.name}"))
    return discovered


def _discover_agent_exposures(*, root: Path) -> set[tuple[str, str]]:
    discovered: set[tuple[str, str]] = set()
    for py_path in _python_files(root):
        rel_str = str(py_path.relative_to(root))
        if not rel_str.startswith("src/"):
            continue
        try:
            tree = ast.parse(py_path.read_text(encoding="utf-8"), filename=str(py_path))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            is_agent = False
            for d in node.decorator_list:
                qn = _decorator_qualified_name(d)
                if "tool" in qn.lower() or "agent" in qn.lower():
                    is_agent = True
                    break
            if not is_agent:
                continue
            calls = _reachable_call_names(tree, node.name)
            has_capital = bool(calls & CAPITAL_ROOT_CALLS)
            has_import_writer = bool(calls & FORBIDDEN_GENERIC_WRITES) and bool(
                _structured_import_markers(node) & ALL_PRODUCTION_MARKERS
            )
            if has_capital or has_import_writer:
                mod_name = _py_to_module(py_path, root)
                discovered.add(("agent", f"{mod_name}.{node.name}"))
    return discovered


def _discover_exposures(*, root: Path) -> set[tuple[str, str]]:
    functions = _discover_function_exposures(root=root)
    scripts = _discover_script_exposures(root=root, discovered_functions=functions)
    tasks = _discover_task_exposures(
        root=root, discovered_scripts=scripts, discovered_functions=functions,
    )
    apis = _discover_api_exposures(root=root)
    agents = _discover_agent_exposures(root=root)
    return functions | scripts | tasks | apis | agents


# ============================================================================
# Function existence helper (for registered exposure validation)
# ============================================================================

def _function_exposure_exists(exposure_ref: str, *, root: Path) -> bool:
    module_name, _, symbol = exposure_ref.rpartition(".")
    path = _module_path(module_name, root=root)
    if not path.is_file():
        return False
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return _function_node(tree, symbol) is not None


# ============================================================================
# Exposure findings — bidirectional
# ============================================================================

def _exposure_findings(
    *, root: Path = ROOT, discovered: set[tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
    if discovered is None:
        discovered = _discover_exposures(root=root)
    findings: list[dict[str, Any]] = []
    adapter_ids = {spec.adapter_id for spec in PRODUCTION_CAPITAL_IMPORT_ADAPTERS}
    exposure_ids: set[str] = set()
    taskfile = (root / "Taskfile.yml").read_text(encoding="utf-8") if (root / "Taskfile.yml").is_file() else ""
    registered = {(spec.exposure_kind, spec.exposure_ref) for spec in PRODUCTION_CAPITAL_IMPORT_EXPOSURES}

    for spec in PRODUCTION_CAPITAL_IMPORT_EXPOSURES:
        if spec.exposure_id in exposure_ids:
            findings.append({"code": "duplicate_exposure_id", "value": spec.exposure_id})
        exposure_ids.add(spec.exposure_id)
        if spec.adapter_id not in adapter_ids:
            findings.append({"code": "exposure_unknown_adapter", "exposure_id": spec.exposure_id, "adapter_id": spec.adapter_id})
        elif spec.exposure_kind == "task" and f"{spec.exposure_ref}:" not in taskfile:
            findings.append({"code": "task_exposure_missing", "exposure_id": spec.exposure_id})
        elif spec.exposure_kind == "script" and not (root / spec.exposure_ref).is_file():
            findings.append({"code": "script_exposure_missing", "exposure_id": spec.exposure_id})
        elif spec.exposure_kind == "function" and not _function_exposure_exists(spec.exposure_ref, root=root):
            findings.append({"code": "function_exposure_missing", "exposure_id": spec.exposure_id})
        if spec.exposure_kind in ("api", "agent"):
            if (spec.exposure_kind, spec.exposure_ref) not in discovered:
                findings.append({"code": f"registered_{spec.exposure_kind}_exposure_not_discovered", "exposure_id": spec.exposure_id})

    for kind, ref in sorted(discovered - registered):
        findings.append({"code": f"unregistered_{kind}_capital_import_exposure", "exposure_kind": kind, "exposure_ref": ref})

    for kind, ref in sorted(registered - discovered):
        if kind in ("api", "agent"):
            findings.append({"code": f"registered_{kind}_capital_import_exposure_not_discovered", "exposure_kind": kind, "exposure_ref": ref})
        else:
            findings.append({"code": "registered_capital_import_exposure_not_discovered", "exposure_kind": kind, "exposure_ref": ref})

    return findings


# ============================================================================
# Projection
# ============================================================================

def _projection_findings(path: Path) -> list[dict[str, Any]]:
    try:
        actual = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [{"code": "projection_unreadable", "path": str(path), "message": str(exc)}]
    if actual != registry_projection():
        return [{"code": "projection_drift", "path": str(path)}]
    return []


# ============================================================================
# Full validator
# ============================================================================

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
    discovered_by_kind: dict[str, list[str]] = {}
    for kind, ref in discovered:
        discovered_by_kind.setdefault(kind, []).append(ref)
    return {
        "schema": "finharness.capital_import_entrypoint_check.v1",
        "ok": not findings,
        "production_source_kinds": sorted(PRODUCTION_CAPITAL_IMPORT_SOURCE_KINDS),
        "adapter_count": len(PRODUCTION_CAPITAL_IMPORT_ADAPTERS),
        "exposure_count": len(PRODUCTION_CAPITAL_IMPORT_EXPOSURES),
        "discovered_exposures": {k: sorted(v) for k, v in sorted(discovered_by_kind.items())},
        "findings": findings,
    }


# ============================================================================
# CLI
# ============================================================================

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
