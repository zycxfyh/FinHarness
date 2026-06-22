"""Advisory vocabulary lint for FinHarness formal surfaces.

This is intentionally grep-level. It reports language that deserves a human
look, but v1 does not fail the build unless --strict is supplied.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]

EXEMPT_DIRS = {
    "docs/think",
    "docs/musings",
    "docs/archive",
    "tests",
    "vendor",
    ".venv",
    "node_modules",
}
EXEMPT_FILES = {
    "scripts/vocab_lint.py",
    "docs/adr/2026-06-18-controlled-vocabulary-and-two-tier-language.md",
    "docs/reference/glossary.md",
    "docs/proposals/2026-06-18-terminology-governance-execution-brief.md",
}
FORMAL_GLOBS = ("src/finharness/**/*.py", "scripts/*.py", "docs/**/*.md")
GLOSSARY_MARKERS = ("docs/reference/glossary.md", "../reference/glossary.md", "glossary")
ALLOW_MARKERS = (
    "non-claim",
    "non_claim",
    "not claimed",
    "not_claimed",
    "证据等级",
    "evidence at level",
    "supported at rung",
    "not a compliance certification",
    "not legal or regulatory compliance certification",
)


@dataclass(frozen=True)
class Finding:
    severity: Literal["advisory", "warn"]
    rule: str
    path: str
    line: int
    term: str
    message: str


OVERCLAIM_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("edge_proven", re.compile(r"\bedge proven\b|已证明\s*alpha", re.IGNORECASE)),
    ("safe_to_trade", re.compile(r"\bsafe to trade\b|可以交易", re.IGNORECASE)),
    ("inflated_maturity", re.compile(r"工业级|机构级")),
    ("proven_without_level", re.compile(r"\bproven\b|证明", re.IGNORECASE)),
    ("compliance_without_cert", re.compile(r"\bcompliant\b|合规", re.IGNORECASE)),
)
PROJECT_TERMS: tuple[str, ...] = (
    "Ordivon",
    "ABC",
    "B4",
    "target-state-b",
    "firebreak",
    "Hermes",
    "wheels",
    "razor",
)


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def is_exempt(path: Path) -> bool:
    relative = rel(path)
    if relative in EXEMPT_FILES:
        return True
    return any(relative == item or relative.startswith(f"{item}/") for item in EXEMPT_DIRS)


def formal_files(root: Path = ROOT) -> list[Path]:
    files: set[Path] = set()
    for pattern in FORMAL_GLOBS:
        files.update(root.glob(pattern))
    return sorted(path for path in files if path.is_file() and not is_exempt(path))


def paragraph_for_line(lines: list[str], index: int) -> str:
    start = index
    while start > 0 and lines[start - 1].strip():
        start -= 1
    end = index
    while end + 1 < len(lines) and lines[end + 1].strip():
        end += 1
    return "\n".join(lines[start : end + 1])


def nearby_window(lines: list[str], index: int, radius: int = 3) -> str:
    start = max(0, index - radius)
    end = min(len(lines), index + radius + 1)
    return "\n".join(lines[start:end])


def is_blocklist_context(lines: list[str], index: int) -> bool:
    window = nearby_window(lines, index, radius=10).lower()
    return (
        "blocked_" in window
        or "blocked language" in window
        or "restricted language" in window
        or "blocklist" in window
    )


def paragraph_has_allowance(paragraph: str) -> bool:
    lowered = paragraph.lower()
    return any(marker in lowered for marker in ALLOW_MARKERS)


def has_glossary_anchor(window: str) -> bool:
    lowered = window.lower()
    return any(marker in lowered for marker in GLOSSARY_MARKERS)


def project_term_matches(line: str) -> list[str]:
    matches: list[str] = []
    for term in PROJECT_TERMS:
        if term in {"ABC", "B4"}:
            if re.search(rf"\b{re.escape(term)}\b", line):
                matches.append(term)
        elif re.search(rf"\b{re.escape(term)}\b", line, re.IGNORECASE):
            matches.append(term)
    return matches


def lint_text(path: Path, text: str) -> list[Finding]:
    lines = text.splitlines()
    findings: list[Finding] = []
    relative = rel(path)
    for index, line in enumerate(lines):
        if is_blocklist_context(lines, index):
            continue
        paragraph = paragraph_for_line(lines, index)
        for rule, pattern in OVERCLAIM_PATTERNS:
            if pattern.search(line) and not paragraph_has_allowance(paragraph):
                findings.append(
                    Finding(
                        severity="advisory",
                        rule=rule,
                        path=relative,
                        line=index + 1,
                        term=pattern.search(line).group(0) if pattern.search(line) else "",
                        message="Potential overclaim without nearby evidence level or non-claim.",
                    )
                )
        window = nearby_window(lines, index)
        for term in project_term_matches(line):
            if has_glossary_anchor(window):
                continue
            findings.append(
                Finding(
                    severity="warn",
                    rule="project_term_anchor",
                    path=relative,
                    line=index + 1,
                    term=term,
                    message=(
                        "Project term appears on a formal surface without a "
                        "nearby glossary anchor."
                    ),
                )
            )
    return findings


def run(paths: list[Path] | None = None) -> list[Finding]:
    targets = paths or formal_files()
    findings: list[Finding] = []
    for path in targets:
        if not path.exists() or not path.is_file() or is_exempt(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        findings.extend(lint_text(path, text))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Advisory FinHarness vocabulary lint")
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--json", action="store_true", help="emit JSON findings")
    parser.add_argument("--strict", action="store_true", help="exit non-zero on findings")
    args = parser.parse_args(argv)

    paths = [path if path.is_absolute() else ROOT / path for path in args.paths]
    findings = run(paths or None)
    if args.json:
        print(json.dumps([asdict(item) for item in findings], ensure_ascii=False, indent=2))
    else:
        for item in findings:
            print(
                f"{item.severity.upper()} {item.path}:{item.line} "
                f"{item.rule} {item.term}: {item.message}"
            )
        print(
            json.dumps(
                {
                    "finding_count": len(findings),
                    "strict": args.strict,
                    "status": "fail" if findings and args.strict else "pass",
                },
                ensure_ascii=False,
            )
        )
    return 1 if findings and args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
