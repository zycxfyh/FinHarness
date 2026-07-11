"""Run pytest-only test files listed in tests/pytest-only.txt.

Rules:
- Parse the manifest, skip blank/comment lines, validate every path exists under tests/.
- Manifest must be non-empty, must not contain duplicates.
- Execute with the current Python environment's pytest.
- Return the pytest exit code unchanged.
- Never capture or mask pytest failures.
- Never touch network or modify any repository file.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _read_manifest(path: Path) -> list[str]:
    raw = path.read_text(encoding="utf-8")
    lines: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    return lines


def _validate_manifest(lines: list[str], repo_root: Path) -> list[Path]:
    if not lines:
        print("ERROR: pytest-only manifest is empty — fail closed", file=sys.stderr)
        sys.exit(2)

    seen: set[str] = set()
    resolved: list[Path] = []
    for entry in lines:
        if entry in seen:
            print(f"ERROR: duplicate entry in pytest-only manifest: {entry}", file=sys.stderr)
            sys.exit(2)
        seen.add(entry)

        test_path = repo_root / entry
        if not test_path.is_file():
            print(f"ERROR: manifest entry does not exist: {entry}", file=sys.stderr)
            sys.exit(2)

        # Security: all entries must be under tests/
        try:
            test_path.resolve().relative_to((repo_root / "tests").resolve())
        except ValueError:
            print(f"ERROR: manifest entry outside tests/: {entry}", file=sys.stderr)
            sys.exit(2)

        resolved.append(test_path)

    return resolved


def main() -> None:
    repo = _repo_root()
    manifest_path = repo / "tests" / "pytest-only.txt"

    if not manifest_path.is_file():
        print("ERROR: tests/pytest-only.txt not found", file=sys.stderr)
        sys.exit(2)

    entries = _read_manifest(manifest_path)
    test_paths = _validate_manifest(entries, repo)

    print(f"pytest manifest: {len(test_paths)} file(s) registered")
    for tp in test_paths:
        print(f"  {tp.relative_to(repo)}")

    argv = ["pytest", *[str(p) for p in test_paths]]
    print(f"running: {' '.join(argv)}")

    exit_code = pytest.main(argv[1:])  # pytest.main expects args without 'pytest' prefix
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
