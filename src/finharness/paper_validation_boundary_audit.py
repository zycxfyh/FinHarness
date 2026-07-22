"""Direct transitive-import audit for the deprecated PaperValidation surface."""

from __future__ import annotations

import ast
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

# ── AST import graph for transitive boundary analysis ─────────────────────────


@dataclass(frozen=True)
class ImportEdge:
    """A single import edge in the internal dependency graph."""

    source_module: str
    target_module: str
    source_path: str
    lineno: int


@dataclass(frozen=True)
class BoundaryFinding:
    """A finding from the transitive import boundary audit."""

    code: str
    source_module: str
    target_module: str
    path: tuple[str, ...]


@dataclass
class ImportGraph:
    """Import graph with canonical module names and external leaf nodes."""

    nodes: set[str] = field(default_factory=set)
    edges: list[ImportEdge] = field(default_factory=list)
    _adjacency: dict[str, set[str]] = field(default_factory=dict, repr=False)

    def add_edge(self, edge: ImportEdge) -> None:
        self.nodes.add(edge.source_module)
        self.nodes.add(edge.target_module)
        self.edges.append(edge)
        self._adjacency.setdefault(edge.source_module, set()).add(edge.target_module)

    def successors(self, module: str) -> set[str]:
        return self._adjacency.get(module, set())


def _module_name(root: Path, file_path: Path) -> str:
    relative = file_path.relative_to(root)
    if relative.parts[0] == "src":
        relative = Path(*relative.parts[1:])
    relative = relative.parent if file_path.name == "__init__.py" else relative.with_suffix("")
    return ".".join(relative.parts)


def _resolve_import_from(
    *,
    source_module: str,
    source_is_package: bool,
    module: str | None,
    level: int,
) -> str:
    if level == 0:
        return module or ""
    package_parts = source_module.split(".")
    if not source_is_package:
        package_parts = package_parts[:-1]
    parent_hops = level - 1
    if parent_hops > len(package_parts):
        return ""
    base = package_parts[: len(package_parts) - parent_hops]
    if module:
        base.extend(module.split("."))
    return ".".join(base)


def _extract_imports(
    file_path: Path,
    *,
    source_module: str,
    internal_modules: set[str],
) -> list[tuple[str, int]]:
    """Extract canonical import targets, including external leaf modules."""
    imports: list[tuple[str, int]] = []
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError):
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            target = _resolve_import_from(
                source_module=source_module,
                source_is_package=file_path.name == "__init__.py",
                module=node.module,
                level=node.level,
            )
            if not target:
                continue
            imports.append((target, node.lineno))
            for alias in node.names:
                submodule = f"{target}.{alias.name}"
                if submodule in internal_modules:
                    imports.append((submodule, node.lineno))
    return imports


def build_internal_import_graph(root: Path) -> ImportGraph:
    """Build a graph for project modules plus every directly imported leaf.

    Source files use importable names such as ``finharness.api.app`` rather than
    filesystem names such as ``src.finharness.api.app``. Third-party and stdlib
    imports remain leaf nodes so network-capable imports can be prohibited.
    """
    graph = ImportGraph()
    scan_dirs = ["src", "tests", "scripts"]

    # Collect all internal module paths
    internal_modules: dict[str, Path] = {}
    for dir_name in scan_dirs:
        scan_root = root / dir_name
        if not scan_root.is_dir():
            continue
        for py_file in scan_root.rglob("*.py"):
            if "archive" in py_file.parts:
                continue
            internal_modules[_module_name(root, py_file)] = py_file

    graph.nodes.update(internal_modules)

    # Build edges by parsing all files
    for py_file in internal_modules.values():
        rel = py_file.relative_to(root).as_posix()
        source_mod = _module_name(root, py_file)
        module_parts = source_mod.split(".")
        for length in range(1, len(module_parts)):
            package_module = ".".join(module_parts[:length])
            if package_module in internal_modules:
                graph.add_edge(
                    ImportEdge(
                        source_module=source_mod,
                        target_module=package_module,
                        source_path=rel,
                        lineno=0,
                    )
                )
        for target_mod, lineno in _extract_imports(
            py_file,
            source_module=source_mod,
            internal_modules=set(internal_modules),
        ):
            graph.add_edge(
                ImportEdge(
                    source_module=source_mod,
                    target_module=target_mod,
                    source_path=rel,
                    lineno=lineno,
                )
            )

    return graph


def find_unapproved_incoming_imports(
    graph: ImportGraph,
    *,
    protected_modules: set[str],
    approved_sources: set[str],
    source_prefix: str = "finharness",
) -> list[BoundaryFinding]:
    """Find new production modules importing compatibility-only modules.

    Tests and scripts may inspect the legacy surface. Current production callers
    must be named explicitly so a new FinHarness module cannot silently make the
    compatibility runtime a current dependency again.
    """
    findings: list[BoundaryFinding] = []
    for edge in graph.edges:
        if edge.target_module not in protected_modules:
            continue
        if edge.source_module in protected_modules or edge.source_module in approved_sources:
            continue
        if edge.source_module != source_prefix and not edge.source_module.startswith(
            source_prefix + "."
        ):
            continue
        findings.append(
            BoundaryFinding(
                code="unapproved_incoming_import",
                source_module=edge.source_module,
                target_module=edge.target_module,
                path=(edge.source_module, edge.target_module),
            )
        )
    return sorted(
        findings,
        key=lambda finding: (finding.source_module, finding.target_module),
    )


def find_forbidden_transitive_imports(
    graph: ImportGraph,
    *,
    roots: set[str],
    forbidden_prefixes: set[str],
) -> list[BoundaryFinding]:
    """Find all transitive import paths from roots to forbidden modules.

    Uses BFS from each root. Returns a BoundaryFinding for each
    unique (source, target) pair, with the shortest path found.
    """
    findings: list[BoundaryFinding] = []

    for root_module in sorted(roots):
        if root_module not in graph.nodes:
            findings.append(
                BoundaryFinding(
                    code="missing_boundary_root",
                    source_module=root_module,
                    target_module=root_module,
                    path=(root_module,),
                )
            )
            continue
        # BFS from this root
        visited: dict[str, tuple[str, ...]] = {root_module: (root_module,)}
        queue: deque[str] = deque([root_module])

        while queue:
            current = queue.popleft()
            current_path = visited[current]

            for successor in graph.successors(current):
                if successor in visited:
                    continue
                new_path = (*current_path, successor)
                visited[successor] = new_path

                # Check if successor is forbidden
                if any(
                    successor == fp or successor.startswith(fp + ".") for fp in forbidden_prefixes
                ):
                    findings.append(
                        BoundaryFinding(
                            code="forbidden_transitive_import",
                            source_module=root_module,
                            target_module=successor,
                            path=new_path,
                        )
                    )
                    continue  # Don't traverse further from forbidden targets

                if successor in graph._adjacency:
                    queue.append(successor)

    return findings
