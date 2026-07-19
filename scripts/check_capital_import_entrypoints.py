"""Validate production capital-import adapters and operator exposures."""

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
    PRODUCTION_CAPITAL_IMPORT_SOURCE_KINDS,
    registry_projection,
)
from finharness.project_paths import ROOT

DEFAULT_PROJECTION = ROOT / "docs" / "governance" / "capital-import-entrypoints.json"
REQUIRED_RESULT_FIELDS = {"batch_id", "manifest_id"}
REQUIRED_ENVELOPE_CALLS = {"prepare_import", "materialize_import_batch"}
FORBIDDEN_GENERIC_WRITES = {"write_records", "upsert_records"}


def _module_path(module_name: str, *, root: Path = ROOT) -> Path:
    return root / "src" / Path(*module_name.split(".")).with_suffix(".py")


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


def _function_node(
    tree: ast.Module,
    symbol: str,
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    return next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == symbol
        ),
        None,
    )


def _class_fields(tree: ast.Module, symbol: str) -> set[str] | None:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == symbol:
            return {
                item.target.id
                for item in node.body
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
            }
    return None


def find_generic_write_bypasses(
    source: str,
    *,
    registered_source_kinds: set[str] | frozenset[str],
) -> list[dict[str, Any]]:
    """Find explicit direct writers that embed an unregistered import-like kind."""
    findings: list[dict[str, Any]] = []
    for node in ast.parse(source).body:
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
            value
            for value in strings
            if value.endswith(("_import", "_ledger", "_read")) or "import" in value
        )
        unregistered = [
            value for value in candidates if value not in registered_source_kinds
        ]
        if unregistered:
            findings.append(
                {
                    "code": "unregistered_production_capital_import",
                    "function": node.name,
                    "writers": writers,
                    "source_kinds": unregistered,
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
    missing_calls = sorted(REQUIRED_ENVELOPE_CALLS - _call_names(tree))
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


def _function_exposure_exists(exposure_ref: str, *, root: Path) -> bool:
    module_name, _, symbol = exposure_ref.rpartition(".")
    path = _module_path(module_name, root=root)
    if not path.is_file():
        return False
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return _function_node(tree, symbol) is not None


def _exposure_findings(*, root: Path = ROOT) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    adapter_ids = {spec.adapter_id for spec in PRODUCTION_CAPITAL_IMPORT_ADAPTERS}
    exposure_ids: set[str] = set()
    taskfile = (root / "Taskfile.yml").read_text(encoding="utf-8")
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
            spec.exposure_ref,
            root=root,
        ):
            findings.append(
                {"code": "function_exposure_missing", "exposure_id": spec.exposure_id}
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
    findings = [
        *_adapter_findings(root=root),
        *_exposure_findings(root=root),
        *_projection_findings(projection),
    ]
    return {
        "schema": "finharness.capital_import_entrypoint_check.v1",
        "ok": not findings,
        "production_source_kinds": sorted(PRODUCTION_CAPITAL_IMPORT_SOURCE_KINDS),
        "adapter_count": len(PRODUCTION_CAPITAL_IMPORT_ADAPTERS),
        "exposure_count": len(PRODUCTION_CAPITAL_IMPORT_EXPOSURES),
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
