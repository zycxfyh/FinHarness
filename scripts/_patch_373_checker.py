from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = '''"""Validate production capital-import adapters and operator exposures."""

from __future__ import annotations

import argparse
import ast
import json
import re
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
AUDITED_CODE_ROOTS = ("src", "scripts")
MARKER_KEYS = {"source", "kind", "source_kind", "materialized_source"}


def _module_path(module_name: str, *, root: Path = ROOT) -> Path:
    return root / "src" / Path(*module_name.split(".")).with_suffix(".py")


def _module_name(path: Path, *, root: Path) -> str:
    relative = path.relative_to(root)
    if relative.parts[0] == "src":
        return ".".join(relative.with_suffix("").parts[1:])
    return relative.as_posix()


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _call_names(tree: ast.AST) -> set[str]:
    return {
        name
        for node in ast.walk(tree)
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


def _function_node(
    tree: ast.Module,
    symbol: str,
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    return _function_nodes(tree).get(symbol)


def _reachable_function_nodes(
    tree: ast.Module,
    symbol: str,
) -> tuple[ast.FunctionDef | ast.AsyncFunctionDef, ...]:
    functions = _function_nodes(tree)
    pending = [symbol]
    visited: set[str] = set()
    result: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        node = functions.get(current)
        if node is None:
            continue
        result.append(node)
        pending.extend(sorted(_call_names(node) & set(functions), reverse=True))
    return tuple(result)


def _reachable_call_names(tree: ast.Module, symbol: str) -> set[str]:
    return {
        call
        for node in _reachable_function_nodes(tree, symbol)
        for call in _call_names(node)
    }


def _class_fields(tree: ast.Module, symbol: str) -> set[str] | None:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == symbol:
            return {
                item.target.id
                for item in node.body
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
            }
    return None


def _constant_string(node: ast.AST | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _marker_strings(nodes: tuple[ast.AST, ...]) -> set[str]:
    markers: set[str] = set()
    for root in nodes:
        for node in ast.walk(root):
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values, strict=True):
                    key_text = _constant_string(key)
                    value_text = _constant_string(value)
                    if key_text in MARKER_KEYS and value_text:
                        markers.add(value_text)
            elif isinstance(node, ast.Call):
                for keyword in node.keywords:
                    value_text = _constant_string(keyword.value)
                    if keyword.arg in MARKER_KEYS and value_text:
                        markers.add(value_text)
            elif isinstance(node, ast.Assign):
                value_text = _constant_string(node.value)
                if value_text and any(
                    isinstance(target, ast.Name)
                    and any(token in target.id.lower() for token in ("source", "kind"))
                    for target in node.targets
                ):
                    markers.add(value_text)
            elif isinstance(node, ast.AnnAssign):
                value_text = _constant_string(node.value)
                if (
                    value_text
                    and isinstance(node.target, ast.Name)
                    and any(token in node.target.id.lower() for token in ("source", "kind"))
                ):
                    markers.add(value_text)
    return markers


def _import_like(value: str) -> bool:
    return value.endswith(("_import", "_ledger", "_read")) or "import" in value


def find_generic_write_bypasses(
    source: str,
    *,
    registered_source_kinds: set[str] | frozenset[str],
    registered_materialized_sources: set[str] | frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    """Find explicit import-shaped generic writers in one Python module."""
    tree = ast.parse(source)
    findings: list[dict[str, Any]] = []
    registered = set(registered_source_kinds) | set(registered_materialized_sources)
    for function_name in sorted(_function_nodes(tree)):
        reachable_nodes = _reachable_function_nodes(tree, function_name)
        writers = sorted(
            {
                call
                for node in reachable_nodes
                for call in _call_names(node)
            }
            & FORBIDDEN_GENERIC_WRITES
        )
        if not writers:
            continue
        markers = _marker_strings(tuple(reachable_nodes))
        registered_markers = sorted(markers & registered)
        unregistered_markers = sorted(
            value for value in markers if value not in registered and _import_like(value)
        )
        if registered_markers:
            findings.append(
                {
                    "code": "registered_production_import_bypass",
                    "function": function_name,
                    "writers": writers,
                    "source_kinds": registered_markers,
                }
            )
        if unregistered_markers:
            findings.append(
                {
                    "code": "unregistered_production_capital_import",
                    "function": function_name,
                    "writers": writers,
                    "source_kinds": unregistered_markers,
                }
            )
    return findings


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
        reachable_calls: set[str] = set()
    else:
        reachable_calls = _reachable_call_names(tree, spec.symbol)
    missing_calls = sorted(REQUIRED_ENVELOPE_CALLS - reachable_calls)
    if missing_calls:
        findings.append(
            {
                "code": "adapter_missing_canonical_envelope",
                "adapter_id": spec.adapter_id,
                "missing_calls": missing_calls,
            }
        )
    forbidden = sorted(reachable_calls & FORBIDDEN_GENERIC_WRITES)
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


def _python_files(*, root: Path) -> tuple[Path, ...]:
    paths: list[Path] = []
    for root_name in AUDITED_CODE_ROOTS:
        candidate = root / root_name
        if not candidate.is_dir():
            continue
        paths.extend(
            path
            for path in candidate.rglob("*.py")
            if "archive" not in path.parts and "__pycache__" not in path.parts
        )
    return tuple(sorted(paths))


def _repository_bypass_findings(*, root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for path in _python_files(root=root):
        try:
            source = path.read_text(encoding="utf-8")
            current = find_generic_write_bypasses(
                source,
                registered_source_kinds=PRODUCTION_CAPITAL_IMPORT_SOURCE_KINDS,
                registered_materialized_sources=(
                    PRODUCTION_CAPITAL_IMPORT_MATERIALIZED_SOURCES
                ),
            )
        except (OSError, SyntaxError) as exc:
            findings.append(
                {
                    "code": "capital_import_source_unreadable",
                    "path": path.relative_to(root).as_posix(),
                    "message": str(exc),
                }
            )
            continue
        for finding in current:
            findings.append(
                {**finding, "path": path.relative_to(root).as_posix()}
            )
    return findings


def _function_exposure_exists(exposure_ref: str, *, root: Path) -> bool:
    module_name, _, symbol = exposure_ref.rpartition(".")
    path = _module_path(module_name, root=root)
    if not path.is_file():
        return False
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return _function_node(tree, symbol) is not None


def _task_blocks(text: str) -> dict[str, str]:
    matches = list(re.finditer(r"^  ([A-Za-z0-9:_-]+):\\s*$", text, re.MULTILINE))
    return {
        match.group(1): text[
            match.start() : matches[index + 1].start() if index + 1 < len(matches) else len(text)
        ]
        for index, match in enumerate(matches)
    }


def _surface_kind(path: Path, *, root: Path) -> str:
    relative = path.relative_to(root).as_posix().lower()
    if relative.startswith("src/finharness/api/") or "/routes_" in relative:
        return "api"
    if any(token in relative for token in ("agent", "tool")):
        return "agent"
    return "function"


def _discover_exposures(*, root: Path) -> tuple[dict[str, str], ...]:
    adapter_symbols = {spec.symbol for spec in PRODUCTION_CAPITAL_IMPORT_ADAPTERS}
    adapter_modules = {spec.module for spec in PRODUCTION_CAPITAL_IMPORT_ADAPTERS}
    discovered: dict[tuple[str, str], dict[str, str]] = {}
    discovered_scripts: set[str] = set()
    for path in _python_files(root=root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relative = path.relative_to(root).as_posix()
        module_name = _module_name(path, root=root)
        if relative.startswith("scripts/"):
            if _call_names(tree) & adapter_symbols:
                discovered_scripts.add(relative)
                discovered[("script", relative)] = {
                    "exposure_kind": "script",
                    "exposure_ref": relative,
                }
            continue
        for function_name in sorted(_function_nodes(tree)):
            if module_name in adapter_modules and any(
                spec.module == module_name and spec.symbol == function_name
                for spec in PRODUCTION_CAPITAL_IMPORT_ADAPTERS
            ):
                continue
            if not (_reachable_call_names(tree, function_name) & adapter_symbols):
                continue
            kind = _surface_kind(path, root=root)
            ref = f"{module_name}.{function_name}"
            discovered[(kind, ref)] = {
                "exposure_kind": kind,
                "exposure_ref": ref,
            }
    taskfile_path = root / "Taskfile.yml"
    taskfile = taskfile_path.read_text(encoding="utf-8") if taskfile_path.is_file() else ""
    script_refs = discovered_scripts | {
        spec.exposure_ref
        for spec in PRODUCTION_CAPITAL_IMPORT_EXPOSURES
        if spec.exposure_kind == "script"
    }
    for task_name, block in _task_blocks(taskfile).items():
        if any(script_ref in block for script_ref in script_refs) or any(
            symbol in block for symbol in adapter_symbols
        ):
            discovered[("task", task_name)] = {
                "exposure_kind": "task",
                "exposure_ref": task_name,
            }
    return tuple(discovered[key] for key in sorted(discovered))


def _exposure_findings(
    *, root: Path = ROOT, discovered: tuple[dict[str, str], ...] | None = None
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    adapter_ids = {spec.adapter_id for spec in PRODUCTION_CAPITAL_IMPORT_ADAPTERS}
    exposure_ids: set[str] = set()
    taskfile_path = root / "Taskfile.yml"
    taskfile = taskfile_path.read_text(encoding="utf-8") if taskfile_path.is_file() else ""
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
        elif spec.exposure_kind in {"function", "api", "agent"} and not _function_exposure_exists(
            spec.exposure_ref,
            root=root,
        ):
            findings.append(
                {"code": "function_exposure_missing", "exposure_id": spec.exposure_id}
            )
    registered = {
        (spec.exposure_kind, spec.exposure_ref)
        for spec in PRODUCTION_CAPITAL_IMPORT_EXPOSURES
    }
    for item in discovered if discovered is not None else _discover_exposures(root=root):
        key = (item["exposure_kind"], item["exposure_ref"])
        if key not in registered:
            findings.append(
                {
                    "code": f"unregistered_{item['exposure_kind']}_capital_import_exposure",
                    **item,
                }
            )
    return findings


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
        "production_materialized_sources": sorted(
            PRODUCTION_CAPITAL_IMPORT_MATERIALIZED_SOURCES
        ),
        "adapter_count": len(PRODUCTION_CAPITAL_IMPORT_ADAPTERS),
        "exposure_count": len(PRODUCTION_CAPITAL_IMPORT_EXPOSURES),
        "discovered_exposures": list(discovered),
        "findings": findings,
    }


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
'''

(ROOT / "scripts" / "check_capital_import_entrypoints.py").write_text(
    CHECKER, encoding="utf-8"
)
