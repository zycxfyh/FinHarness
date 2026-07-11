"""Dependency-free project and artifact path definitions.

Path consumers must not import ``market_data`` merely to locate the repository.
That module owns optional data wheels and network-capable providers.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MARKET_DATA_RAW_ROOT = ROOT / "data" / "raw" / "market-data"
MARKET_DATA_NORMALIZED_ROOT = ROOT / "data" / "normalized" / "market-data"
MARKET_DATA_RECEIPT_ROOT = ROOT / "data" / "receipts" / "market-data"
NAUTILUS_CATALOG_ROOT = ROOT / "data" / "catalog" / "nautilus"


def display_path(path: Path) -> str:
    """Render repository-owned paths relative to the project root."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)
