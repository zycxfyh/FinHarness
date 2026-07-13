"""Compatibility wrapper for exporting FinHarness red-team artifacts."""

from __future__ import annotations


def main() -> int:
    from export_redteam_artifacts import main as export_main

    return export_main()


if __name__ == "__main__":
    raise SystemExit(main())
