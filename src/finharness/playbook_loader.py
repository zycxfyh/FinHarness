"""CognitionPlaybook loader — progressive disclosure for domain playbooks.

Agentic-space dimension: Deliberation / Evaluation.
Operating surface: Track D — Playbooks.

Level 0: list — name, description, when_to_use
Level 1: load — full procedure body

Playbooks are read-only for agents. Updates require human attestation.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict

NON_CLAIMS: tuple[str, ...] = (
    "CognitionPlaybooks are review procedures, not execution authorization.",
    "Not investment advice.",
)

PLAYBOOKS_ROOT = Path(__file__).resolve().parents[2] / "docs" / "playbooks"

_BODY_START = re.compile(r"^##\s+Procedure", re.MULTILINE)


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


def _parse_frontmatter(text: str) -> dict[str, object]:
    """Parse YAML-like frontmatter from a markdown playbook file."""
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    frontmatter = parts[1].strip()
    out: dict[str, object] = {}
    for line in frontmatter.splitlines():
        line = line.strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            out[key] = [
                v.strip().strip('"').strip("'")
                for v in value[1:-1].split(",")
                if v.strip()
            ]
        elif value.lower() in ("true", "false"):
            out[key] = value.lower() == "true"
        else:
            out[key] = value.strip('"').strip("'")
    return out


def _load_playbook_file(name: str) -> tuple[dict[str, object], str] | None:
    """Load a playbook markdown file. Returns (frontmatter, body) or None."""
    file_path = PLAYBOOKS_ROOT / f"{name}.md"
    if not file_path.exists():
        return None
    text = file_path.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    # Extract procedure body after "## Procedure"
    match = _BODY_START.search(text)
    body = text[match.start():] if match else ""
    return fm, body


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
        summaries.append(PlaybookSummary(
            name=str(fm.get("name", name)),
            version=str(fm.get("version", "0.1.0")),
            space=str(fm.get("space", "")),
            description=str(fm.get("description", "")),
            when_to_use=str(fm.get("when_to_use", "")),
            required_context_packs=_str_list(fm, "required_context_packs"),
        ))
    return summaries


def load_cognition_playbook(name: str) -> CognitionPlaybook | None:
    """Level 1: load full playbook including procedure body."""
    result = _load_playbook_file(name)
    if result is None:
        return None
    fm, body = result
    return CognitionPlaybook(
        name=str(fm.get("name", name)),
        version=str(fm.get("version", "0.1.0")),
        space=str(fm.get("space", "")),
        description=str(fm.get("description", "")),
        when_to_use=str(fm.get("when_to_use", "")),
        required_context_packs=_str_list(fm, "required_context_packs"),
        recommended_evaluators=_str_list(fm, "recommended_evaluators"),
        side_effects=_str_list(fm, "side_effects"),
        procedure=body,
    )


def _str_list(fm: dict[str, object], key: str) -> list[str]:
    val = fm.get(key, [])
    if isinstance(val, list):
        return [str(v) for v in val]
    if isinstance(val, str):
        return [val]
    return []
