"""CognitionPlaybook loader — progressive disclosure for domain playbooks.

Agentic-space dimension: Deliberation / Evaluation.
Operating surface: Track D — Playbooks.

Level 0: list — name, description, when_to_use
Level 1: load — full procedure body

Playbooks are read-only for agents. Updates require human attestation.

v0.1 (PR #213): Uses real YAML parser (yaml.safe_load) instead of
hand-rolled YAML-like parser. Adds CognitionPlaybookFrontmatter
validation model.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

NON_CLAIMS: tuple[str, ...] = (
    "CognitionPlaybooks are review procedures, not execution authorization.",
    "Not investment advice.",
)

PLAYBOOKS_ROOT = Path(__file__).resolve().parents[2] / "docs" / "playbooks"

_BODY_START = re.compile(r"^##\s+Procedure", re.MULTILINE)


# ── frontmatter validation model ──────────────────────────────────────


class PlaybookFrontmatterError(Exception):
    """Raised when playbook frontmatter fails validation."""


class CognitionPlaybookFrontmatter(BaseModel):
    """Validated playbook YAML frontmatter."""

    model_config = ConfigDict(frozen=True)

    name: str
    version: str
    space: str
    description: str
    when_to_use: str
    required_context_packs: list[str] = []
    recommended_evaluators: list[str] = []
    side_effects: list[str] = []
    execution_allowed: bool = False


# ── model ────────────────────────────────────────────────────────────


class PlaybookSummary(BaseModel):
    """Level 0: name, description, when_to_use — no procedure body."""

    model_config = ConfigDict(frozen=True)

    name: str
    version: str
    space: str
    description: str
    when_to_use: str
    required_context_packs: list[str]
    execution_allowed: bool = False


class CognitionPlaybook(BaseModel):
    """Level 1: full playbook including procedure body."""

    model_config = ConfigDict(frozen=True)

    name: str
    version: str
    space: str
    description: str
    when_to_use: str
    required_context_packs: list[str]
    recommended_evaluators: list[str]
    side_effects: list[str]
    procedure: str
    execution_allowed: bool = False


# ── frontmatter parsing ──────────────────────────────────────────────


def _parse_frontmatter(text: str) -> dict[str, object]:
    """Parse YAML frontmatter from a markdown playbook file.

    Uses yaml.safe_load() for real YAML parsing (supports nested
    metadata, multi-line lists, etc). Falls back to empty dict on
    parse failure.
    """
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    frontmatter = parts[1].strip()
    if not frontmatter:
        return {}
    try:
        parsed = yaml.safe_load(frontmatter)
    except yaml.YAMLError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return parsed


def _validate_frontmatter(
    fm: dict[str, object],
    *,
    strict: bool = False,
) -> CognitionPlaybookFrontmatter:
    """Validate frontmatter against the expected schema.

    In strict mode, missing required fields raise PlaybookFrontmatterError.
    In non-strict mode, defaults are used for missing fields.
    """
    try:
        return CognitionPlaybookFrontmatter(**fm)
    except Exception as exc:
        if strict:
            raise PlaybookFrontmatterError(
                f"Playbook frontmatter validation failed: {exc}"
            ) from exc
        # Non-strict: return with defaults for missing fields
        return CognitionPlaybookFrontmatter(
            name=str(fm.get("name", "unknown")),
            version=str(fm.get("version", "0.1.0")),
            space=str(fm.get("space", "")),
            description=str(fm.get("description", "")),
            when_to_use=str(fm.get("when_to_use", "")),
            required_context_packs=_str_list(fm, "required_context_packs"),
            recommended_evaluators=_str_list(fm, "recommended_evaluators"),
            side_effects=_str_list(fm, "side_effects"),
            execution_allowed=bool(fm.get("execution_allowed", False)),
        )


# ── file loading ─────────────────────────────────────────────────────


def _load_playbook_file(name: str) -> tuple[dict[str, object], str] | None:
    """Load a playbook markdown file. Returns (frontmatter_dict, body) or None."""
    file_path = PLAYBOOKS_ROOT / f"{name}.md"
    if not file_path.exists():
        return None
    text = file_path.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    match = _BODY_START.search(text)
    body = text[match.start():] if match else ""
    return fm, body


# ── public API ───────────────────────────────────────────────────────


def list_cognition_playbooks() -> list[PlaybookSummary]:
    """Level 0: list all available playbooks without procedure bodies."""
    if not PLAYBOOKS_ROOT.is_dir():
        return []
    summaries: list[PlaybookSummary] = []
    for file_path in sorted(PLAYBOOKS_ROOT.glob("*.md")):
        if file_path.name == "README.md":
            continue
        name = file_path.stem
        result = _load_playbook_file(name)
        if result is None:
            continue
        fm, _body = result
        vfm = _validate_frontmatter(fm)
        summaries.append(PlaybookSummary(
            name=vfm.name,
            version=vfm.version,
            space=vfm.space,
            description=vfm.description,
            when_to_use=vfm.when_to_use,
            required_context_packs=vfm.required_context_packs,
            execution_allowed=vfm.execution_allowed,
        ))
    return summaries


def load_cognition_playbook(name: str) -> CognitionPlaybook | None:
    """Level 1: load full playbook including procedure body."""
    result = _load_playbook_file(name)
    if result is None:
        return None
    fm, body = result
    vfm = _validate_frontmatter(fm)
    return CognitionPlaybook(
        name=vfm.name,
        version=vfm.version,
        space=vfm.space,
        description=vfm.description,
        when_to_use=vfm.when_to_use,
        required_context_packs=vfm.required_context_packs,
        recommended_evaluators=vfm.recommended_evaluators,
        side_effects=vfm.side_effects,
        procedure=body,
        execution_allowed=vfm.execution_allowed,
    )


# ── helpers ──────────────────────────────────────────────────────────


def _str_list(fm: dict[str, object], key: str) -> list[str]:
    val = fm.get(key, [])
    if isinstance(val, list):
        return [str(v) for v in val]
    if isinstance(val, str):
        return [val]
    return []


def parse_frontmatter_text(text: str) -> CognitionPlaybookFrontmatter | None:
    """Parse and validate frontmatter from raw text. Returns None on failure."""
    fm = _parse_frontmatter(text)
    if not fm:
        return None
    return _validate_frontmatter(fm)
