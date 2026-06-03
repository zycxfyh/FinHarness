"""Compatibility wrapper for exporting FinHarness red-team artifacts."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

def main() -> int:
    from export_redteam_artifacts import main as export_main

    return export_main()


if __name__ == "__main__":
    raise SystemExit(main())
