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
"""Create exact-SHA documentation inventory evidence for Issue #450.

The output is an audit artifact, not a permanent documentation registry.
Machine classifications remain candidates until reviewed in the historical
report under ``docs/reviews/documentation``.
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

SCHEMA = "finharness.documentation_inventory.v1"
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

TASK_RE = re.compile(r"\btask\s+([A-Za-z0-9:_-]+)")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
DECLARED_LIFECYCLE_RE = re.compile(
    r"(?mi)^\s*(?:>\s*)?(?:[-*]\s*)?(?:status|lifecycle)\s*:\s*"
    r"(current|preview|deprecated|superseded|historical|archived)\b"
)
LIFECYCLE_BANNER_RE = re.compile(
    r"(?mi)^\s*>\s*(historical|archived|superseded|deprecated)\b"
)
LOCAL_PATH_PATTERNS = (
    re.compile(r"(?<![\w.-])/root/(?:[\w./-]+)"),
    re.compile(r"(?<![\w.-])/home/[^/\s]+/(?:[\w./-]+)"),
    re.compile(r"\b[A-Za-z]:\\(?:[^\\\s]+\\)*[^\\\s]*"),
    re.compile(r"\bfile://[^\s)>]+"),
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
class Document:
    path: str
    title: str
    headings: tuple[str, ...]
    links: tuple[str, ...]
    code_blocks: tuple[str, ...]
    frontmatter: dict[str, Any]
    raw_text: str
    first_lines: tuple[str, ...]
    sha256: str


class HTMLLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "a" and values.get("href"):
            self.links.append(str(values["href"]))


def git(root: Path, *args: str, text: bool = True) -> subprocess.CompletedProcess[Any]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=text,
    )


def commit_sha(root: Path, baseline: str) -> str:
    return git(root, "rev-parse", f"{baseline}^{{commit}}").stdout.strip()


def tracked_paths(root: Path, baseline: str) -> tuple[str, ...]:
    raw = git(root, "ls-tree", "-r", "--name-only", "-z", baseline, text=False).stdout
    if not isinstance(raw, bytes):
        raise TypeError("git ls-tree must return bytes")
    return tuple(
        sorted(item.decode("utf-8") for item in raw.split(b"\0") if item)
    )


def git_text(root: Path, baseline: str, path: str) -> str:
    raw = git(root, "show", f"{baseline}:{path}", text=False).stdout
    if not isinstance(raw, bytes):
        raise TypeError("git show must return bytes")
    return raw.decode("utf-8", errors="replace")


def markdown_parser() -> MarkdownIt:
    parser = MarkdownIt("commonmark", {"html": True})
    parser.enable("table")
    parser.enable("strikethrough")
    parser.use(front_matter_plugin)
    return parser


def parse_frontmatter(content: str) -> dict[str, Any]:
    try:
        value = yaml.safe_load(content) or {}
    except yaml.YAMLError:
        return {"_parse_error": True}
    return value if isinstance(value, dict) else {"_non_mapping": value}


def parse_document(path: str, text: str) -> Document:
    headings: list[str] = []
    links: list[str] = []
    code_blocks: list[str] = []
    frontmatter: dict[str, Any] = {}
    pending_heading = False
    html_links = HTMLLinks()

    for token in markdown_parser().parse(text):
        if token.type == "front_matter":
            frontmatter = parse_frontmatter(token.content)
        elif token.type == "heading_open":
            pending_heading = True
        elif token.type == "inline":
            if pending_heading:
                headings.append(token.content.strip())
                pending_heading = False
            for child in token.children or ():
                if child.type == "link_open" and child.attrGet("href"):
                    links.append(str(child.attrGet("href")))
                elif child.type in {"html_inline", "html_block"}:
                    html_links.feed(child.content)
        elif token.type in {"html_inline", "html_block"}:
            html_links.feed(token.content)
        elif token.type in {"fence", "code_block"}:
            code_blocks.append(token.content)

    links.extend(html_links.links)
    title = next((value for value in headings if value), PurePosixPath(path).stem)
    return Document(
        path=path,
        title=title,
        headings=tuple(headings),
        links=tuple(dict.fromkeys(links)),
        code_blocks=tuple(code_blocks),
        frontmatter=frontmatter,
        raw_text=text,
        first_lines=tuple(text.splitlines()[:40]),
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


def collapse_path(path: PurePosixPath) -> str | None:
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


def resolve_link(source: str, raw: str, tracked: set[str]) -> tuple[str, str | None]:
    target = raw.strip()
    if not target:
        return "empty", None
    parsed = urlsplit(target)
    if parsed.scheme.lower() in EXTERNAL_SCHEMES or parsed.netloc:
        return "external", None
    if target.startswith("#") or not parsed.path:
        return "anchor", source
    clean = unquote(parsed.path).strip()
    if clean.startswith("/"):
        return "root_absolute", clean
    collapsed = collapse_path(PurePosixPath(source).parent / clean)
    if collapsed is None:
        return "outside_repo", clean

    candidates = [collapsed]
    if not PurePosixPath(collapsed).suffix:
        candidates.extend((f"{collapsed}.md", f"{collapsed}/README.md"))
    for candidate in candidates:
        if candidate in tracked:
            return "internal", candidate
    prefix = f"{collapsed.rstrip('/')}/"
    if any(path.startswith(prefix) for path in tracked):
        return "directory", collapsed
    return "missing", collapsed


def load_yaml(root: Path, baseline: str, path: str) -> dict[str, Any]:
    try:
        value = yaml.safe_load(git_text(root, baseline, path)) or {}
    except subprocess.CalledProcessError:
        return {}
    return value if isinstance(value, dict) else {}


def historical_prefixes(catalog: dict[str, Any]) -> tuple[str, ...]:
    navigation = catalog.get("documentation", {}).get("navigation", {})
    values = [
        *navigation.get("historical_roots", []),
        *navigation.get("historical_paths", []),
        "docs/archive",
        "experiments/archive",
    ]
    return tuple(sorted({str(value).rstrip("/") for value in values if value}))


def under(path: str, prefixes: Iterable[str]) -> bool:
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in prefixes)


def current_graph(
    documents: dict[str, Document],
    links: dict[str, list[dict[str, Any]]],
    catalog: dict[str, Any],
) -> set[str]:
    navigation = catalog.get("documentation", {}).get("navigation", {})
    queue: deque[str] = deque(str(value) for value in navigation.get("entrypoints", ["README.md"]))
    historical = historical_prefixes(catalog)
    seen: set[str] = set()
    while queue:
        path = queue.popleft()
        if path in seen or path not in documents or under(path, historical):
            continue
        seen.add(path)
        queue.extend(
            str(item["target"])
            for item in links[path]
            if item["kind"] == "internal" and item["target"] in documents
        )
    return seen


def document_type(path: str, title: str) -> str:
    lower = path.lower()
    title_lower = title.lower()
    parent = PurePosixPath(path).parent.name
    if "/tutorial" in lower or "golden path" in title_lower:
        return "tutorial"
    if "/how-to/" in lower or title_lower.startswith("how to "):
        return "how_to"
    if "/operations/" in lower or "/playbooks/" in lower or "runbook" in title_lower:
        return "runbook"
    if parent == "adr":
        return "adr"
    if parent == "proposals" or lower.startswith("ideas/"):
        return "proposal"
    if parent == "reviews":
        return "review"
    if "/architecture/" in lower or "/modules/" in lower:
        return "architecture"
    if "/reference/" in lower or "/templates/" in lower or lower.startswith("data/"):
        return "reference"
    if any(
        marker in lower
        for marker in (
            "/engineering/",
            "/think/",
            "/lessons/",
            "/product/",
            "/security/",
            "/research/",
            "experiments/",
        )
    ):
        return "explanation"
    return "other"


def audience(path: str, kind: str) -> str:
    lower = path.lower()
    if path in {"README.md", "docs/README.md"} or kind == "tutorial":
        return "user"
    if path in {"AGENTS.md", "CONTRIBUTING.md", "CONTEXT.md"}:
        return "developer"
    if any(marker in lower for marker in ("/security/", "/audits/", "/governance/")):
        return "auditor"
    if kind == "runbook" or "/reference/" in lower:
        return "operator"
    if kind == "how_to":
        return "developer" if "issue-worktree" in lower or "mature-wheel" in lower else "user"
    if lower.startswith((".github/", "ideas/")):
        return "maintainer"
    if lower.startswith("data/"):
        return "operator"
    if lower.startswith("experiments/"):
        return "developer"
    return "maintainer"


def declared_lifecycle(document: Document) -> str | None:
    for key in ("lifecycle", "status"):
        value = document.frontmatter.get(key)
        if isinstance(value, str) and value.lower() in LIFECYCLES:
            return value.lower()
    header = "\n".join(document.first_lines)
    match = DECLARED_LIFECYCLE_RE.search(header) or LIFECYCLE_BANNER_RE.search(header)
    return match.group(1).lower() if match else None


def lifecycle(path: str, document: Document, current: set[str], historical: tuple[str, ...]) -> str:
    declared = declared_lifecycle(document)
    if under(path, historical):
        return declared if declared in {"historical", "archived"} else "historical"
    if declared:
        return declared
    if path in current:
        return "current"
    if "/reviews/" in path.lower():
        return "historical"
    if "/proposals/" in path.lower():
        return "preview"
    return "unclassified"


def owner_area(path: str, current: bool) -> str:
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
    if any(marker in lower for marker in ("/architecture/", "/adr/", "/modules/")):
        return "architecture"
    if "/engineering/" in lower or path in {"AGENTS.md", "CONTRIBUTING.md", "CONTEXT.md"}:
        return "engineering"
    if any(marker in lower for marker in ("/operations/", "/playbooks/")):
        return "operations"
    if "/security/" in lower:
        return "security"
    if any(marker in lower for marker in ("/governance/", "/audits/")):
        return "governance"
    if "/research/" in lower:
        return "research"
    return "documentation" if current else "unclassified"


def verification_class(document: Document, kind: str, current: bool) -> str:
    text = document.raw_text
    if "Generated from `" in text and "Do not edit" in text:
        return "generated"
    if "schema" in text.lower() and any(name in text for name in ("Pydantic", "SQLModel", "OpenAPI")):
        return "schema_compared"
    if kind in {"tutorial", "how_to", "runbook"} and TASK_RE.search(text):
        return "executable"
    if "task docs:current-check" in text or "task governance:check" in text:
        return "static_fact_check"
    if kind in {"adr", "proposal", "review"}:
        return "review_only"
    return "link_graph" if current else "none"


def canonical_sources(document: Document) -> list[str]:
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
    candidates.extend(value for value in known if value.lower() in document.raw_text.lower())
    generated = re.search(r"Generated from `([^`]+)`", document.raw_text, re.IGNORECASE)
    if generated:
        candidates.insert(0, generated.group(1))
    return list(dict.fromkeys(candidates))


def verifier_candidates(document: Document, known_tasks: set[str]) -> list[str]:
    tasks = [
        f"task {name}"
        for name in TASK_RE.findall(document.raw_text)
        if name in known_tasks and "check" in name
    ]
    if "Generated from `" in document.raw_text and "Do not edit" in document.raw_text:
        tasks.append("generated-output drift check")
    return list(dict.fromkeys(tasks))


def local_paths(text: str) -> list[str]:
    return sorted(
        {
            match.group(0)
            for pattern in LOCAL_PATH_PATTERNS
            for match in pattern.finditer(text)
        }
    )


def tokens(text: str) -> set[str]:
    return {
        word.lower()
        for word in WORD_RE.findall(text)
        if word.lower() not in STOPWORDS and not word.isdigit()
    }


def duplicate_title_clusters(documents: dict[str, Document]) -> list[dict[str, Any]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for path, document in documents.items():
        title = re.sub(r"\W+", " ", document.title.lower()).strip()
        if title:
            grouped[title].append(path)
    return [
        {
            "kind": "duplicate_title",
            "members": sorted(paths),
            "reason": f"same normalized title: {title}",
        }
        for title, paths in sorted(grouped.items())
        if len(paths) > 1
    ]


def similar_content_clusters(documents: dict[str, Document]) -> list[dict[str, Any]]:
    token_map = {path: tokens(document.raw_text) for path, document in documents.items()}
    eligible = {path: values for path, values in token_map.items() if len(values) >= 60}
    pairs: list[dict[str, Any]] = []
    paths = sorted(eligible)
    for index, left in enumerate(paths):
        for right in paths[index + 1 :]:
            union = eligible[left] | eligible[right]
            score = len(eligible[left] & eligible[right]) / len(union)
            if score >= 0.72:
                pairs.append(
                    {
                        "kind": "content_similarity",
                        "members": [left, right],
                        "reason": f"token-set Jaccard similarity {score:.3f}; review required",
                    }
                )
    return pairs


def repeated_task_clusters(
    documents: dict[str, Document], known_tasks: set[str]
) -> list[dict[str, Any]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for path, document in documents.items():
        for name in TASK_RE.findall(document.raw_text):
            if name in known_tasks:
                grouped[name].add(path)
    return [
        {
            "kind": "repeated_task_claim",
            "members": sorted(paths),
            "reason": f"`task {name}` appears in {len(paths)} documents",
            "task": name,
        }
        for name, paths in sorted(grouped.items())
        if len(paths) >= 3
    ]


def clusters(documents: dict[str, Document], known_tasks: set[str]) -> list[dict[str, Any]]:
    values = [
        *duplicate_title_clusters(documents),
        *similar_content_clusters(documents),
        *repeated_task_clusters(documents, known_tasks),
    ]
    for index, value in enumerate(values, start=1):
        value["cluster_id"] = f"DOC-CONFLICT-{index:04d}"
    return values


def finding(code: str, severity: str, detail: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "detail": detail}


def link_findings(entries: list[dict[str, Any]]) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for entry in entries:
        if entry["kind"] == "missing":
            results.append(finding("broken_internal_link", "error", f"{entry['raw']} -> {entry['target']}"))
        elif entry["kind"] == "outside_repo":
            results.append(finding("link_outside_repository", "error", str(entry["raw"])))
        elif entry["kind"] == "root_absolute":
            results.append(finding("ambiguous_root_absolute_link", "warning", str(entry["raw"])))
        elif entry["kind"] == "directory":
            results.append(finding("directory_navigation_target", "info", str(entry["raw"])))
    return results


def document_findings(
    path: str,
    document: Document,
    entries: list[dict[str, Any]],
    current: set[str],
    historical: tuple[str, ...],
) -> list[dict[str, str]]:
    results = link_findings(entries)
    results.extend(finding("hard_coded_local_path", "error", value) for value in local_paths(document.raw_text))
    state = lifecycle(path, document, current, historical)
    if path not in current and state in {"current", "unclassified"}:
        results.append(
            finding("current_looking_orphan", "warning", "not reachable from current entrypoints")
        )
    if path in current and state in {"historical", "archived", "superseded"}:
        results.append(
            finding("noncurrent_page_in_current_graph", "error", f"lifecycle candidate is {state}")
        )
    for entry in entries:
        target = entry["target"]
        if path in current and entry["kind"] == "internal" and isinstance(target, str) and under(target, historical):
            results.append(
                finding("current_links_historical", "warning", f"current page links {target}")
            )
    return sorted(results, key=lambda item: (item["severity"], item["code"], item["detail"]))


def disposition(
    state: str,
    current: bool,
    findings: list[dict[str, str]],
    cluster_ids: list[str],
) -> str:
    if current and any(item["severity"] == "error" for item in findings):
        return "correct"
    if cluster_ids:
        return "owner_decision_required"
    if state in {"historical", "archived"} or current:
        return "keep"
    return "owner_decision_required"


def string_array() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}, "uniqueItems": True}


def inventory_schema() -> dict[str, Any]:
    finding_shape = {
        "type": "object",
        "additionalProperties": False,
        "required": ["code", "severity", "detail"],
        "properties": {
            "code": {"type": "string"},
            "severity": {"enum": ["info", "warning", "error"]},
            "detail": {"type": "string"},
        },
    }
    document_properties: dict[str, Any] = {
        "path": {"type": "string"},
        "title": {"type": "string"},
        "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "current_navigation_reachable": {"type": "boolean"},
        "inbound_internal_links": string_array(),
        "outbound_internal_links": string_array(),
        "external_links": string_array(),
        "primary_audience": {"enum": list(AUDIENCES)},
        "secondary_audiences": string_array(),
        "document_type": {"enum": list(DOC_TYPES)},
        "lifecycle_assessment": {"enum": list(LIFECYCLES)},
        "canonical_source_candidates": string_array(),
        "owner_area": {"enum": list(OWNER_AREAS)},
        "verification_class": {"enum": list(VERIFICATION_CLASSES)},
        "verifier_candidates": string_array(),
        "conflict_cluster_ids": string_array(),
        "observed_findings": {"type": "array", "items": finding_shape},
        "recommended_disposition": {"enum": list(DISPOSITIONS)},
        "review_status": {"enum": ["machine_only", "manually_reviewed"]},
    }
    document_shape = {
        "type": "object",
        "additionalProperties": False,
        "required": list(document_properties),
        "properties": document_properties,
    }
    cluster_shape = {
        "type": "object",
        "additionalProperties": False,
        "required": ["cluster_id", "kind", "members", "reason"],
        "properties": {
            "cluster_id": {"type": "string"},
            "kind": {"enum": ["duplicate_title", "content_similarity", "repeated_task_claim"]},
            "members": string_array(),
            "reason": {"type": "string"},
            "task": {"type": "string"},
        },
    }
    top_properties: dict[str, Any] = {
        "schema": {"const": SCHEMA},
        "tool": {"type": "string"},
        "baseline_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
        "scan_roots": string_array(),
        "exclusions": string_array(),
        "known_limitations": string_array(),
        "summary": {"type": "object"},
        "documents": {"type": "array", "items": document_shape},
        "conflict_clusters": {"type": "array", "items": cluster_shape},
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA,
        "type": "object",
        "additionalProperties": False,
        "required": list(top_properties),
        "properties": top_properties,
    }


def build_inventory(root: Path, baseline: str) -> dict[str, Any]:
    exact_sha = commit_sha(root, baseline)
    all_paths = set(tracked_paths(root, exact_sha))
    markdown_paths = tuple(
        path
        for path in sorted(all_paths)
        if PurePosixPath(path).suffix.lower() in {".md", ".markdown"}
    )
    documents = {
        path: parse_document(path, git_text(root, exact_sha, path)) for path in markdown_paths
    }
    resolved = {
        path: [
            {"raw": raw, "kind": kind, "target": target}
            for raw in document.links
            for kind, target in [resolve_link(path, raw, all_paths)]
        ]
        for path, document in documents.items()
    }
    catalog = load_yaml(root, exact_sha, "docs/architecture/system-catalog.yml")
    taskfile = load_yaml(root, exact_sha, "Taskfile.yml")
    known_tasks = set(taskfile.get("tasks", {})) if isinstance(taskfile.get("tasks"), dict) else set()
    current = current_graph(documents, resolved, catalog)
    historical = historical_prefixes(catalog)
    conflict_clusters = clusters(documents, known_tasks)
    cluster_ids: dict[str, list[str]] = defaultdict(list)
    for cluster in conflict_clusters:
        for path in cluster["members"]:
            cluster_ids[path].append(cluster["cluster_id"])

    inbound: dict[str, set[str]] = defaultdict(set)
    for source, entries in resolved.items():
        for entry in entries:
            if entry["kind"] == "internal" and entry["target"] in documents:
                inbound[str(entry["target"])].add(source)

    rows: list[dict[str, Any]] = []
    for path, document in sorted(documents.items()):
        kind = document_type(path, document.title)
        state = lifecycle(path, document, current, historical)
        findings = document_findings(path, document, resolved[path], current, historical)
        internal = sorted(
            {
                str(entry["target"])
                for entry in resolved[path]
                if entry["kind"] == "internal" and entry["target"] in documents
            }
        )
        external = sorted(
            {str(entry["raw"]) for entry in resolved[path] if entry["kind"] == "external"}
        )
        ids = sorted(cluster_ids[path])
        rows.append(
            {
                "path": path,
                "title": document.title,
                "sha256": document.sha256,
                "current_navigation_reachable": path in current,
                "inbound_internal_links": sorted(inbound[path]),
                "outbound_internal_links": internal,
                "external_links": external,
                "primary_audience": audience(path, kind),
                "secondary_audiences": [],
                "document_type": kind,
                "lifecycle_assessment": state,
                "canonical_source_candidates": canonical_sources(document),
                "owner_area": owner_area(path, path in current),
                "verification_class": verification_class(document, kind, path in current),
                "verifier_candidates": verifier_candidates(document, known_tasks),
                "conflict_cluster_ids": ids,
                "observed_findings": findings,
                "recommended_disposition": disposition(state, path in current, findings, ids),
                "review_status": "machine_only",
            }
        )

    summary = {
        "tracked_markdown_count": len(rows),
        "current_navigation_reachable_count": sum(
            row["current_navigation_reachable"] for row in rows
        ),
        "current_error_document_count": sum(
            row["current_navigation_reachable"]
            and any(item["severity"] == "error" for item in row["observed_findings"])
            for row in rows
        ),
        "broken_internal_link_count": sum(
            item["code"] == "broken_internal_link"
            for row in rows
            for item in row["observed_findings"]
        ),
        "hard_coded_local_path_count": sum(
            item["code"] == "hard_coded_local_path"
            for row in rows
            for item in row["observed_findings"]
        ),
        "conflict_cluster_count": len(conflict_clusters),
        "by_audience": dict(sorted(Counter(row["primary_audience"] for row in rows).items())),
        "by_type": dict(sorted(Counter(row["document_type"] for row in rows).items())),
        "by_lifecycle": dict(
            sorted(Counter(row["lifecycle_assessment"] for row in rows).items())
        ),
        "by_owner_area": dict(sorted(Counter(row["owner_area"] for row in rows).items())),
        "by_verification_class": dict(
            sorted(Counter(row["verification_class"] for row in rows).items())
        ),
        "by_disposition": dict(
            sorted(Counter(row["recommended_disposition"] for row in rows).items())
        ),
        "manual_review_required_count": len(rows),
    }
    inventory = {
        "schema": SCHEMA,
        "tool": TOOL_VERSION,
        "baseline_sha": exact_sha,
        "scan_roots": ["Git tracked tree"],
        "exclusions": ["untracked files", "ignored runtime artifacts", "non-Markdown files"],
        "known_limitations": [
            "classification fields are candidates until the historical report records manual review",
            "external URLs are recorded but not network-validated in Issue #450",
            "similarity and repeated-task clusters are discovery hints, not authority",
            "Git timestamps are intentionally excluded from lifecycle classification",
        ],
        "summary": summary,
        "documents": rows,
        "conflict_clusters": conflict_clusters,
    }
    errors = sorted(Draft202012Validator(inventory_schema()).iter_errors(inventory), key=str)
    if errors:
        details = "\n".join(f"- {error.json_path}: {error.message}" for error in errors)
        raise ValueError(f"inventory schema validation failed:\n{details}")
    if len(rows) != len(markdown_paths) or len({row["path"] for row in rows}) != len(rows):
        raise ValueError("every tracked Markdown path must appear exactly once")
    return inventory


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def render_report(inventory: dict[str, Any]) -> str:
    summary = inventory["summary"]
    lines = [
        "# Documentation Inventory — Machine Pass",
        "",
        f"- Baseline: `{inventory['baseline_sha']}`",
        f"- Tool: `{inventory['tool']}`",
        f"- Tracked Markdown: **{summary['tracked_markdown_count']}**",
        f"- Current reachable: **{summary['current_navigation_reachable_count']}**",
        f"- Current pages with machine error findings: **{summary['current_error_document_count']}**",
        f"- Broken internal links: **{summary['broken_internal_link_count']}**",
        f"- Hard-coded local paths: **{summary['hard_coded_local_path_count']}**",
        f"- Conflict candidates: **{summary['conflict_cluster_count']}**",
        "",
        "> Machine discovery only. The historical report owns reviewed interpretation.",
        "",
        "## Current error candidates",
        "",
    ]
    errors = [
        (row["path"], item)
        for row in inventory["documents"]
        if row["current_navigation_reachable"]
        for item in row["observed_findings"]
        if item["severity"] == "error"
    ]
    lines.extend(
        f"- `{path}` — `{item['code']}`: {item['detail']}" for path, item in errors
    )
    if not errors:
        lines.append("- None detected.")
    return "\n".join(lines) + "\n"


def write_outputs(output_dir: Path, inventory: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "documentation-inventory.json", inventory)
    write_json(output_dir / "documentation-inventory.schema.json", inventory_schema())
    write_json(
        output_dir / "documentation-link-graph.json",
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
    )
    write_json(
        output_dir / "documentation-conflict-clusters.json",
        {
            "schema": "finharness.documentation_conflict_clusters.v1",
            "baseline_sha": inventory["baseline_sha"],
            "clusters": inventory["conflict_clusters"],
        },
    )
    (output_dir / "documentation-machine-report.md").write_text(
        render_report(inventory), encoding="utf-8"
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def self_test() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        git(root, "init")
        git(root, "config", "user.email", "docs@example.invalid")
        git(root, "config", "user.name", "Docs Inventory")
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
        (root / "config.yml").write_text("enabled: true\n", encoding="utf-8")
        (root / "README.md").write_text("# Entry\n\n[Guide](docs/guide.md)\n", encoding="utf-8")
        (root / "docs" / "guide.md").write_text(
            "# Shared\n\nStatus: accepted\n\nHistorical summaries exist.\n\n"
            "Use `/root/projects/example` and `task check`.\n\n"
            "[Config](../config.yml) [Missing](missing.md)\n",
            encoding="utf-8",
        )
        (root / "docs" / "archive" / "old.md").write_text(
            "# Current-looking old page\n\n[Review](../reviews/only.md)\n", encoding="utf-8"
        )
        (root / "docs" / "reviews" / "only.md").write_text(
            "# Shared\n\nHistorical evidence.\n", encoding="utf-8"
        )
        (root / "docs" / "orphan.md").write_text("# Orphan\n", encoding="utf-8")
        git(root, "add", ".")
        git(root, "commit", "-m", "fixture")
        inventory = build_inventory(root, "HEAD")
        rows = {row["path"]: row for row in inventory["documents"]}
        require(len(rows) == 5, "tracked Markdown census is incomplete")
        require(rows["docs/guide.md"]["current_navigation_reachable"], "guide not reachable")
        require(
            rows["docs/guide.md"]["lifecycle_assessment"] == "current",
            "ordinary historical prose changed lifecycle",
        )
        require(
            rows["docs/archive/old.md"]["lifecycle_assessment"] == "historical",
            "archive path was promoted",
        )
        guide_codes = {item["code"] for item in rows["docs/guide.md"]["observed_findings"]}
        require("broken_internal_link" in guide_codes, "missing link was not detected")
        require("hard_coded_local_path" in guide_codes, "local path was not detected")
        require(
            all("config.yml" not in item["detail"] for item in rows["docs/guide.md"]["observed_findings"]),
            "tracked non-Markdown target was reported missing",
        )
        require(
            any(cluster["kind"] == "duplicate_title" for cluster in inventory["conflict_clusters"]),
            "duplicate-title candidate was not detected",
        )
        require(
            all(row["review_status"] == "machine_only" for row in rows.values()),
            "machine pass claimed human review",
        )
    print("OK: documentation inventory adversarial self-test")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", default="HEAD")
    parser.add_argument(
        "--output-dir", type=Path, default=Path(".artifacts/documentation-inventory")
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    inventory = build_inventory(Path.cwd(), args.baseline)
    write_outputs(args.output_dir, inventory)
    print(
        f"OK: {inventory['summary']['tracked_markdown_count']} tracked Markdown files "
        f"at {inventory['baseline_sha']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
