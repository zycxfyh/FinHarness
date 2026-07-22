#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "jsonschema==4.25.1",
#   "markdown-it-py==4.0.0",
#   "mdit-py-plugins==0.5.0",
#   "PyYAML==6.0.2",
# ]
# ///
"""Build an exact-Git-SHA documentation inventory for DOCS-BOOT-00 (#450).

This is an audit adapter, not a permanent documentation registry. It delegates
Markdown parsing to markdown-it-py, reads only tracked Git objects from the
requested baseline, validates a closed JSON shape, and writes ignored evidence
under .artifacts by default.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from urllib.parse import unquote, urlsplit

import yaml
from jsonschema import Draft202012Validator
from markdown_it import MarkdownIt
from mdit_py_plugins.front_matter import front_matter_plugin

SCHEMA_ID = "finharness.documentation_inventory.v1"
TOOL_VERSION = "finharness-doc-inventory/1.0.0"

AUDIENCES = ("user", "operator", "developer", "auditor", "maintainer", "unclassified")
DOC_TYPES = (
    "tutorial",
    "how_to",
    "reference",
    "explanation",
    "runbook",
    "architecture",
    "adr",
    "proposal",
    "review",
    "other",
    "unclassified",
)
LIFECYCLES = (
    "current",
    "preview",
    "deprecated",
    "superseded",
    "historical",
    "archived",
    "unclassified",
)
DISPOSITIONS = (
    "keep",
    "correct",
    "split",
    "merge",
    "move",
    "supersede",
    "archive",
    "delete",
    "owner_decision_required",
)
REVIEW_STATUSES = ("machine_only", "manually_reviewed")
OWNER_AREAS = (
    "product",
    "capital",
    "agent",
    "architecture",
    "engineering",
    "operations",
    "security",
    "governance",
    "research",
    "documentation",
    "repository",
    "unclassified",
)
VERIFICATION_CLASSES = (
    "generated",
    "schema_compared",
    "executable",
    "static_fact_check",
    "link_graph",
    "review_only",
    "none",
    "unclassified",
)

LOCAL_PATH_PATTERNS = (
    re.compile(r"(?<![\w.-])/root/(?:[\w./-]+)"),
    re.compile(r"(?<![\w.-])/home/[^/\s]+/(?:[\w./-]+)"),
    re.compile(r"\b[A-Za-z]:\\(?:[^\\\s]+\\)*[^\\\s]*"),
    re.compile(r"\bfile://[^\s)>]+"),
)
TASK_RE = re.compile(r"\btask\s+([A-Za-z0-9:_-]+)")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
DECLARED_LIFECYCLE_RE = re.compile(
    r"(?mi)^\s*(?:>\s*)?(?:[-*]\s*)?(?:status|lifecycle)\s*:\s*"
    r"(current|preview|deprecated|superseded|historical|archived)\b"
)
LIFECYCLE_BANNER_RE = re.compile(
    r"(?mi)^\s*>\s*(historical|archived|superseded|deprecated)\b"
)
EXTERNAL_SCHEMES = frozenset({"http", "https", "mailto", "tel", "data", "app"})
STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "that",
        "with",
        "from",
        "this",
        "into",
        "only",
        "must",
        "should",
        "will",
        "are",
        "not",
        "use",
        "using",
        "current",
        "document",
        "documentation",
        "finharness",
        "task",
        "docs",
        "file",
        "files",
        "system",
        "project",
    }
)


@dataclass(frozen=True)
class ParsedDocument:
    path: str
    title: str
    headings: tuple[str, ...]
    links: tuple[str, ...]
    images: tuple[str, ...]
    code_languages: tuple[str, ...]
    code_blocks: tuple[str, ...]
    frontmatter: dict[str, Any]
    plain_text: str
    first_lines: tuple[str, ...]
    sha256: str


class _HTMLLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.images: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag == "a" and attr_map.get("href"):
            self.links.append(str(attr_map["href"]))
        if tag == "img" and attr_map.get("src"):
            self.images.append(str(attr_map["src"]))


def _run_git(root: Path, *args: str, text: bool = True) -> subprocess.CompletedProcess[Any]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=text,
    )


def resolve_commit(root: Path, baseline: str) -> str:
    return _run_git(root, "rev-parse", f"{baseline}^{{commit}}").stdout.strip()


def tracked_repository_paths(root: Path, baseline: str) -> tuple[str, ...]:
    raw = _run_git(
        root,
        "ls-tree",
        "-r",
        "--name-only",
        "-z",
        baseline,
        text=False,
    ).stdout
    if not isinstance(raw, bytes):
        raise TypeError("git ls-tree returned text while bytes were required")
    return tuple(
        sorted(
            item.decode("utf-8", errors="strict")
            for item in raw.split(b"\0")
            if item
        )
    )


def tracked_markdown_paths(root: Path, baseline: str) -> tuple[str, ...]:
    return tuple(
        path
        for path in tracked_repository_paths(root, baseline)
        if PurePosixPath(path).suffix.lower() in {".md", ".markdown"}
    )


def read_git_text(root: Path, baseline: str, path: str) -> str:
    result = _run_git(root, "show", f"{baseline}:{path}", text=False)
    raw = result.stdout
    if not isinstance(raw, bytes):
        raise TypeError("git show returned text while bytes were required")
    return raw.decode("utf-8", errors="replace")


def _parser() -> MarkdownIt:
    parser = MarkdownIt("commonmark", {"html": True})
    parser.enable("table")
    parser.enable("strikethrough")
    parser.use(front_matter_plugin)
    return parser


def _frontmatter(content: str) -> dict[str, Any]:
    try:
        value = yaml.safe_load(content) or {}
    except yaml.YAMLError:
        return {"_parse_error": True}
    return value if isinstance(value, dict) else {"_non_mapping": value}


def parse_document(path: str, text: str) -> ParsedDocument:
    tokens = _parser().parse(text)
    headings: list[str] = []
    links: list[str] = []
    images: list[str] = []
    code_languages: list[str] = []
    code_blocks: list[str] = []
    plain_parts: list[str] = []
    metadata: dict[str, Any] = {}
    html_parser = _HTMLLinkParser()

    heading_level: str | None = None
    for token in tokens:
        if token.type == "front_matter":
            metadata = _frontmatter(token.content)
        elif token.type == "heading_open":
            heading_level = token.tag
        elif token.type == "inline":
            if heading_level:
                headings.append(token.content.strip())
                heading_level = None
            if token.content.strip():
                plain_parts.append(token.content.strip())
            for child in token.children or ():
                if child.type == "link_open":
                    href = child.attrGet("href")
                    if href:
                        links.append(href)
                elif child.type == "image":
                    src = child.attrGet("src")
                    if src:
                        images.append(src)
                elif child.type in {"html_inline", "html_block"}:
                    html_parser.feed(child.content)
        elif token.type in {"html_inline", "html_block"}:
            html_parser.feed(token.content)
        elif token.type == "fence":
            code_languages.append(token.info.strip().split(maxsplit=1)[0] if token.info else "")
            code_blocks.append(token.content)
        elif token.type == "code_block":
            code_languages.append("")
            code_blocks.append(token.content)

    links.extend(html_parser.links)
    images.extend(html_parser.images)
    title = next((heading for heading in headings if heading), PurePosixPath(path).stem)
    return ParsedDocument(
        path=path,
        title=title,
        headings=tuple(headings),
        links=tuple(dict.fromkeys(links)),
        images=tuple(dict.fromkeys(images)),
        code_languages=tuple(code_languages),
        code_blocks=tuple(code_blocks),
        frontmatter=metadata,
        plain_text="\n".join(plain_parts),
        first_lines=tuple(text.splitlines()[:40]),
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


def _collapse_posix(path: PurePosixPath) -> str | None:
    parts: list[str] = []
    for part in path.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
        else:
            parts.append(part)
    return "/".join(parts)


def resolve_internal_target(
    source_path: str,
    raw_target: str,
    tracked_paths: set[str],
) -> tuple[str, str | None]:
    target = raw_target.strip()
    if not target:
        return "empty", None
    split = urlsplit(target)
    if split.scheme.lower() in EXTERNAL_SCHEMES or split.netloc:
        return "external", None
    if target.startswith("#"):
        return "anchor", source_path
    clean = unquote(split.path).strip()
    if not clean:
        return "anchor", source_path
    if clean.startswith("/"):
        return "repo_absolute_or_external", clean
    collapsed = _collapse_posix(PurePosixPath(source_path).parent / clean)
    if collapsed is None:
        return "outside_repo", clean

    candidates = [collapsed]
    suffix = PurePosixPath(collapsed).suffix.lower()
    if not suffix:
        candidates.extend((f"{collapsed}.md", f"{collapsed}/README.md"))
    elif collapsed.endswith("/"):
        candidates.append(f"{collapsed}README.md")
    for candidate in candidates:
        if candidate in tracked_paths:
            return "internal", candidate
    directory_prefix = f"{collapsed.rstrip('/')}/"
    if any(path.startswith(directory_prefix) for path in tracked_paths):
        return "internal_directory", collapsed
    return "missing", collapsed


def _load_catalog(root: Path, baseline: str) -> dict[str, Any]:
    path = "docs/architecture/system-catalog.yml"
    try:
        value = yaml.safe_load(read_git_text(root, baseline, path)) or {}
    except subprocess.CalledProcessError:
        return {}
    return value if isinstance(value, dict) else {}


def _load_task_names(root: Path, baseline: str) -> set[str]:
    try:
        data = yaml.safe_load(read_git_text(root, baseline, "Taskfile.yml")) or {}
    except subprocess.CalledProcessError:
        return set()
    tasks = data.get("tasks", {}) if isinstance(data, dict) else {}
    return {str(name) for name in tasks} if isinstance(tasks, dict) else set()


def _historical_prefixes(catalog: dict[str, Any]) -> tuple[str, ...]:
    navigation = catalog.get("documentation", {}).get("navigation", {})
    values = [
        *navigation.get("historical_roots", []),
        *navigation.get("historical_paths", []),
        "docs/archive",
        "experiments/archive",
    ]
    return tuple(sorted({str(value).rstrip("/") for value in values if value}))


def _is_under(path: str, prefixes: Iterable[str]) -> bool:
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in prefixes)


def current_reachable_paths(
    documents: dict[str, ParsedDocument],
    resolved_links: dict[str, list[dict[str, Any]]],
    catalog: dict[str, Any],
) -> set[str]:
    navigation = catalog.get("documentation", {}).get("navigation", {})
    entrypoints = [str(value) for value in navigation.get("entrypoints", ["README.md"])]
    historical = _historical_prefixes(catalog)
    queue: deque[str] = deque(entrypoints)
    seen: set[str] = set()
    while queue:
        path = queue.popleft()
        if path in seen or path not in documents or _is_under(path, historical):
            continue
        seen.add(path)
        for link in resolved_links[path]:
            if link["kind"] == "internal" and link["target"]:
                queue.append(str(link["target"]))
    return seen


def candidate_type(path: str, title: str) -> str:
    lower = path.lower()
    title_lower = title.lower()
    name = PurePosixPath(path).name.lower()
    if "/tutorial" in lower or "tutorial" in title_lower or "golden path" in title_lower:
        return "tutorial"
    if "/how-to" in lower or "/how_to" in lower or title_lower.startswith("how to "):
        return "how_to"
    if "/runbook" in lower or "/operations/" in lower or "/playbooks/" in lower:
        return "runbook"
    if "/adr/" in lower or PurePosixPath(path).parent.name == "adr":
        return "adr"
    if "/proposals/" in lower or PurePosixPath(path).parent.name == "proposals":
        return "proposal"
    if "/reviews/" in lower or PurePosixPath(path).parent.name == "reviews":
        return "review"
    if "/architecture/" in lower or "/modules/" in lower:
        return "architecture"
    if "/reference" in lower or title_lower.endswith(" reference"):
        return "reference"
    if "/templates/" in lower or "checklist" in title_lower or "standard" in title_lower:
        return "reference"
    if any(
        marker in lower
        for marker in (
            "/engineering/",
            "/explanation/",
            "/think/",
            "/lessons/",
            "/product/",
            "/security/",
            "/research/",
        )
    ):
        return "explanation"
    if name in {"contributing.md", "agents.md", "context.md", "readme.md"}:
        return "other"
    if lower.startswith("ideas/"):
        return "proposal"
    if lower.startswith("data/"):
        return "reference"
    if lower.startswith("experiments/"):
        return "explanation"
    if lower.startswith("docs/"):
        return "other"
    return "other"


def candidate_audience(path: str, doc_type: str) -> str:
    lower = path.lower()
    name = PurePosixPath(path).name.lower()
    if path in {"README.md", "docs/README.md"}:
        return "user"
    if path in {"CONTRIBUTING.md", "AGENTS.md", "CONTEXT.md"}:
        return "developer"
    if "/security/" in lower or "/audits/" in lower or "/governance/" in lower:
        return "auditor"
    if "/operations/" in lower or "/playbooks/" in lower or doc_type == "runbook":
        return "operator"
    if "/how-to/" in lower:
        if any(
            marker in name
            for marker in (
                "mature-wheel",
                "issue-worktree",
            )
        ):
            return "developer"
        if any(
            marker in name
            for marker in (
                "audit-issue",
                "governance-inventories",
                "lesson-to-rule",
            )
        ):
            return "maintainer"
        return "user"
    if "/tutorial" in lower:
        return "user"
    if "/reference/" in lower:
        return "operator"
    if any(
        marker in lower
        for marker in (
            "/architecture/",
            "/engineering/",
            "/adr/",
            "/proposals/",
            "/reviews/",
            "/notes/",
            "/think/",
            "/lessons/",
            "/modules/",
            "/templates/",
            "/research/",
            "/product/",
        )
    ):
        return "maintainer"
    if any(
        marker in lower
        for marker in (
            "finance-operating-model",
            "personal-governance",
            "investing-first-principles",
        )
    ):
        return "user"
    if path in {"docs/week-01.md", "docs/wheels.md"}:
        return "developer"
    if lower.startswith(".github/"):
        return "repository"
    if lower.startswith("ideas/"):
        return "maintainer"
    if lower.startswith("data/"):
        return "operator"
    if lower.startswith("experiments/"):
        return "developer"
    return "maintainer"


def _declared_lifecycle(document: ParsedDocument) -> str | None:
    for key in ("lifecycle", "status"):
        value = document.frontmatter.get(key)
        if isinstance(value, str) and value.lower() in LIFECYCLES:
            return value.lower()
    first = "\n".join(document.first_lines)
    declared = DECLARED_LIFECYCLE_RE.search(first)
    if declared:
        return declared.group(1).lower()
    banner = LIFECYCLE_BANNER_RE.search(first)
    return banner.group(1).lower() if banner else None


def candidate_lifecycle(
    path: str,
    document: ParsedDocument,
    current_reachable: set[str],
    historical_prefixes: tuple[str, ...],
) -> str:
    declared = _declared_lifecycle(document)
    if _is_under(path, historical_prefixes):
        if declared in {"archived", "historical"}:
            return declared
        return "historical"
    if declared:
        return declared
    if path in current_reachable:
        return "current"
    if "/reviews/" in path.lower():
        return "historical"
    if "/proposals/" in path.lower():
        return "preview"
    return "unclassified"


def candidate_owner_area(path: str, current: bool) -> str:
    lower = path.lower()
    if path in {"README.md", "docs/README.md"} or any(
        marker in lower for marker in ("/tutorials/", "/how-to/", "/reference/")
    ):
        return "documentation"
    if lower.startswith(".github/"):
        return "repository"
    if "/product/" in lower or "product-north-star" in lower:
        return "product"
    if any(marker in lower for marker in ("capital", "finance", "investing")):
        return "capital"
    if "agent" in lower:
        return "agent"
    if "/architecture/" in lower or "/adr/" in lower or "/modules/" in lower:
        return "architecture"
    if "/engineering/" in lower or path in {"AGENTS.md", "CONTRIBUTING.md", "CONTEXT.md"}:
        return "engineering"
    if "/operations/" in lower or "/playbooks/" in lower:
        return "operations"
    if "/security/" in lower:
        return "security"
    if "/governance/" in lower or "/audits/" in lower:
        return "governance"
    if "/research/" in lower:
        return "research"
    if current:
        return "documentation"
    return "unclassified"


def candidate_verification_class(
    document: ParsedDocument,
    doc_type: str,
    current: bool,
) -> str:
    text = "\n".join((*document.first_lines, *document.code_blocks))
    if "Generated from `" in text and "Do not edit" in text:
        return "generated"
    if "schema" in text.lower() and any(
        name in text for name in ("Pydantic", "SQLModel", "OpenAPI")
    ):
        return "schema_compared"
    if doc_type in {"tutorial", "how_to", "runbook"} and TASK_RE.search(text):
        return "executable"
    if "task docs:current-check" in text or "task governance:check" in text:
        return "static_fact_check"
    if doc_type in {"adr", "proposal", "review"}:
        return "review_only"
    if current:
        return "link_graph"
    return "none"


def canonical_source_candidates(document: ParsedDocument) -> list[str]:
    text = "\n".join((*document.first_lines, document.plain_text[:3000]))
    candidates: list[str] = []
    known = (
        "Taskfile.yml",
        "docs/architecture/system-catalog.yml",
        "docs/governance/debt-register.json",
        "GitHub Issues",
        "OpenAPI",
        "Pydantic",
        "SQLModel",
    )
    candidates.extend(value for value in known if value.lower() in text.lower())
    generated_match = re.search(r"Generated from `([^`]+)`", text, re.IGNORECASE)
    if generated_match:
        candidates.insert(0, generated_match.group(1))
    return list(dict.fromkeys(candidates))


def verifier_candidates(
    document: ParsedDocument,
    known_tasks: set[str],
) -> list[str]:
    text = "\n".join((*document.first_lines, *document.code_blocks))
    values = [
        f"task {name}"
        for name in TASK_RE.findall(text)
        if name in known_tasks and "check" in name
    ]
    if "Do not edit" in text and "Generated from" in text:
        values.append("generated-output drift check")
    return list(dict.fromkeys(values))


def _local_path_findings(text: str) -> list[str]:
    findings: list[str] = []
    for pattern in LOCAL_PATH_PATTERNS:
        findings.extend(match.group(0) for match in pattern.finditer(text))
    return sorted(set(findings))


def _token_set(text: str) -> set[str]:
    return {
        word.lower()
        for word in WORD_RE.findall(text)
        if word.lower() not in STOPWORDS and not word.isdigit()
    }


def similarity_clusters(documents: dict[str, ParsedDocument]) -> list[dict[str, Any]]:
    eligible = {
        path: _token_set(document.plain_text)
        for path, document in documents.items()
        if len(_token_set(document.plain_text)) >= 60
    }
    adjacency: dict[str, set[str]] = defaultdict(set)
    paths = sorted(eligible)
    for index, left in enumerate(paths):
        for right in paths[index + 1 :]:
            union = eligible[left] | eligible[right]
            if not union:
                continue
            score = len(eligible[left] & eligible[right]) / len(union)
            if score >= 0.72:
                adjacency[left].add(right)
                adjacency[right].add(left)

    clusters: list[dict[str, Any]] = []
    visited: set[str] = set()
    for path in paths:
        if path in visited or not adjacency[path]:
            continue
        component: set[str] = set()
        queue = [path]
        while queue:
            current = queue.pop()
            if current in component:
                continue
            component.add(current)
            queue.extend(adjacency[current] - component)
        visited.update(component)
        clusters.append(
            {
                "kind": "content_similarity",
                "members": sorted(component),
                "reason": "token-set Jaccard similarity >= 0.72; manual review required",
            }
        )
    return clusters


def _title_clusters(documents: dict[str, ParsedDocument]) -> list[dict[str, Any]]:
    by_title: dict[str, list[str]] = defaultdict(list)
    for path, document in documents.items():
        normalized = re.sub(r"\W+", " ", document.title.lower()).strip()
        if normalized:
            by_title[normalized].append(path)
    return [
        {
            "kind": "duplicate_title",
            "members": sorted(paths),
            "reason": f"same normalized title: {title}",
        }
        for title, paths in sorted(by_title.items())
        if len(paths) > 1
    ]


def _task_clusters(
    documents: dict[str, ParsedDocument],
    known_tasks: set[str],
) -> list[dict[str, Any]]:
    task_paths: dict[str, set[str]] = defaultdict(set)
    for path, document in documents.items():
        text = "\n".join((document.plain_text, *document.code_blocks))
        for task in TASK_RE.findall(text):
            if task in known_tasks:
                task_paths[task].add(path)
    return [
        {
            "kind": "repeated_task_claim",
            "members": sorted(paths),
            "reason": f"`task {task}` appears in {len(paths)} documents",
            "task": task,
        }
        for task, paths in sorted(task_paths.items())
        if len(paths) >= 3
    ]


def inventory_schema() -> dict[str, Any]:
    string_array = {"type": "array", "items": {"type": "string"}, "uniqueItems": True}
    finding_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["code", "severity", "detail"],
        "properties": {
            "code": {"type": "string"},
            "severity": {"enum": ["info", "warning", "error"]},
            "detail": {"type": "string"},
        },
    }
    item = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "path",
            "title",
            "sha256",
            "current_navigation_reachable",
            "inbound_internal_links",
            "outbound_internal_links",
            "external_links",
            "primary_audience",
            "secondary_audiences",
            "document_type",
            "lifecycle_assessment",
            "canonical_source_candidates",
            "owner_area",
            "verification_class",
            "verifier_candidates",
            "conflict_cluster_ids",
            "observed_findings",
            "recommended_disposition",
            "review_status",
        ],
        "properties": {
            "path": {"type": "string"},
            "title": {"type": "string"},
            "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "current_navigation_reachable": {"type": "boolean"},
            "inbound_internal_links": string_array,
            "outbound_internal_links": string_array,
            "external_links": string_array,
            "primary_audience": {"enum": list(AUDIENCES)},
            "secondary_audiences": string_array,
            "document_type": {"enum": list(DOC_TYPES)},
            "lifecycle_assessment": {"enum": list(LIFECYCLES)},
            "canonical_source_candidates": string_array,
            "owner_area": {"enum": list(OWNER_AREAS)},
            "verification_class": {"enum": list(VERIFICATION_CLASSES)},
            "verifier_candidates": string_array,
            "conflict_cluster_ids": string_array,
            "observed_findings": {"type": "array", "items": finding_schema},
            "recommended_disposition": {"enum": list(DISPOSITIONS)},
            "review_status": {"enum": list(REVIEW_STATUSES)},
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema",
            "tool",
            "baseline_sha",
            "scan_roots",
            "exclusions",
            "known_limitations",
            "summary",
            "documents",
            "conflict_clusters",
        ],
        "properties": {
            "schema": {"const": SCHEMA_ID},
            "tool": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "version", "markdown_parser"],
                "properties": {
                    "name": {"const": "audit_documentation_inventory.py"},
                    "version": {"const": TOOL_VERSION},
                    "markdown_parser": {"type": "string"},
                },
            },
            "baseline_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
            "scan_roots": string_array,
            "exclusions": string_array,
            "known_limitations": string_array,
            "summary": {"type": "object"},
            "documents": {"type": "array", "items": item},
            "conflict_clusters": {"type": "array", "items": {"type": "object"}},
        },
    }


def _finding(code: str, severity: str, detail: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "detail": detail}


def _disposition(
    lifecycle: str,
    current: bool,
    findings: list[dict[str, str]],
    conflict_ids: list[str],
) -> str:
    error_codes = {item["code"] for item in findings if item["severity"] == "error"}
    warning_codes = {item["code"] for item in findings if item["severity"] == "warning"}
    if current and error_codes:
        return "correct"
    if current and ("mixed_document_responsibility" in warning_codes):
        return "split"
    if conflict_ids:
        return "owner_decision_required"
    if lifecycle in {"historical", "archived"}:
        return "keep"
    if current:
        return "keep"
    return "owner_decision_required"


def build_inventory(root: Path, baseline: str) -> dict[str, Any]:  # noqa: C901
    baseline_sha = resolve_commit(root, baseline)
    tracked_all = set(tracked_repository_paths(root, baseline_sha))
    paths = tuple(
        path
        for path in sorted(tracked_all)
        if PurePosixPath(path).suffix.lower() in {".md", ".markdown"}
    )
    documents = {
        path: parse_document(path, read_git_text(root, baseline_sha, path)) for path in paths
    }

    resolved_links: dict[str, list[dict[str, Any]]] = {}
    inbound: dict[str, set[str]] = defaultdict(set)
    for path, document in documents.items():
        entries: list[dict[str, Any]] = []
        for raw_target in document.links:
            kind, target = resolve_internal_target(path, raw_target, tracked_all)
            entry = {"raw": raw_target, "kind": kind, "target": target}
            entries.append(entry)
            if kind == "internal" and target:
                inbound[target].add(path)
        resolved_links[path] = entries

    catalog = _load_catalog(root, baseline_sha)
    known_tasks = _load_task_names(root, baseline_sha)
    current = current_reachable_paths(documents, resolved_links, catalog)
    historical = _historical_prefixes(catalog)

    clusters = [
        *_title_clusters(documents),
        *similarity_clusters(documents),
        *_task_clusters(documents, known_tasks),
    ]
    for index, cluster in enumerate(clusters, start=1):
        cluster["cluster_id"] = f"DOC-CONFLICT-{index:04d}"
    cluster_by_path: dict[str, list[str]] = defaultdict(list)
    for cluster in clusters:
        for member in cluster["members"]:
            cluster_by_path[member].append(cluster["cluster_id"])

    rows: list[dict[str, Any]] = []
    for path, document in sorted(documents.items()):
        doc_type = candidate_type(path, document.title)
        audience = candidate_audience(path, doc_type)
        lifecycle = candidate_lifecycle(path, document, current, historical)
        findings: list[dict[str, str]] = []
        external_links: list[str] = []
        outbound_internal: list[str] = []

        for link in resolved_links[path]:
            if link["kind"] == "internal" and link["target"]:
                outbound_internal.append(str(link["target"]))
            elif link["kind"] == "external":
                external_links.append(str(link["raw"]))
            elif link["kind"] == "internal_directory":
                findings.append(
                    _finding(
                        "directory_navigation_target",
                        "info",
                        f"{link['raw']} -> {link['target']}",
                    )
                )
            elif link["kind"] == "missing":
                findings.append(
                    _finding(
                        "broken_internal_link",
                        "error",
                        f"{link['raw']} -> {link['target']}",
                    )
                )
            elif link["kind"] == "outside_repo":
                findings.append(
                    _finding("link_outside_repository", "error", str(link["raw"]))
                )
            elif link["kind"] == "repo_absolute_or_external":
                findings.append(
                    _finding(
                        "ambiguous_root_absolute_link",
                        "warning",
                        str(link["raw"]),
                    )
                )

        source_text = "\n".join((*document.first_lines, *document.code_blocks))
        for local_path in _local_path_findings(source_text):
            findings.append(_finding("hard_coded_local_path", "error", local_path))

        if path not in current and lifecycle in {"current", "unclassified"}:
            findings.append(
                _finding(
                    "current_looking_orphan",
                    "warning",
                    "not reachable from the governed current entrypoints",
                )
            )
        if path in current and _is_under(path, historical):
            findings.append(
                _finding(
                    "historical_page_in_current_graph",
                    "error",
                    "historical/archive path entered the current graph",
                )
            )

        heading_text = " ".join(document.headings).lower()
        if doc_type == "tutorial" and any(
            word in heading_text for word in ("reference", "schema", "api operations")
        ):
            findings.append(
                _finding(
                    "mixed_document_responsibility",
                    "warning",
                    "tutorial contains strong reference-section signals",
                )
            )

        for link in resolved_links[path]:
            target = link["target"]
            if (
                path in current
                and link["kind"] == "internal"
                and isinstance(target, str)
                and _is_under(target, historical)
            ):
                findings.append(
                    _finding(
                        "current_links_historical",
                        "warning",
                        f"current page links historical authority candidate {target}",
                    )
                )

        conflict_ids = sorted(cluster_by_path[path])
        row = {
            "path": path,
            "title": document.title,
            "sha256": document.sha256,
            "current_navigation_reachable": path in current,
            "inbound_internal_links": sorted(inbound[path]),
            "outbound_internal_links": sorted(set(outbound_internal)),
            "external_links": sorted(set(external_links)),
            "primary_audience": audience,
            "secondary_audiences": [],
            "document_type": doc_type,
            "lifecycle_assessment": lifecycle,
            "canonical_source_candidates": canonical_source_candidates(document),
            "owner_area": candidate_owner_area(path, path in current),
            "verification_class": candidate_verification_class(
                document,
                doc_type,
                path in current,
            ),
            "verifier_candidates": verifier_candidates(document, known_tasks),
            "conflict_cluster_ids": conflict_ids,
            "observed_findings": sorted(
                findings,
                key=lambda item: (item["severity"], item["code"], item["detail"]),
            ),
            "recommended_disposition": _disposition(
                lifecycle,
                path in current,
                findings,
                conflict_ids,
            ),
            "review_status": "machine_only",
        }
        rows.append(row)

    summary = {
        "tracked_markdown_count": len(rows),
        "current_navigation_reachable_count": sum(
            1 for row in rows if row["current_navigation_reachable"]
        ),
        "orphan_count": sum(
            1
            for row in rows
            if any(
                item["code"] == "current_looking_orphan"
                for item in row["observed_findings"]
            )
        ),
        "broken_internal_link_count": sum(
            1
            for row in rows
            for item in row["observed_findings"]
            if item["code"] == "broken_internal_link"
        ),
        "hard_coded_local_path_count": sum(
            1
            for row in rows
            for item in row["observed_findings"]
            if item["code"] == "hard_coded_local_path"
        ),
        "by_audience": dict(sorted(Counter(row["primary_audience"] for row in rows).items())),
        "by_type": dict(sorted(Counter(row["document_type"] for row in rows).items())),
        "by_lifecycle": dict(
            sorted(Counter(row["lifecycle_assessment"] for row in rows).items())
        ),
        "by_disposition": dict(
            sorted(Counter(row["recommended_disposition"] for row in rows).items())
        ),
        "by_owner_area": dict(sorted(Counter(row["owner_area"] for row in rows).items())),
        "by_verification_class": dict(
            sorted(Counter(row["verification_class"] for row in rows).items())
        ),
        "conflict_cluster_count": len(clusters),
        "manual_review_required_count": len(rows),
    }

    inventory = {
        "schema": SCHEMA_ID,
        "tool": {
            "name": "audit_documentation_inventory.py",
            "version": TOOL_VERSION,
            "markdown_parser": "markdown-it-py==4.0.0 + mdit-py-plugins==0.5.0",
        },
        "baseline_sha": baseline_sha,
        "scan_roots": ["Git tracked tree"],
        "exclusions": [
            "untracked files",
            "ignored runtime artifacts",
            "non-Markdown repository files",
        ],
        "known_limitations": [
            "audience, type, lifecycle, canonical source, conflict, and disposition "
            "are machine candidates until human review",
            "external URLs are recorded but not network-validated in DOCS-BOOT-00",
            "content-similarity clusters are discovery hints, not duplicate authority",
            "Git history timestamps are intentionally not used for lifecycle classification",
        ],
        "summary": summary,
        "documents": rows,
        "conflict_clusters": clusters,
    }
    errors = sorted(Draft202012Validator(inventory_schema()).iter_errors(inventory), key=str)
    if errors:
        details = "\n".join(f"- {error.json_path}: {error.message}" for error in errors)
        raise ValueError(f"inventory schema validation failed:\n{details}")
    if len({row["path"] for row in rows}) != len(paths):
        raise ValueError("each tracked Markdown path must appear exactly once")
    return inventory


def _markdown_table(counter: dict[str, int]) -> list[str]:
    lines = ["| Value | Count |", "| --- | ---: |"]
    lines.extend(f"| `{key}` | {value} |" for key, value in counter.items())
    return lines


def render_machine_report(inventory: dict[str, Any]) -> str:
    summary = inventory["summary"]
    lines = [
        "# Documentation Inventory — Machine Pass",
        "",
        f"- Baseline: `{inventory['baseline_sha']}`",
        f"- Tool: `{inventory['tool']['version']}`",
        f"- Tracked Markdown: **{summary['tracked_markdown_count']}**",
        f"- Current-navigation reachable: **{summary['current_navigation_reachable_count']}**",
        f"- Broken internal link findings: **{summary['broken_internal_link_count']}**",
        f"- Hard-coded local path findings: **{summary['hard_coded_local_path_count']}**",
        f"- Conflict/duplicate candidate clusters: **{summary['conflict_cluster_count']}**",
        "",
        "> This is a machine discovery pass. It is not the reviewed lifecycle or "
        "disposition authority required to close Issue #450.",
        "",
        "## Candidate lifecycle",
        "",
        *_markdown_table(summary["by_lifecycle"]),
        "",
        "## Candidate type",
        "",
        *_markdown_table(summary["by_type"]),
        "",
        "## Candidate audience",
        "",
        *_markdown_table(summary["by_audience"]),
        "",
        "## Current-entry error findings",
        "",
    ]
    current_errors = [
        (row["path"], finding)
        for row in inventory["documents"]
        if row["current_navigation_reachable"]
        for finding in row["observed_findings"]
        if finding["severity"] == "error"
    ]
    if current_errors:
        lines.extend(
            f"- `{path}` — `{finding['code']}`: {finding['detail']}"
            for path, finding in current_errors
        )
    else:
        lines.append("- None detected by the machine pass.")
    lines.extend(
        (
            "",
            "## Manual review queue",
            "",
            "Review every current-navigation page, every current-looking orphan, every "
            "conflict cluster, and representative historical/archive families against "
            "actual content. Record corrections and final migration ordering in the "
            "historical review report; do not mutate source documents in Issue #450.",
            "",
        )
    )
    return "\n".join(lines)


def write_outputs(output_dir: Path, inventory: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "documentation-inventory.json").write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "documentation-inventory.schema.json").write_text(
        json.dumps(inventory_schema(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "documentation-link-graph.json").write_text(
        json.dumps(
            {
                "schema": "finharness.documentation_link_graph.v1",
                "baseline_sha": inventory["baseline_sha"],
                "nodes": [
                    {
                        "path": row["path"],
                        "current": row["current_navigation_reachable"],
                        "lifecycle_candidate": row["lifecycle_assessment"],
                    }
                    for row in inventory["documents"]
                ],
                "edges": [
                    {"source": row["path"], "target": target}
                    for row in inventory["documents"]
                    for target in row["outbound_internal_links"]
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "documentation-conflict-clusters.json").write_text(
        json.dumps(
            {
                "schema": "finharness.documentation_conflict_clusters.v1",
                "baseline_sha": inventory["baseline_sha"],
                "clusters": inventory["conflict_clusters"],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "documentation-machine-report.md").write_text(
        render_machine_report(inventory),
        encoding="utf-8",
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def self_test() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _run_git(root, "init")
        _run_git(root, "config", "user.email", "docs-inventory@example.invalid")
        _run_git(root, "config", "user.name", "Documentation Inventory Test")
        (root / "docs" / "architecture").mkdir(parents=True)
        (root / "docs" / "archive").mkdir(parents=True)
        (root / "docs" / "reviews").mkdir(parents=True)
        (root / "docs" / "architecture" / "system-catalog.yml").write_text(
            yaml.safe_dump(
                {
                    "documentation": {
                        "navigation": {
                            "entrypoints": ["README.md"],
                            "historical_roots": ["docs/archive"],
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        (root / "Taskfile.yml").write_text(
            yaml.safe_dump({"tasks": {"check": {"cmds": ["echo ok"]}}}),
            encoding="utf-8",
        )
        (root / "README.md").write_text(
            "# Current Entry\n\n[Guide](docs/guide.md)\n",
            encoding="utf-8",
        )
        (root / "docs" / "guide.md").write_text(
            "# Shared Meaning\n\nStatus: accepted\n\n"
            "Historical summaries are reference only.\n\n"
            "Run `/root/projects/example` and `task check`.\n"
            "[Missing](missing.md)\n",
            encoding="utf-8",
        )
        (root / "docs" / "archive" / "old.md").write_text(
            "# Current-Looking Archived Page\n\n[Only historical](../reviews/only.md)\n",
            encoding="utf-8",
        )
        (root / "docs" / "reviews" / "only.md").write_text(
            "# Shared Meaning\n\nHistorical evidence.\n",
            encoding="utf-8",
        )
        (root / "docs" / "orphan.md").write_text(
            "# Orphan\n\nThis file has an old date but no current route.\n",
            encoding="utf-8",
        )
        (root / "config.yml").write_text("enabled: true\n", encoding="utf-8")
        (root / "docs" / "guide.md").write_text(
            (root / "docs" / "guide.md").read_text(encoding="utf-8")
            + "[Tracked config](../config.yml)\n",
            encoding="utf-8",
        )
        _run_git(root, "add", ".")
        _run_git(root, "commit", "-m", "fixture")
        inventory = build_inventory(root, "HEAD")

        _require(
            inventory["summary"]["tracked_markdown_count"] == 5,
            "tracked Markdown count did not match the fixture",
        )
        rows = {row["path"]: row for row in inventory["documents"]}
        _require(
            rows["README.md"]["current_navigation_reachable"] is True,
            "root entrypoint was not reachable",
        )
        _require(
            rows["docs/guide.md"]["current_navigation_reachable"] is True,
            "linked guide was not reachable",
        )
        _require(
            rows["docs/guide.md"]["lifecycle_assessment"] == "current",
            "accepted status or historical prose caused a false lifecycle downgrade",
        )
        _require(
            rows["docs/archive/old.md"]["lifecycle_assessment"] == "historical",
            "archive path was promoted by current-looking prose",
        )
        _require(
            rows["docs/reviews/only.md"]["current_navigation_reachable"] is False,
            "historical-only link incorrectly entered the current graph",
        )
        _require(
            rows["docs/orphan.md"]["current_navigation_reachable"] is False,
            "orphan page incorrectly entered the current graph",
        )
        _require(
            any(
                item["code"] == "broken_internal_link"
                for item in rows["docs/guide.md"]["observed_findings"]
            ),
            "broken internal link was not detected",
        )
        _require(
            any(
                item["code"] == "hard_coded_local_path"
                for item in rows["docs/guide.md"]["observed_findings"]
            ),
            "hard-coded local path was not detected",
        )
        _require(
            not any(
                item["code"] == "broken_internal_link"
                and "config.yml" in item["detail"]
                for item in rows["docs/guide.md"]["observed_findings"]
            ),
            "tracked non-Markdown target was reported missing",
        )
        _require(
            any(
                cluster["kind"] == "duplicate_title"
                for cluster in inventory["conflict_clusters"]
            ),
            "duplicate-title cluster was not detected",
        )
        _require(
            all(row["review_status"] == "machine_only" for row in rows.values()),
            "machine pass incorrectly claimed human review",
        )
        print("OK: documentation inventory adversarial self-test")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", default="HEAD")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".artifacts/documentation-inventory"),
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    root = Path.cwd()
    inventory = build_inventory(root, args.baseline)
    write_outputs(args.output_dir, inventory)
    print(
        "OK: "
        f"{inventory['summary']['tracked_markdown_count']} tracked Markdown files "
        f"at {inventory['baseline_sha']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
