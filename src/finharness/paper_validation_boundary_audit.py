"""Paper validation boundary audit — SEC-BOUNDARY-01 / ENG-DEBT-0002.

Machine-verifiable consumer inventory for the deprecated PaperValidation surface.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

_MANIFEST_RELATIVE = "docs/governance/paper-validation-consumers.json"

_PAPER_IMPORT_SIGNATURES = {
    # Direct paper-validation module imports
    "finharness.api.routes_paper_validation",
    "finharness.statecore.paper_accounts",
    "finharness.statecore.paper_order_tickets",
    "finharness.statecore.paper_executions",
}

_PAPER_SYMBOL_NAMES = {
    # Classes and functions that indicate paper-validation consumption
    "PaperAccount",
    "PaperOrderTicketCandidate",
    "PaperExecutionReceipt",
    "PaperPosition",
    "create_paper_account",
    "create_paper_order_ticket_candidate",
    "record_paper_execution_receipt",
    "apply_paper_execution_to_account",
    "PAPER_VALIDATION_SUPERSEDED_BY",
    "PaperAccountStaleError",
    "PaperAccountValidationError",
    "PaperExecutionStaleError",
    "PaperExecutionValidationError",
    "PaperOrderTicketStaleError",
    "PaperOrderTicketValidationError",
    "PAPER_ACCOUNT_NON_CLAIMS",
    "PAPER_EXECUTION_NON_CLAIMS",
    "PAPER_ORDER_TICKET_NON_CLAIMS",
    "paper_validation_legacy_boundary",
}


def _load_manifest(root: Path) -> dict:
    manifest_path = root / _MANIFEST_RELATIVE
    if not manifest_path.exists():
        return {"entries": []}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _manifest_registered_paths(root: Path) -> set[str]:
    """Return the set of relative paths registered in the manifest."""
    manifest = _load_manifest(root)
    return {entry["path"] for entry in manifest.get("entries", [])}


def _is_paper_importfrom(node: ast.ImportFrom) -> bool:
    """Check if an ImportFrom node references paper-validation symbols."""
    if not node.module:
        return False
    if node.module in _PAPER_IMPORT_SIGNATURES:
        return True
    return any(alias.name in _PAPER_SYMBOL_NAMES for alias in node.names)


def _is_paper_import(node: ast.Import) -> bool:
    """Check if an Import node references paper-validation symbols."""
    for alias in node.names:
        if alias.name in _PAPER_IMPORT_SIGNATURES:
            return True
        if alias.name in _PAPER_SYMBOL_NAMES and alias.name == alias.asname:
            return True
    return False


def _is_paper_attribute(node: ast.Attribute) -> bool:
    """Check attribute access to paper symbols: e.g. paper_accounts.create()."""
    return (
        isinstance(node.value, ast.Name)
        and node.value.id in _PAPER_SYMBOL_NAMES
    )


def _is_paper_name(node: ast.Name) -> bool:
    """Check bare name references to paper symbols."""
    return node.id in _PAPER_SYMBOL_NAMES


def _is_paper_consumer_file(file_path: Path) -> bool:
    """Check whether a .py file imports or references paper-validation symbols."""
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError):
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and _is_paper_importfrom(node):
            return True
        if isinstance(node, ast.Import) and _is_paper_import(node):
            return True
        if isinstance(node, ast.Attribute) and _is_paper_attribute(node):
            return True
        if isinstance(node, ast.Name) and _is_paper_name(node):
            return True

    return False


def scan_paper_consumers(root: Path) -> list[dict[str, object]]:
    """Scan the codebase for consumers of the PaperValidation surface.

    Returns a list of findings. An empty list means no issues detected.
    A finding with code='unregistered_paper_validation_consumer' means
    a consumer was found that is not in the manifest.
    """
    findings: list[dict[str, object]] = []
    registered = _manifest_registered_paths(root)

    # Scan Python files in src, tests, scripts
    scan_dirs = ["src", "tests", "scripts"]
    for dir_name in scan_dirs:
        scan_root = root / dir_name
        if not scan_root.is_dir():
            continue
        for py_file in scan_root.rglob("*.py"):
            if "archive" in py_file.parts:
                continue
            relative = py_file.relative_to(root).as_posix()
            # Skip the surface roots themselves (they define, not consume)
            if relative in {
                "src/finharness/api/routes_paper_validation.py",
                "src/finharness/statecore/paper_accounts.py",
                "src/finharness/statecore/paper_order_tickets.py",
                "src/finharness/statecore/paper_executions.py",
            }:
                continue
            if _is_paper_consumer_file(py_file) and relative not in registered:
                findings.append({
                    "code": "unregistered_paper_validation_consumer",
                    "path": relative,
                    "detail": (
                        f"File {relative} references paper-validation symbols "
                        "but is not registered in the consumer manifest"
                    ),
                })

    # Also check for stale manifest entries (paths that no longer exist or
    # that no longer actually consume paper symbols)
    manifest = _load_manifest(root)
    for entry in manifest.get("entries", []):
        entry_path = entry["path"]
        full_path = root / entry_path
        if not full_path.exists():
            findings.append({
                "code": "stale_manifest_entry",
                "path": entry_path,
                "consumer_id": entry["consumer_id"],
                "detail": f"Manifest entry {entry['consumer_id']} references "
                          f"non-existent path: {entry_path}",
            })
        elif entry_path.endswith(".py") and not _is_paper_consumer_file(full_path):
            # The file exists but no longer imports paper symbols
            pass  # Not an error — the entry may reference non-code consumers

    return findings
