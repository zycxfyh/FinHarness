"""Single-pass market-data receipt loader v0.

Scans receipt_mds_*.json files once, returning both valid DataReceipt objects
and malformed receipt issues in a single ReceiptLoadResult.

No network calls. No ingestion. No Agent/scenario/paper integration.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from finharness.market_data import RECEIPT_ROOT, DataReceipt


@dataclass(frozen=True)
class ReceiptLoadIssue:
    """A receipt file that failed to parse or validate."""

    path: Path
    message: str
    error_type: str


@dataclass(frozen=True)
class ReceiptLoadResult:
    """Result of a single market-data receipt scan."""

    receipts: tuple[DataReceipt, ...]
    issues: tuple[ReceiptLoadIssue, ...]
    source_refs: tuple[str, ...]


def load_market_data_receipts(
    receipt_root: Path | None = None,
) -> ReceiptLoadResult:
    """Load all market-data receipts from the receipt root in one pass.

    - Missing directory: empty result.
    - Empty directory: empty result.
    - Valid receipt: added to receipts.
    - Malformed JSON or validation error: added to issues.
    - No network calls.
    - Deterministic sorted path order.

    Callers (build_data_catalog) are responsible for translating missing/empty
    directories and issues into DataGap objects.
    """
    root = receipt_root or RECEIPT_ROOT
    if not root.is_dir():
        return ReceiptLoadResult(
            receipts=(),
            issues=(),
            source_refs=(),
        )

    receipts: list[DataReceipt] = []
    issues: list[ReceiptLoadIssue] = []
    source_refs: list[str] = []

    for path in sorted(root.glob("receipt_mds_*.json")):
        if not path.is_file():
            continue
        source_refs.append(str(path))
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            receipts.append(DataReceipt.model_validate(payload))
        except json.JSONDecodeError as exc:
            issues.append(
                ReceiptLoadIssue(
                    path=path,
                    message=f"Malformed receipt JSON: {exc}",
                    error_type="json_decode_error",
                )
            )
        except ValueError as exc:
            issues.append(
                ReceiptLoadIssue(
                    path=path,
                    message=f"Receipt validation failed: {exc}",
                    error_type="validation_error",
                )
            )

    return ReceiptLoadResult(
        receipts=tuple(receipts),
        issues=tuple(issues),
        source_refs=tuple(source_refs),
    )
