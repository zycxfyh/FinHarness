#!/usr/bin/env python3
"""Fail CI on import SCCs or architecture-layer violations."""

from __future__ import annotations

from finharness.architecture_boundaries import audit_architecture, render_audit


def main() -> int:
    audit = audit_architecture()
    print(render_audit(audit))
    return 0 if audit["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
