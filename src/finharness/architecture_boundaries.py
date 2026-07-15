"""Repository-wide Python import cycle and architecture-boundary proof."""

from __future__ import annotations

import ast
import fnmatch
import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from finharness.project_paths import ROOT

DEFAULT_MATRIX_PATH = ROOT / "config" / "architecture-layers.yml"
PLANE_MODEL_SCHEMA = "finharness.plane_model.v1"
IDENTITY_MODEL_SCHEMA = "finharness.identity_version_graph.v1"
REQUIRED_IDENTITY_NAMESPACES = frozenset(
    {
        "principal",
        "agent-runtime",
        "request",
        "external-source",
        "domain-logical",
        "domain-version",
        "git-commit",
    }
)
REQUIRED_VERSION_NODES = frozenset(
    {
        "CapitalStateVersion",
        "EvidenceSetVersion",
        "PolicyVersion",
        "ProposalVersion",
        "DecisionCaseVersion",
        "ScenarioVersion",
        "ReviewStateVersion",
        "DecisionRecord",
    }
)
REQUIRED_SUBSTITUTION_BARRIERS = {
    "agent-runtime": frozenset({"principal"}),
    "request": frozenset(
        {"principal", "external-source", "domain-logical", "domain-version"}
    ),
    "display_id": frozenset(
        {"principal", "external-source", "domain-logical", "domain-version"}
    ),
    "local_alias": frozenset(
        {"external-source", "domain-logical", "domain-version"}
    ),
    "path": frozenset({"external-source"}),
    "content_digest": frozenset({"domain-version"}),
    "git-commit": frozenset(
        {"principal", "external-source", "domain-logical", "domain-version"}
    ),
}
EXPECTED_FRESHNESS_OWNERS = {
    "capital_state_admission": "truth",
    "evidence_admission_or_withdrawal": "knowledge",
    "policy_activation": "control",
    "proposal_revision": "judgment",
    "case_basis_change": "judgment",
    "scenario_recalculation": "judgment",
    "review_event": "judgment",
    "decision_recorded": "judgment",
}


@dataclass(frozen=True)
class ImportEdge:
    source: str
    target: str
    source_path: str
    line: int
    statement: str


@dataclass(frozen=True)
class BoundaryViolation:
    rule_id: str
    kind: str
    source_layer: str
    target_layer: str
    path: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "kind": self.kind,
            "source_layer": self.source_layer,
            "target_layer": self.target_layer,
            "path": list(self.path),
        }


def _module_for_file(path: Path, *, root: Path, source_roots: tuple[str, ...]) -> str:
    relative = path.relative_to(root)
    for source_root in source_roots:
        prefix = Path(source_root)
        try:
            under = relative.relative_to(prefix)
        except ValueError:
            continue
        module_path = under if source_root == "src" else relative
        parts = list(module_path.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts.pop()
        return ".".join(parts)
    raise ValueError(f"{path} is not under a configured source root")


def discover_modules(
    root: Path,
    source_roots: tuple[str, ...],
) -> dict[str, Path]:
    modules: dict[str, Path] = {}
    for source_root in source_roots:
        base = root / source_root
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            if any(part in {".venv", "__pycache__", "node_modules"} for part in path.parts):
                continue
            module = _module_for_file(path, root=root, source_roots=source_roots)
            if module:
                modules[module] = path
    return modules


def _package_for(module: str, path: Path) -> str:
    return module if path.name == "__init__.py" else module.rpartition(".")[0]


def _resolve_from_import(
    node: ast.ImportFrom,
    *,
    module: str,
    path: Path,
    known: set[str],
) -> set[str]:
    if node.level:
        package = _package_for(module, path)
        parts = package.split(".") if package else []
        trim = node.level - 1
        if trim > len(parts):
            return set()
        anchor = parts[: len(parts) - trim] if trim else parts
        if node.module:
            anchor.extend(node.module.split("."))
        base = ".".join(anchor)
    else:
        base = node.module or ""

    targets: set[str] = set()
    resolved_alias = False
    for alias in node.names:
        if alias.name == "*":
            continue
        candidate = f"{base}.{alias.name}" if base else alias.name
        if candidate in known:
            targets.add(candidate)
            resolved_alias = True
    if base in known and not resolved_alias:
        targets.add(base)
    return targets


def build_canonical_import_graph(
    root: Path,
    source_roots: tuple[str, ...],
) -> tuple[dict[str, Path], tuple[ImportEdge, ...]]:
    modules = discover_modules(root, source_roots)
    known = set(modules)
    edges: set[ImportEdge] = set()
    for module, path in modules.items():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError) as exc:
            raise ValueError(f"cannot parse architecture source {path}: {exc}") from exc
        for node in ast.walk(tree):
            targets: set[str] = set()
            statement = ""
            if isinstance(node, ast.Import):
                statement = ast.unparse(node)
                for alias in node.names:
                    parts = alias.name.split(".")
                    targets.update(
                        candidate
                        for index in range(len(parts), 0, -1)
                        if (candidate := ".".join(parts[:index])) in known
                    )
            elif isinstance(node, ast.ImportFrom):
                statement = ast.unparse(node)
                targets = _resolve_from_import(
                    node,
                    module=module,
                    path=path,
                    known=known,
                )
            for target in targets:
                if target == module:
                    continue
                edges.add(
                    ImportEdge(
                        source=module,
                        target=target,
                        source_path=path.relative_to(root).as_posix(),
                        line=int(getattr(node, "lineno", 0)),
                        statement=statement,
                    )
                )
    return modules, tuple(sorted(edges, key=lambda edge: (edge.source, edge.target, edge.line)))


def strongly_connected_components(
    modules: set[str],
    edges: tuple[ImportEdge, ...],
) -> tuple[tuple[str, ...], ...]:
    adjacency: dict[str, set[str]] = {module: set() for module in modules}
    for edge in edges:
        adjacency.setdefault(edge.source, set()).add(edge.target)
    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[tuple[str, ...]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in sorted(adjacency.get(node, set())):
            if target not in indices:
                visit(target)
                lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[target])
        if lowlinks[node] != indices[node]:
            return
        component: list[str] = []
        while stack:
            member = stack.pop()
            on_stack.remove(member)
            component.append(member)
            if member == node:
                break
        if len(component) > 1:
            components.append(tuple(sorted(component)))

    for module in sorted(modules):
        if module not in indices:
            visit(module)
    return tuple(sorted(components))


def _matches(value: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(value, pattern) for pattern in patterns)


def _required_string_list(plane: dict[str, Any], field: str) -> list[str]:
    values = plane.get(field)
    if (
        not isinstance(values, list)
        or not values
        or any(not isinstance(value, str) or not value.strip() for value in values)
    ):
        raise ValueError(f"plane {plane.get('name', '<unknown>')} requires non-empty {field}")
    return values


def _validate_plane_shape(name: str, plane: dict[str, Any]) -> list[str]:
    purpose = plane.get("purpose")
    if not isinstance(purpose, str) or not purpose.strip():
        raise ValueError(f"plane {name} requires a purpose")
    for field in (
        "canonical_inputs",
        "canonical_outputs",
        "owned_objects",
        "forbidden_responsibilities",
    ):
        _required_string_list(plane, field)
    dependencies = plane.get("depends_on", [])
    if not isinstance(dependencies, list) or any(
        not isinstance(dependency, str) for dependency in dependencies
    ):
        raise ValueError(f"plane {name} depends_on must be a string list")
    if len(dependencies) != len(set(dependencies)):
        raise ValueError(f"plane {name} has duplicate dependencies")
    return dependencies


def _validate_domain_plane(
    name: str,
    plane: dict[str, Any],
    dependencies: list[str],
    *,
    by_name: dict[str, dict[str, Any]],
    domain_names: set[str],
) -> None:
    rank = plane.get("dependency_rank")
    if not isinstance(rank, int) or isinstance(rank, bool) or rank < 0:
        raise ValueError(f"domain plane {name} requires a non-negative dependency_rank")
    for dependency in dependencies:
        if dependency not in domain_names:
            raise ValueError(f"domain plane {name} has non-domain dependency {dependency}")
        target_rank = by_name[dependency].get("dependency_rank")
        if not isinstance(target_rank, int) or target_rank >= rank:
            raise ValueError(
                f"reverse dependency {name} -> {dependency} violates dependency rank"
            )


def _validate_horizontal_plane(
    name: str,
    plane: dict[str, Any],
    dependencies: list[str],
    *,
    domain_names: set[str],
) -> None:
    if dependencies:
        raise ValueError(f"horizontal plane {name} cannot join the domain DAG")
    supports = plane.get("supports")
    if (
        not isinstance(supports, list)
        or len(supports) != len(domain_names)
        or set(supports) != domain_names
    ):
        raise ValueError("assurance must support every domain plane exactly once")


def _record_owned_objects(
    name: str,
    plane: dict[str, Any],
    object_owners: dict[str, str],
) -> None:
    for owned_object in plane["owned_objects"]:
        previous = object_owners.get(owned_object)
        if previous is not None:
            raise ValueError(
                f"owned object {owned_object} has multiple planes: {previous}, {name}"
            )
        object_owners[owned_object] = name


def _identity_string_list(
    record: dict[str, Any],
    field: str,
    *,
    label: str,
    allow_empty: bool = False,
) -> list[str]:
    values = record.get(field)
    if (
        not isinstance(values, list)
        or (not allow_empty and not values)
        or any(not isinstance(value, str) or not value.strip() for value in values)
    ):
        qualifier = "a string list" if allow_empty else "a non-empty string list"
        raise ValueError(f"{label} requires {field} as {qualifier}")
    if len(values) != len(set(values)):
        raise ValueError(f"{label} has duplicate {field}")
    return values


def _validate_external_source_identity(model: dict[str, Any]) -> None:
    source = model.get("external_source_identity")
    if not isinstance(source, dict):
        raise ValueError("identity model requires external_source_identity")
    if source.get("standard") != "W3C PROV-DM qualified name":
        raise ValueError("external source identity must reuse W3C PROV-DM qualified names")
    if source.get("canonical_key") != ["source_namespace", "source_native_id"]:
        raise ValueError(
            "external source identity key must be source_namespace + source_native_id"
        )
    if source.get("shared_reference_planes") != ["truth", "knowledge"]:
        raise ValueError(
            "Truth and Knowledge must share one external source identity authority"
        )
    if set(source.get("non_authoritative_tokens", [])) != {
        "display_id",
        "request_id",
        "local_alias",
        "path",
    }:
        raise ValueError("external source identity requires exact non-authoritative tokens")


def _validate_identity_namespaces(model: dict[str, Any]) -> None:
    namespaces = model.get("namespaces")
    if not isinstance(namespaces, list) or not namespaces:
        raise ValueError("identity model requires namespaces")
    names: list[str] = []
    for namespace in namespaces:
        if not isinstance(namespace, dict):
            raise ValueError("identity namespace entries must be mappings")
        name = namespace.get("name")
        authority = namespace.get("authority")
        if not isinstance(name, str) or not name:
            raise ValueError("identity namespace requires a name")
        if not isinstance(authority, str) or not authority:
            raise ValueError(f"identity namespace {name} requires authority semantics")
        names.append(name)
    if len(names) != len(set(names)):
        raise ValueError("identity namespace names must be unique")
    if set(names) != REQUIRED_IDENTITY_NAMESPACES:
        raise ValueError("identity namespace vocabulary is incomplete or unknown")


def _validate_substitution_barriers(model: dict[str, Any]) -> None:
    barriers = model.get("substitution_barriers")
    if not isinstance(barriers, list) or not barriers:
        raise ValueError("identity model requires substitution barriers")
    actual: dict[str, frozenset[str]] = {}
    for barrier in barriers:
        if not isinstance(barrier, dict):
            raise ValueError("identity substitution barriers must be mappings")
        source = barrier.get("source")
        if not isinstance(source, str) or not source:
            raise ValueError("identity substitution barrier requires source")
        if source in actual:
            raise ValueError(f"identity substitution source {source} is duplicated")
        targets = _identity_string_list(
            barrier,
            "cannot_replace",
            label=f"identity substitution source {source}",
            allow_empty=True,
        )
        if not set(targets) <= REQUIRED_IDENTITY_NAMESPACES:
            raise ValueError(f"identity substitution source {source} has unknown target")
        actual[source] = frozenset(targets)
    if actual != REQUIRED_SUBSTITUTION_BARRIERS:
        raise ValueError("identity substitution barriers are incomplete or unknown")


def _parse_version_nodes(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    nodes = graph.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("version graph requires nodes")
    by_name: dict[str, dict[str, Any]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            raise ValueError("version graph nodes must be mappings")
        name = node.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("version graph node requires a name")
        if name in by_name:
            raise ValueError(f"version graph node {name} is duplicated")
        by_name[name] = node
    if set(by_name) != REQUIRED_VERSION_NODES:
        raise ValueError("version graph node vocabulary is incomplete or unknown")
    return by_name


def _validate_version_node(
    name: str,
    node: dict[str, Any],
    *,
    nodes: dict[str, dict[str, Any]],
    planes: dict[str, dict[str, Any]],
) -> list[str]:
    owner = node.get("owner_plane")
    if owner not in planes:
        raise ValueError(f"version graph node {name} has unknown owner {owner}")
    if name not in planes[str(owner)]["owned_objects"]:
        raise ValueError(f"version graph node {name} is not owned by plane {owner}")
    if node.get("identity_namespace") not in {"domain-logical", "domain-version"}:
        raise ValueError(f"version graph node {name} has invalid identity namespace")
    expected_history = "append-only" if name == "DecisionRecord" else "immutable"
    if node.get("history") != expected_history:
        raise ValueError(
            f"version graph node {name} must preserve {expected_history} history"
        )
    dependencies = _identity_string_list(
        node,
        "depends_on",
        label=f"version graph node {name}",
        allow_empty=True,
    )
    citations = (
        _identity_string_list(
            node,
            "may_cite",
            label=f"version graph node {name}",
            allow_empty=True,
        )
        if "may_cite" in node
        else []
    )
    for target in (*dependencies, *citations):
        if target not in nodes:
            raise ValueError(f"version graph node {name} references unknown node {target}")
    if name in dependencies:
        raise ValueError(f"version graph node {name} cannot depend on itself")
    return dependencies


def _validate_case_scenario_direction(nodes: dict[str, dict[str, Any]]) -> None:
    case_dependencies = set(nodes["DecisionCaseVersion"]["depends_on"])
    if case_dependencies != {
        "CapitalStateVersion",
        "EvidenceSetVersion",
        "PolicyVersion",
        "ProposalVersion",
    }:
        raise ValueError("DecisionCaseVersion requires the canonical pre-scenario basis")
    if nodes["ScenarioVersion"]["depends_on"] != ["DecisionCaseVersion"]:
        raise ValueError("ScenarioVersion must depend on one DecisionCaseVersion")
    if nodes["DecisionRecord"].get("may_cite") != ["ScenarioVersion"]:
        raise ValueError("DecisionRecord may cite ScenarioVersion without changing Case")


def _validate_acyclic_version_edges(
    nodes: dict[str, dict[str, Any]],
    dependencies: dict[str, list[str]],
) -> None:
    adjacency: dict[str, set[str]] = {name: set() for name in nodes}
    indegree = dict.fromkeys(nodes, 0)
    for name, upstream in dependencies.items():
        for dependency in upstream:
            adjacency[dependency].add(name)
            indegree[name] += 1
    queue = deque(sorted(name for name, degree in indegree.items() if degree == 0))
    visited: list[str] = []
    while queue:
        current = queue.popleft()
        visited.append(current)
        for dependent in sorted(adjacency[current]):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                queue.append(dependent)
    if len(visited) != len(nodes):
        raise ValueError("version graph contains a cycle")


def _validate_freshness_rules(
    graph: dict[str, Any],
    *,
    node_names: set[str],
) -> None:
    rules = graph.get("freshness_rules")
    if not isinstance(rules, list) or not rules:
        raise ValueError("version graph requires freshness rules")
    seen_triggers: set[str] = set()
    affected_nodes: set[str] = set()
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError("freshness rules must be mappings")
        trigger = rule.get("trigger")
        owner = rule.get("owner_plane")
        if not isinstance(trigger, str) or not trigger:
            raise ValueError("freshness rule requires trigger")
        if trigger in seen_triggers:
            raise ValueError(f"freshness trigger {trigger} has multiple owners")
        seen_triggers.add(trigger)
        expected_owner = EXPECTED_FRESHNESS_OWNERS.get(trigger)
        if owner != expected_owner:
            raise ValueError(f"freshness trigger {trigger} requires owner {expected_owner}")
        affected = _identity_string_list(
            rule,
            "affects",
            label=f"freshness trigger {trigger}",
        )
        if not set(affected) <= node_names:
            raise ValueError(f"freshness trigger {trigger} affects unknown node")
        affected_nodes.update(affected)
    if seen_triggers != set(EXPECTED_FRESHNESS_OWNERS):
        raise ValueError("freshness trigger vocabulary is incomplete or unknown")
    if affected_nodes != node_names:
        raise ValueError("every version graph node requires a freshness owner")


def _validate_version_graph(
    model: dict[str, Any],
    *,
    planes: dict[str, dict[str, Any]],
) -> None:
    graph = model.get("version_graph")
    if not isinstance(graph, dict):
        raise ValueError("identity model requires version_graph")
    if graph.get("edge_semantics") != "depends_on names immutable upstream identity inputs":
        raise ValueError("version graph requires canonical edge semantics")
    nodes = _parse_version_nodes(graph)
    dependencies = {
        name: _validate_version_node(name, node, nodes=nodes, planes=planes)
        for name, node in nodes.items()
    }
    _validate_case_scenario_direction(nodes)
    _validate_acyclic_version_edges(nodes, dependencies)
    _validate_freshness_rules(graph, node_names=set(nodes))


def validate_identity_model(
    model: Any,
    *,
    planes: dict[str, dict[str, Any]],
) -> None:
    """Validate identity namespaces and the one-way domain version graph."""

    if not isinstance(model, dict) or model.get("schema") != IDENTITY_MODEL_SCHEMA:
        raise ValueError("unsupported identity and version graph model")
    _validate_external_source_identity(model)
    _validate_identity_namespaces(model)
    _validate_substitution_barriers(model)
    _validate_version_graph(model, planes=planes)


def validate_plane_model(model: dict[str, Any]) -> None:
    """Validate the canonical conceptual plane DAG in the existing matrix."""

    if not isinstance(model, dict) or model.get("schema") != PLANE_MODEL_SCHEMA:
        raise ValueError("unsupported architecture plane model")
    planes = model.get("planes")
    if not isinstance(planes, list) or not planes:
        raise ValueError("architecture plane model requires planes")

    names = [plane.get("name") for plane in planes if isinstance(plane, dict)]
    if len(names) != len(planes) or any(not isinstance(name, str) for name in names):
        raise ValueError("every architecture plane requires a name")
    if len(names) != len(set(names)):
        raise ValueError("architecture plane names must be unique")

    by_name = {str(plane["name"]): plane for plane in planes}
    domain_names = {
        name for name, plane in by_name.items() if plane.get("kind") == "domain"
    }
    horizontal_names = {
        name for name, plane in by_name.items() if plane.get("kind") == "horizontal"
    }
    if horizontal_names != {"assurance"}:
        raise ValueError("assurance must be the sole horizontal plane")
    if not domain_names:
        raise ValueError("architecture plane model requires domain planes")

    object_owners: dict[str, str] = {}
    for name, plane in by_name.items():
        dependencies = _validate_plane_shape(name, plane)
        _record_owned_objects(name, plane, object_owners)

        if plane.get("kind") == "domain":
            _validate_domain_plane(
                name,
                plane,
                dependencies,
                by_name=by_name,
                domain_names=domain_names,
            )
        elif plane.get("kind") == "horizontal":
            _validate_horizontal_plane(
                name,
                plane,
                dependencies,
                domain_names=domain_names,
            )
        else:
            raise ValueError(f"plane {name} has unsupported kind {plane.get('kind')}")
    validate_identity_model(model.get("identity_model"), planes=by_name)


def classify_modules(modules: set[str], matrix: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for module in sorted(modules):
        for layer in matrix["layers"]:
            if _matches(module, list(layer["module_globs"])):
                result[module] = str(layer["name"])
                break
        if module not in result:
            raise ValueError(f"module has no architecture layer: {module}")
    return result


def _rule_forbidden(
    rule: dict[str, Any],
    target: str,
    target_layer: str,
) -> bool:
    return target_layer in set(rule.get("forbidden_target_layers", [])) or _matches(
        target,
        list(rule.get("forbidden_target_modules", [])),
    )


def _shortest_forbidden_path(
    source: str,
    *,
    rule: dict[str, Any],
    adjacency: dict[str, set[str]],
    layers: dict[str, str],
) -> tuple[str, ...] | None:
    queue: deque[tuple[str, ...]] = deque([(source,)])
    seen = {source}
    while queue:
        path = queue.popleft()
        for target in sorted(adjacency.get(path[-1], set())):
            if target in path:
                continue
            candidate = (*path, target)
            if _rule_forbidden(rule, target, layers[target]):
                return candidate
            if target not in seen:
                seen.add(target)
                queue.append(candidate)
    return None


def boundary_violations(
    modules: set[str],
    edges: tuple[ImportEdge, ...],
    matrix: dict[str, Any],
) -> tuple[BoundaryViolation, ...]:
    layers = classify_modules(modules, matrix)
    adjacency: dict[str, set[str]] = {module: set() for module in modules}
    for edge in edges:
        adjacency[edge.source].add(edge.target)
    violations: set[BoundaryViolation] = set()
    for rule in matrix["rules"]:
        sources = set(rule["source_layers"])
        for source in sorted(module for module in modules if layers[module] in sources):
            direct = [
                target
                for target in sorted(adjacency[source])
                if _rule_forbidden(rule, target, layers[target])
            ]
            for target in direct:
                violations.add(
                    BoundaryViolation(
                        rule_id=str(rule["id"]),
                        kind="direct",
                        source_layer=layers[source],
                        target_layer=layers[target],
                        path=(source, target),
                    )
                )
            path = _shortest_forbidden_path(
                source,
                rule=rule,
                adjacency=adjacency,
                layers=layers,
            )
            if path is not None and len(path) > 2:
                violations.add(
                    BoundaryViolation(
                        rule_id=str(rule["id"]),
                        kind="transitive",
                        source_layer=layers[path[0]],
                        target_layer=layers[path[-1]],
                        path=path,
                    )
                )
    return tuple(sorted(violations, key=lambda item: (item.rule_id, item.kind, item.path)))


def load_layer_matrix(path: Path = DEFAULT_MATRIX_PATH) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != "finharness.architecture_layers.v1"
    ):
        raise ValueError("unsupported architecture layer matrix")
    if not payload.get("layers") or not payload.get("rules"):
        raise ValueError("architecture layer matrix requires layers and rules")
    if "plane_model" in payload:
        validate_plane_model(payload["plane_model"])
    return payload


def audit_architecture(
    *,
    root: Path = ROOT,
    matrix_path: Path | None = None,
) -> dict[str, Any]:
    matrix = load_layer_matrix(matrix_path or root / "config" / "architecture-layers.yml")
    source_roots = tuple(str(item) for item in matrix["source_roots"])
    modules, edges = build_canonical_import_graph(root, source_roots)
    cycles = strongly_connected_components(set(modules), edges)
    violations = boundary_violations(set(modules), edges, matrix)
    plane_model = matrix.get("plane_model")
    identity_model = plane_model.get("identity_model") if plane_model else None
    version_graph = identity_model.get("version_graph") if identity_model else None
    return {
        "schema": "finharness.architecture_audit.v1",
        "matrix_schema": matrix["schema"],
        "module_count": len(modules),
        "edge_count": len(edges),
        "cycles": [list(component) for component in cycles],
        "violations": [violation.as_dict() for violation in violations],
        "plane_count": len(plane_model["planes"]) if plane_model else 0,
        "plane_dependency_edges": (
            sum(len(plane.get("depends_on", [])) for plane in plane_model["planes"])
            if plane_model
            else 0
        ),
        "identity_namespace_count": (
            len(identity_model["namespaces"]) if identity_model else 0
        ),
        "version_graph_node_count": len(version_graph["nodes"]) if version_graph else 0,
        "version_graph_edges": (
            sum(len(node.get("depends_on", [])) for node in version_graph["nodes"])
            if version_graph
            else 0
        ),
        "freshness_rule_count": (
            len(version_graph["freshness_rules"]) if version_graph else 0
        ),
        "ok": not cycles and not violations,
    }


def render_audit(audit: dict[str, Any]) -> str:
    return json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True)
