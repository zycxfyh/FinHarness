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
RECORD_TAXONOMY_SCHEMA = "finharness.record_taxonomy.v1"
AGENT_HARNESS_BOUNDARY_SCHEMA = "finharness.agent_harness_boundary.v1"
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
EXPECTED_IDENTITY_AUTHORITIES = {
    "principal": "authenticated principal context",
    "agent-runtime": "bounded runtime invocation only",
    "request": "correlation and idempotency only",
    "external-source": "qualified external source key",
    "domain-logical": "owning domain logical-identity boundary",
    "domain-version": (
        "owning domain version-creation boundary; encoded as RFC 9562 UUIDv7"
    ),
    "git-commit": "repository object and workflow identity only",
}
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
EXPECTED_VERSION_NODE_CONTRACT = {
    "CapitalStateVersion": {
        "owner_plane": "truth",
        "identity_namespace": "domain-version",
        "history": "immutable",
        "depends_on": (),
        "may_cite": (),
    },
    "EvidenceSetVersion": {
        "owner_plane": "knowledge",
        "identity_namespace": "domain-version",
        "history": "immutable",
        "depends_on": (),
        "may_cite": (),
    },
    "PolicyVersion": {
        "owner_plane": "control",
        "identity_namespace": "domain-version",
        "history": "immutable",
        "depends_on": (),
        "may_cite": (),
    },
    "ProposalVersion": {
        "owner_plane": "judgment",
        "identity_namespace": "domain-version",
        "history": "immutable",
        "depends_on": (),
        "may_cite": (),
    },
    "DecisionCaseVersion": {
        "owner_plane": "judgment",
        "identity_namespace": "domain-version",
        "history": "immutable",
        "depends_on": (
            "CapitalStateVersion",
            "EvidenceSetVersion",
            "PolicyVersion",
            "ProposalVersion",
        ),
        "may_cite": (),
    },
    "ScenarioVersion": {
        "owner_plane": "judgment",
        "identity_namespace": "domain-version",
        "history": "immutable",
        "depends_on": ("DecisionCaseVersion",),
        "may_cite": (),
    },
    "ReviewStateVersion": {
        "owner_plane": "judgment",
        "identity_namespace": "domain-version",
        "history": "immutable",
        "depends_on": ("DecisionCaseVersion",),
        "may_cite": (),
    },
    "DecisionRecord": {
        "owner_plane": "judgment",
        "identity_namespace": "domain-logical",
        "history": "append-only",
        "depends_on": ("DecisionCaseVersion",),
        "may_cite": ("ScenarioVersion",),
    },
}
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
EXPECTED_FRESHNESS_CONTRACT = {
    "capital_state_admission": (
        "truth",
        frozenset({"CapitalStateVersion", "DecisionCaseVersion", "ScenarioVersion"}),
    ),
    "evidence_admission_or_withdrawal": (
        "knowledge",
        frozenset({"EvidenceSetVersion", "DecisionCaseVersion", "ScenarioVersion"}),
    ),
    "policy_activation": (
        "control",
        frozenset({"PolicyVersion", "DecisionCaseVersion", "ScenarioVersion"}),
    ),
    "proposal_revision": (
        "judgment",
        frozenset({"ProposalVersion", "DecisionCaseVersion", "ScenarioVersion"}),
    ),
    "case_basis_change": (
        "judgment",
        frozenset({"DecisionCaseVersion", "ScenarioVersion"}),
    ),
    "scenario_recalculation": ("judgment", frozenset({"ScenarioVersion"})),
    "review_event": ("judgment", frozenset({"ReviewStateVersion"})),
    "decision_recorded": ("judgment", frozenset({"DecisionRecord"})),
}
RECORD_CATEGORY_FIELDS = (
    "purpose",
    "truth_owner",
    "authoritative_source",
    "mutability",
    "retention",
    "reconstruction",
    "allowed_references",
    "domain_authority_effect",
    "decision_validity_effect",
    "financial_evidence_admission",
)
EXPECTED_RECORD_CATEGORY_CONTRACT = {
    "DomainRecord": (
        "authoritative domain fact, state transition, or decision history",
        "owning domain plane",
        "owning domain write or admission boundary",
        "immutable version or append-only domain history",
        "domain and legal lifecycle; independent of projection rebuild",
        "authoritative domain history or verified source replay only",
        ("DomainRecord", "ArtifactProvenance", "OperationReceipt"),
        "owning domain policy only",
        "Judgment-owned DomainRecord policy only",
        "owning domain admission boundary only",
    ),
    "OperationReceipt": (
        "integrity-bound operation attempt, outcome, retry, and recovery evidence",
        "bounded operation producer",
        "operation boundary and typed reconciliation resolver",
        "append-only or integrity-linked pending-to-terminal transitions",
        "retry, recovery, and audit horizon; extended while referenced",
        "typed reconciliation may record outcome but cannot fabricate domain effect",
        ("DomainRecord", "OperationReceipt", "ArtifactProvenance", "AgentRunTrace"),
        "none",
        "none",
        "not admissible by receipt presence",
    ),
    "ArtifactProvenance": (
        "immutable artifact origin, derivation, attribution, and integrity binding",
        "artifact producer or qualified external source",
        "W3C PROV-aligned generation and derivation boundary",
        "immutable statements with append-only correction or invalidation",
        "at least the subject artifact and applicable evidence lifecycle",
        "only from verifiable entities, activities, agents, and source bytes",
        ("DomainRecord", "OperationReceipt", "ArtifactProvenance"),
        "none",
        "none",
        "explicit Knowledge or Truth policy required",
    ),
    "AgentRunTrace": (
        "ordered durable execution history of one bounded Agent runtime invocation",
        "Agent runtime",
        "durable unsampled Agent runtime trace and event boundary",
        "append-only canonical trace events with one terminal run outcome",
        "Agent recovery and audit lifecycle with policy-governed redaction",
        "canonical persisted trace records and referenced immutable artifacts;"
        " never sampled telemetry",
        ("DomainRecord", "OperationReceipt", "ArtifactProvenance", "AgentRunTrace"),
        "none",
        "none",
        "explicit domain policy required",
    ),
    "BuildAttestation": (
        "authenticated claim binding a build or verification predicate to subjects",
        "authenticated build or verification system",
        "in-toto Statement and SLSA predicate issued by the builder",
        "immutable authenticated statement; supersession creates a new statement",
        "subject artifact, release, and verification lifecycle",
        "rerun or authenticated reissue; never regenerate from PR prose",
        ("ArtifactProvenance", "BuildAttestation"),
        "none",
        "none",
        "explicit domain policy required",
    ),
    "ProjectionIndex": (
        "disposable discovery or query acceleration over authoritative records",
        "none; upstream category remains authoritative",
        "declared upstream records at a bound generation or high-water mark",
        "replaceable and directly non-authoritative",
        "disposable; delete and rebuild under lifecycle policy",
        "deterministic rebuild from authoritative sources at a bound generation",
        (
            "DomainRecord",
            "OperationReceipt",
            "ArtifactProvenance",
            "AgentRunTrace",
            "BuildAttestation",
        ),
        "none",
        "none",
        "never by index presence",
    ),
}
EXPECTED_RECORD_MIGRATIONS = {
    "statecore_receipt_backed_domain_writes": {
        "canonical_domain_state": {
            "current_role": (
                "receipt-backed canonical domain payload or state history"
            ),
            "current_conformance": "partial",
            "target_category": "DomainRecord",
            "owner_issues": (258, 267, 268, 269, 270, 271),
            "completed_prerequisites": (),
            "disposition": (
                "preserve history and move authority to existing domain write"
                " and admission boundaries"
            ),
        },
        "mutation_operation_evidence": {
            "current_role": (
                "mutation attempt, terminal outcome, retry, and reconciliation"
                " evidence"
            ),
            "current_conformance": "partial",
            "target_category": "OperationReceipt",
            "owner_issues": (383,),
            "completed_prerequisites": (),
            "disposition": (
                "retain operation identity and reconciliation semantics without"
                " granting domain authority"
            ),
        },
        "receipt_discovery_index": {
            "current_role": (
                "lookup rows over canonical receipt or artifact bytes"
            ),
            "current_conformance": "partial",
            "target_category": "ProjectionIndex",
            "owner_issues": (395,),
            "completed_prerequisites": (),
            "disposition": (
                "rebuild from authoritative inventory and prune stale entries"
                " at a bound generation"
            ),
        },
    },
    "receipt_index": {
        "generic_receipt_index_rows": {
            "current_role": (
                "replaceable discovery projection over canonical receipt or"
                " artifact inventory"
            ),
            "current_conformance": "partial",
            "target_category": "ProjectionIndex",
            "owner_issues": (395,),
            "completed_prerequisites": (),
            "disposition": (
                "preserve as rebuildable projection and reject stale or dangling"
                " entries after successful rebuild"
            ),
        },
    },
    "agent_receipt_search": {
        "search_generation_index": {
            "current_role": (
                "generated search projection over retained Agent records"
            ),
            "current_conformance": "partial",
            "target_category": "ProjectionIndex",
            "owner_issues": (367,),
            "completed_prerequisites": (),
            "disposition": (
                "keep generation-bound search state rebuildable and"
                " non-authoritative"
            ),
        },
    },
    "agent_run_receipt_and_trace_sink": {
        "canonical_agent_run_trace": {
            "current_role": (
                "compatibility receipt and trace paths for one Agent work"
                " request"
            ),
            "current_conformance": "partial",
            "target_category": "AgentRunTrace",
            "owner_issues": (291,),
            "completed_prerequisites": (),
            "disposition": (
                "consolidate compatibility paths into one durable ordered"
                " canonical run trace"
            ),
        },
    },
    "legacy_attestation": {
        "historical_review_evidence": {
            "current_role": (
                "retained historical human review and attestation evidence"
            ),
            "current_conformance": "partial",
            "target_category": "DomainRecord",
            "owner_issues": (273,),
            "completed_prerequisites": (),
            "disposition": (
                "preserve historical readability without treating legacy"
                " attestation as current decision truth"
            ),
        },
        "current_decision_truth": {
            "current_role": (
                "legacy consumers treating attestation as current decision or"
                " authority truth"
            ),
            "current_conformance": "not_yet_conforming",
            "target_category": "DomainRecord",
            "owner_issues": (271, 272, 273),
            "completed_prerequisites": (),
            "disposition": (
                "migrate current truth to canonical DecisionRecord and"
                " authority provenance while retaining compatibility reads"
            ),
        },
    },
    "artifact_descriptor_and_import_provenance": {
        "immutable_artifact_descriptor": {
            "current_role": (
                "immutable artifact identity, source bytes, derivation, and"
                " integrity binding"
            ),
            "current_conformance": "partial",
            "target_category": "ArtifactProvenance",
            "owner_issues": (368, 371, 373, 376, 394),
            "completed_prerequisites": (),
            "disposition": (
                "adopt shared immutable artifact and qualified external-source"
                " boundaries"
            ),
        },
    },
    "keyed_mutation_identity_receipt": {
        "keyed_mutation_state_machine": {
            "current_role": (
                "request ownership, pending claim, terminal outcome, replay, and"
                " typed reconciliation evidence"
            ),
            "current_conformance": "partial",
            "target_category": "OperationReceipt",
            "owner_issues": (383, 385, 387, 388, 389),
            "completed_prerequisites": (),
            "disposition": (
                "retain the keyed-mutation state machine while preventing"
                " receipt presence from proving domain effect"
            ),
        },
    },
    "commit_identity_manifest_and_ci_artifacts": {
        "commit_identity_verification_manifest": {
            "current_role": (
                "repository verification JSON artifact binding claim,"
                " repository, commit SHA, ref type, command, and result"
            ),
            "current_conformance": "not_yet_conforming",
            "target_category": "BuildAttestation",
            "owner_issues": (379,),
            "completed_prerequisites": (386,),
            "disposition": (
                "preserve existing commit-identity evidence as compatibility"
                " input; future owner must add authenticated subject and"
                " predicate semantics before claiming BuildAttestation"
                " conformance"
            ),
        },
    },
    "market_data_and_import_receipts": {
        "admitted_market_or_capital_state": {
            "current_role": (
                "domain state admitted from validated market or import data"
            ),
            "current_conformance": "partial",
            "target_category": "DomainRecord",
            "owner_issues": (258,),
            "completed_prerequisites": (),
            "disposition": (
                "keep admitted financial truth behind the owning Truth admission"
                " boundary"
            ),
        },
        "import_operation_outcome": {
            "current_role": (
                "import attempt, validation result, failure, retry, and recovery"
                " evidence"
            ),
            "current_conformance": "partial",
            "target_category": "OperationReceipt",
            "owner_issues": (373, 376),
            "completed_prerequisites": (),
            "disposition": (
                "separate import outcome evidence from admitted financial truth"
            ),
        },
        "imported_source_provenance": {
            "current_role": (
                "imported source identity, bytes, manifest, lineage, and"
                " derivation"
            ),
            "current_conformance": "partial",
            "target_category": "ArtifactProvenance",
            "owner_issues": (373, 376, 394),
            "completed_prerequisites": (),
            "disposition": (
                "preserve source provenance under the shared qualified-source"
                " identity boundary"
            ),
        },
    },
}
EXPECTED_AGENT_TRACE_OBSERVABILITY_EXPORT = {
    "standard": (
        "OpenTelemetry-aligned spans, links, events, and terminal status"
    ),
    "authority": "non-authoritative export of AgentRunTrace",
    "sampling": "permitted for observability export only",
    "redaction": "policy governed",
    "cannot_satisfy": (
        "canonical trace completeness",
        "restart hydration",
        "domain authority",
        "decision validity",
        "financial evidence admission",
    ),
}
EXPECTED_AGENT_HARNESS_BOUNDARY = {
    "schema": AGENT_HARNESS_BOUNDARY_SCHEMA,
    "primary_runtime_path": {
        "current_harness_owner": "finharness.agent_work_loop",
        "selection_point": "AgentWorkDecisionPort",
        "selection_issue": 287,
        "selection_state": "future_adoption_decision",
        "adapter_mode": "single_next_action_decision",
        "decision_cardinality": "one dispatch or complete per invocation",
        "harness_loop_owner": (
            "finharness.agent_work_loop.run_bounded_tool_dispatch_loop"
        ),
        "parallel_core_loops": "forbidden",
        "sdk_runner_loop_on_primary_path": "forbidden",
        "runtime_internal_tool_execution": "forbidden",
        "runtime_internal_handoffs": "forbidden",
        "provider_dependency": "separate_adoption_decision_required",
        "candidates": ["direct Responses API", "OpenAI Agents SDK"],
        "tool_calls_return_as": "AgentWorkToolRequest",
        "all_tool_dispatch_must_cross": [
            "Harness autonomy admission",
            "Harness tool and capability admission",
            "Harness work budgets",
            "canonical Observation reduction",
        ],
    },
    "mature_runtime_capabilities": [
        "model turn loop",
        "tool execution",
        "handoffs",
        "sessions",
        "streaming events",
        "tracing",
    ],
    "delegated_behind_current_decision_port": [
        "one model inference or decision turn",
        "typed candidate tool-call decoding",
        "provider transport retry",
        "token and request usage accounting",
        "non-authoritative observability export",
    ],
    "finharness_owned_semantics": [
        "server-resolved ContextWorld and exact domain-version binding",
        "CapitalState and DecisionCase meaning",
        "evidence admissibility and claim-source policy",
        "tool visibility, admission, and dispatch policy",
        "authority and autonomy admission",
        "stale-world replan policy",
        "independent budgets and stop or escalation policy",
        "domain evaluation and readiness",
        "canonical durable AgentRunTrace and operation receipts",
        "human review, correction, and handoff",
    ],
    "provider_state": {
        "authority": "non-authoritative runtime state",
        "durability": [
            "ephemeral when no resume obligation exists",
            "durable while active pause, resume, or recovery obligation exists",
        ],
        "retention": {
            "may_prune_after": [
                "terminal outcome persisted",
                "canonical trace reconciliation complete",
                "pending human approval resolved or expired",
            ],
        },
        "must_bind": [
            "ContextWorld version",
            "provider and agent definition version",
        ],
        "cannot_replace": [
            "ContextWorld",
            "CapitalStateVersion",
            "DecisionCaseVersion",
            "EvidenceSetVersion",
            "PolicyVersion",
            "AgentRunTrace",
            "DomainRecord",
        ],
    },
    "model_output": {
        "classification": (
            "candidate only until deterministic owning-domain admission"
        ),
        "allowed_outputs": [
            "candidate evidence",
            "data gaps",
            "Scenario request",
            "proposal draft",
            "human handoff",
        ],
        "prohibited_effects": [
            "domain truth mutation",
            "evidence self-admission",
            "authority grant",
            "decision-of-record write",
            "execution authorization",
            "external effect",
        ],
        "execution_allowed": False,
    },
    "mcp_boundary": {
        "owner_issue": 300,
        "lifecycle": "deferred",
        "may_own": [
            "protocol capability negotiation",
            "tools/resources/prompts discovery",
            "protocol lifecycle",
            "transport errors",
            "transport authentication",
            "OAuth token and scope mechanics",
            "resource-server access decision",
        ],
        "finharness_must_own": [
            "approved MCP server allowlist",
            "accepted scope policy",
            "Principal binding",
            "context trust",
            "tool visibility and admission",
            "evidence admission",
            "CapitalMandate",
            "AgentAuthorityGrant",
            "domain truth",
            "decision validity",
            "execution permission",
            "canonical receipts",
        ],
        "transport_authorization_cannot_substitute_for": [
            "principal identity",
            "mandate",
            "grant",
            "tool admission",
            "evidence admission",
            "execution authority",
        ],
    },
    "workflow_engine_boundary": {
        "activation": (
            "measured long-running resume, retry, interrupt, scheduling, or"
            " compensation need plus separate adoption decision"
        ),
        "may_own": [
            "checkpoint mechanics",
            "resume mechanics",
            "scheduling transport",
            "durable interrupts",
            "compensation orchestration",
        ],
        "cannot_own": [
            "CapitalState meaning",
            "DecisionCase meaning",
            "evidence admission",
            "authority policy",
            "stale-world policy",
            "domain evaluation",
            "execution permission",
        ],
        "default_core_dependency": "forbidden",
    },
    "first_evaluation_task": {
        "name": "concentration decision contribution",
        "input_root": {
            "type": "server-resolved ContextWorld",
            "owner_issue": 284,
            "caller_supplied_world_refs": "forbidden",
        },
        "exact_case": {
            "type": "DecisionCaseVersion",
            "basis_match": "required",
        },
        "required_case_basis": [
            "CapitalStateVersion",
            "EvidenceSetVersion",
            "PolicyVersion",
            "ProposalVersion",
        ],
        "basis_resolution": {
            "source": "exact DecisionCaseVersion depends_on",
            "match": "required for every required_case_basis member",
            "independent_latest_or_current_selection": "forbidden",
        },
        "authority_context": {
            "source": "exact ContextWorld",
            "includes": [
                "Principal",
                "CapitalMandateVersion",
                "AgentAuthorityGrantVersion",
            ],
        },
        "mixed_basis": "forbidden",
        "freshness_without_basis_match": "insufficient",
        "allowed_outputs": [
            "candidate evidence",
            "data gaps",
            "Scenario request",
            "proposal draft",
            "human handoff",
        ],
        "evaluation_criteria": [
            "exact world and domain-version freshness",
            "evidence lineage and admission status",
            "deterministic concentration facts separated from model interpretation",
            "uncertainty, counter-evidence, and data gaps",
            "Scenario request when the current basis is insufficient",
            "policy and mandate constraints treated as deterministic inputs",
            "bounded stop, escalation, and human handoff",
            "candidate-only result with no execution authority",
        ],
        "direct_domain_mutation": "forbidden",
        "execution_allowed": False,
        "implementation_state": "not_yet_conforming",
        "implementation_owner_issue": 279,
        "prerequisite_issues": [284, 291],
    },
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
    capability_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "capability_id": self.capability_id,
            "kind": self.kind,
            "source_layer": self.source_layer,
            "target_layer": self.target_layer,
            "target_module": self.path[-1],
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
        expected_authority = EXPECTED_IDENTITY_AUTHORITIES.get(str(name))
        if authority != expected_authority:
            raise ValueError(
                f"identity namespace {name} requires authority {expected_authority}"
            )
        names.append(name)
    if len(names) != len(set(names)):
        raise ValueError("identity namespace names must be unique")
    if set(names) != REQUIRED_IDENTITY_NAMESPACES:
        raise ValueError("identity namespace vocabulary is incomplete or unknown")


def _validate_substitution_barriers(model: dict[str, Any]) -> None:
    if (
        model.get("namespace_substitution_policy")
        != "forbidden_unless_explicitly_allowed"
        or model.get("allowed_namespace_substitutions") != []
    ):
        raise ValueError(
            "declared identity namespaces must be mutually non-substitutable"
        )
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


def _validate_version_node_contract(nodes: dict[str, dict[str, Any]]) -> None:
    for name, expected in EXPECTED_VERSION_NODE_CONTRACT.items():
        node = nodes[name]
        actual = {
            "owner_plane": node.get("owner_plane"),
            "identity_namespace": node.get("identity_namespace"),
            "history": node.get("history"),
            "depends_on": tuple(node.get("depends_on", [])),
            "may_cite": tuple(node.get("may_cite", [])),
        }
        if actual != expected:
            raise ValueError(f"version graph node {name} violates canonical contract")


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
    nodes: dict[str, dict[str, Any]],
) -> None:
    if graph.get("currentness_owner_semantics") != "affected_node.owner_plane":
        raise ValueError("currentness ownership must derive from affected node ownership")
    rules = graph.get("freshness_rules")
    if not isinstance(rules, list) or not rules:
        raise ValueError("version graph requires freshness rules")
    seen_triggers: set[str] = set()
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError("freshness rules must be mappings")
        trigger = rule.get("trigger")
        owner = rule.get("trigger_owner_plane")
        if not isinstance(trigger, str) or not trigger:
            raise ValueError("freshness rule requires trigger")
        if trigger in seen_triggers:
            raise ValueError(f"freshness trigger {trigger} has multiple owners")
        seen_triggers.add(trigger)
        expected_contract = EXPECTED_FRESHNESS_CONTRACT.get(trigger)
        expected_owner = expected_contract[0] if expected_contract else None
        if owner != expected_owner:
            raise ValueError(
                f"freshness trigger {trigger} requires trigger owner {expected_owner}"
            )
        affected = _identity_string_list(
            rule,
            "affects",
            label=f"freshness trigger {trigger}",
        )
        if not set(affected) <= set(nodes):
            raise ValueError(f"freshness trigger {trigger} affects unknown node")
        expected_affected = expected_contract[1] if expected_contract else frozenset()
        if frozenset(affected) != expected_affected:
            raise ValueError(f"freshness trigger {trigger} has non-canonical effects")
    if seen_triggers != set(EXPECTED_FRESHNESS_CONTRACT):
        raise ValueError("freshness trigger vocabulary is incomplete or unknown")


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
    _validate_acyclic_version_edges(nodes, dependencies)
    _validate_version_node_contract(nodes)
    _validate_freshness_rules(graph, nodes=nodes)


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


def _parse_record_categories(taxonomy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    categories = taxonomy.get("categories")
    if not isinstance(categories, list) or not categories:
        raise ValueError("record taxonomy requires categories")
    by_name: dict[str, dict[str, Any]] = {}
    for category in categories:
        if not isinstance(category, dict):
            raise ValueError("record taxonomy categories must be mappings")
        name = category.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("record taxonomy category requires a name")
        if name in by_name:
            raise ValueError(f"record taxonomy category {name} is duplicated")
        by_name[name] = category
    if set(by_name) != set(EXPECTED_RECORD_CATEGORY_CONTRACT):
        raise ValueError("record taxonomy category vocabulary is incomplete or unknown")
    return by_name


def _validate_record_category_contract(
    categories: dict[str, dict[str, Any]],
) -> None:
    category_names = set(categories)
    expected_keys = {"name", *RECORD_CATEGORY_FIELDS}
    for name, expected in EXPECTED_RECORD_CATEGORY_CONTRACT.items():
        category = categories[name]
        if set(category) != expected_keys:
            raise ValueError(f"record category {name} fields violate canonical contract")
        references = _identity_string_list(
            category,
            "allowed_references",
            label=f"record category {name}",
        )
        if not set(references) <= category_names:
            raise ValueError(f"record category {name} references unknown category")
        actual = tuple(
            tuple(references) if field == "allowed_references" else category.get(field)
            for field in RECORD_CATEGORY_FIELDS
        )
        if actual != expected:
            raise ValueError(f"record category {name} violates canonical contract")


_MIGRATION_COMPONENT_FIELDS = frozenset(
    {
        "component",
        "current_role",
        "current_conformance",
        "target_category",
        "owner_issues",
        "completed_prerequisites",
        "disposition",
    }
)
_ALLOWED_CONFORMANCE = frozenset({"conforming", "partial", "not_yet_conforming"})
_VALID_TARGET_CATEGORIES = frozenset(EXPECTED_RECORD_CATEGORY_CONTRACT)


def _parse_record_surface_components(
    taxonomy: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    migrations = taxonomy.get("surface_migrations")
    if not isinstance(migrations, list) or not migrations:
        raise ValueError("record taxonomy requires surface_migrations as a non-empty list")
    surfaces: dict[str, list[dict[str, Any]]] = {}
    for migration in migrations:
        if not isinstance(migration, dict):
            raise ValueError("record surface migration must be a mapping")
        if set(migration) != {"surface", "components"}:
            raise ValueError(
                "record surface migration fields violate canonical contract"
            )
        surface = migration.get("surface")
        if not isinstance(surface, str) or not surface:
            raise ValueError("record surface migration requires a surface name")
        if surface in surfaces:
            raise ValueError(f"record surface migration surface {surface} is duplicated")
        components = migration.get("components")
        if not isinstance(components, list) or not components:
            raise ValueError(
                f"record surface migration surface {surface} requires non-empty components"
            )
        surfaces[surface] = list(components)
    return surfaces


def _validate_record_surface_component(
    surface: str,
    component: dict[str, Any],
) -> None:
    if not isinstance(component, dict):
        raise ValueError(
            f"record surface {surface} component entries must be mappings"
        )
    if set(component) != _MIGRATION_COMPONENT_FIELDS:
        raise ValueError(
            f"record surface {surface} component fields violate canonical contract"
        )
    component_name = component.get("component")
    if not isinstance(component_name, str) or not component_name:
        raise ValueError(
            f"record surface {surface} component requires a name"
        )
    target = component.get("target_category")
    if not isinstance(target, str) or not target:
        raise ValueError(
            f"record surface {surface} component {component_name} "
            f"target_category must be a single string"
        )
    if target not in _VALID_TARGET_CATEGORIES:
        raise ValueError(
            f"record surface {surface} component {component_name} "
            f"has unknown target_category {target}"
        )
    if component.get("current_conformance") not in _ALLOWED_CONFORMANCE:
        raise ValueError(
            f"record surface {surface} component {component_name} "
            f"violates canonical current_conformance"
        )
    owner_issues = component.get("owner_issues")
    if (
        not isinstance(owner_issues, list)
        or not owner_issues
        or any(not isinstance(issue, int) or issue <= 0 for issue in owner_issues)
        or len(owner_issues) != len(set(owner_issues))
    ):
        raise ValueError(
            f"record surface {surface} component {component_name} "
            f"requires non-empty, positive, unique owner_issues"
        )
    prereqs = component.get("completed_prerequisites")
    if not isinstance(prereqs, list) or any(
        not isinstance(p, int) or p <= 0 for p in prereqs
    ):
        raise ValueError(
            f"record surface {surface} component {component_name} "
            f"completed_prerequisites must be a list of positive integers"
        )
    if len(prereqs) != len(set(prereqs)):
        raise ValueError(
            f"record surface {surface} component {component_name} "
            f"completed_prerequisites has duplicates"
        )
    disposition = component.get("disposition")
    if not isinstance(disposition, str) or not disposition:
        raise ValueError(
            f"record surface {surface} component {component_name} "
            f"requires disposition"
        )


def _validate_record_migrations(taxonomy: dict[str, Any]) -> None:
    surfaces = _parse_record_surface_components(taxonomy)
    actual: dict[str, dict[str, dict[str, object]]] = {}
    for surface, components in surfaces.items():
        component_names: set[str] = set()
        surface_components: dict[str, dict[str, object]] = {}
        for component in components:
            _validate_record_surface_component(surface, component)
            comp_name = str(component["component"])
            if comp_name in component_names:
                raise ValueError(
                    f"record surface {surface} component {comp_name} is duplicated"
                )
            component_names.add(comp_name)
            surface_components[comp_name] = {
                "current_role": component["current_role"],
                "current_conformance": component["current_conformance"],
                "target_category": component["target_category"],
                "owner_issues": tuple(component["owner_issues"]),
                "completed_prerequisites": tuple(component["completed_prerequisites"]),
                "disposition": component["disposition"],
            }
        actual[surface] = surface_components
    if actual != EXPECTED_RECORD_MIGRATIONS:
        raise ValueError("record surface migrations are incomplete or non-canonical")


def _validate_agent_trace_observability_export(taxonomy: dict[str, Any]) -> None:
    export = taxonomy.get("agent_trace_observability_export")
    if not isinstance(export, dict):
        raise ValueError("record taxonomy requires agent_trace_observability_export")
    expected_keys = frozenset(EXPECTED_AGENT_TRACE_OBSERVABILITY_EXPORT)
    if set(export) != expected_keys:
        raise ValueError(
            "agent_trace_observability_export fields violate canonical contract"
        )
    for key, expected_value in EXPECTED_AGENT_TRACE_OBSERVABILITY_EXPORT.items():
        actual_value = export.get(key)
        if isinstance(expected_value, tuple):
            if not isinstance(actual_value, (list, tuple)):
                raise ValueError(
                    f"agent_trace_observability_export.{key} must be a list"
                )
            if tuple(actual_value) != expected_value:
                raise ValueError(
                    f"agent_trace_observability_export.{key} is non-canonical"
                )
        elif actual_value != expected_value:
            raise ValueError(
                f"agent_trace_observability_export.{key} is non-canonical"
            )


def validate_record_taxonomy(taxonomy: Any) -> None:
    """Validate explicit record roles without creating a runtime classifier."""

    if not isinstance(taxonomy, dict) or taxonomy.get("schema") != RECORD_TAXONOMY_SCHEMA:
        raise ValueError("unsupported record taxonomy")
    expected_keys = {
        "schema",
        "enforcement",
        "categories",
        "agent_trace_observability_export",
        "surface_migrations",
    }
    if set(taxonomy) != expected_keys:
        raise ValueError(
            "record taxonomy top-level fields violate canonical contract"
        )
    if taxonomy.get("enforcement") != {
        "classification": "explicit_contract_only",
        "universal_base_class": "forbidden",
        "inference_from_name_path_or_storage": "forbidden",
    }:
        raise ValueError("record taxonomy forbids universal bases and inferred categories")
    categories = _parse_record_categories(taxonomy)
    _validate_record_category_contract(categories)
    _validate_record_migrations(taxonomy)
    _validate_agent_trace_observability_export(taxonomy)


def validate_agent_harness_boundary(boundary: Any) -> None:
    """Validate the one runtime-selection point and retained domain ownership."""

    if (
        not isinstance(boundary, dict)
        or boundary.get("schema") != AGENT_HARNESS_BOUNDARY_SCHEMA
    ):
        raise ValueError("unsupported Agent Harness boundary")
    if set(boundary) != set(EXPECTED_AGENT_HARNESS_BOUNDARY):
        raise ValueError(
            "Agent Harness boundary top-level fields violate canonical contract"
        )
    if boundary != EXPECTED_AGENT_HARNESS_BOUNDARY:
        raise ValueError("Agent Harness boundary violates canonical contract")


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
    validate_record_taxonomy(model.get("record_taxonomy"))
    validate_agent_harness_boundary(model.get("agent_harness_boundary"))


CAPABILITY_FIELDS = frozenset({"id", "owner_layer", "semantics", "provider_modules"})
ARCHITECTURE_RULE_FIELDS = frozenset(
    {
        "id",
        "source_layers",
        "forbidden_target_layers",
        "forbidden_target_modules",
        "forbidden_target_capabilities",
    }
)
CAPABILITY_EXCEPTION_FIELDS = frozenset(
    {
        "source_module",
        "rule_id",
        "capability_id",
        "path",
        "reason",
        "owner_issue",
        "review_gate",
    }
)


def _matrix_string_list(
    record: dict[str, Any],
    field: str,
    *,
    label: str,
    allow_empty: bool = False,
) -> list[str]:
    values = record.get(field, [])
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


def _validate_capability_declarations(
    matrix: dict[str, Any],
    *,
    layer_names: set[str],
) -> dict[str, dict[str, Any]]:
    declarations = matrix.get("capabilities", [])
    if not isinstance(declarations, list):
        raise ValueError("architecture capabilities must be a list")
    capabilities: dict[str, dict[str, Any]] = {}
    provider_owner: dict[str, str] = {}
    for declaration in declarations:
        if not isinstance(declaration, dict):
            raise ValueError("architecture capability declarations must be mappings")
        if set(declaration) != CAPABILITY_FIELDS:
            raise ValueError("architecture capability fields violate canonical contract")
        capability_id = declaration.get("id")
        if not isinstance(capability_id, str) or not capability_id.strip():
            raise ValueError("architecture capability requires a stable id")
        if capability_id in capabilities:
            raise ValueError(f"duplicate architecture capability id: {capability_id}")
        owner_layer = declaration.get("owner_layer")
        if owner_layer not in layer_names:
            raise ValueError(
                f"architecture capability {capability_id} has unknown owner layer {owner_layer}"
            )
        semantics = declaration.get("semantics")
        if not isinstance(semantics, str) or not semantics.strip():
            raise ValueError(f"architecture capability {capability_id} requires semantics")
        providers = _matrix_string_list(
            declaration,
            "provider_modules",
            label=f"architecture capability {capability_id}",
        )
        for provider in providers:
            if any(marker in provider for marker in "*?["):
                raise ValueError(
                    f"architecture capability {capability_id} provider must be "
                    f"an exact module: {provider}"
                )
            previous = provider_owner.get(provider)
            if previous is not None:
                raise ValueError(
                    f"architecture capability provider {provider} has multiple capabilities: "
                    f"{previous}, {capability_id}"
                )
            provider_owner[provider] = capability_id
        capabilities[capability_id] = declaration
    return capabilities


def _validate_architecture_rules(
    matrix: dict[str, Any],
    *,
    layer_names: set[str],
    capability_ids: set[str],
) -> dict[str, dict[str, Any]]:
    rules = matrix.get("rules")
    if not isinstance(rules, list) or not rules:
        raise ValueError("architecture layer matrix requires rules")
    by_id: dict[str, dict[str, Any]] = {}
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError("architecture rules must be mappings")
        if not set(rule) <= ARCHITECTURE_RULE_FIELDS:
            raise ValueError("architecture rule fields violate canonical contract")
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not rule_id.strip():
            raise ValueError("architecture rule requires an id")
        if rule_id in by_id:
            raise ValueError(f"duplicate architecture rule id: {rule_id}")
        sources = _matrix_string_list(
            rule, "source_layers", label=f"architecture rule {rule_id}"
        )
        unknown_sources = sorted(set(sources) - layer_names)
        if unknown_sources:
            raise ValueError(
                f"architecture rule {rule_id} has unknown source layers: {unknown_sources}"
            )
        target_layers = _matrix_string_list(
            rule,
            "forbidden_target_layers",
            label=f"architecture rule {rule_id}",
            allow_empty=True,
        )
        unknown_targets = sorted(set(target_layers) - layer_names)
        if unknown_targets:
            raise ValueError(
                f"architecture rule {rule_id} has unknown target layers: {unknown_targets}"
            )
        target_modules = _matrix_string_list(
            rule,
            "forbidden_target_modules",
            label=f"architecture rule {rule_id}",
            allow_empty=True,
        )
        target_capabilities = _matrix_string_list(
            rule,
            "forbidden_target_capabilities",
            label=f"architecture rule {rule_id}",
            allow_empty=True,
        )
        unknown_capabilities = sorted(set(target_capabilities) - capability_ids)
        if unknown_capabilities:
            raise ValueError(
                f"architecture rule {rule_id} references unknown capabilities: "
                f"{unknown_capabilities}"
            )
        if not target_layers and not target_modules and not target_capabilities:
            raise ValueError(f"architecture rule {rule_id} has no forbidden target")
        by_id[rule_id] = rule
    return by_id


def _validate_capability_exception_scope(
    exception: dict[str, Any],
    *,
    rules: dict[str, dict[str, Any]],
    capabilities: dict[str, dict[str, Any]],
) -> tuple[str, str, str, tuple[str, ...]]:
    source = exception.get("source_module")
    if (
        not isinstance(source, str)
        or not source.strip()
        or any(marker in source for marker in "*?[")
        or source in {"finharness", "core", "agent", "research"}
    ):
        raise ValueError("capability exception source_module must be one exact module")
    rule_id = exception.get("rule_id")
    if rule_id not in rules:
        raise ValueError(f"capability exception references unknown rule: {rule_id}")
    capability_id = exception.get("capability_id")
    if capability_id not in capabilities:
        raise ValueError(
            f"capability exception references unknown capability: {capability_id}"
        )
    if capability_id not in rules[str(rule_id)].get(
        "forbidden_target_capabilities", []
    ):
        raise ValueError(
            f"capability exception {source} cannot mask capability {capability_id} "
            f"for rule {rule_id}"
        )
    path = _matrix_string_list(
        exception, "path", label=f"capability exception {source}"
    )
    if len(path) < 2 or path[0] != source:
        raise ValueError("capability exception path must start at its exact source")
    if path[-1] not in capabilities[str(capability_id)]["provider_modules"]:
        raise ValueError(
            "capability exception path must terminate at a provider of its capability"
        )
    if any(any(marker in module for marker in "*?[") for module in path):
        raise ValueError("capability exception path must contain exact modules")
    return source, str(rule_id), str(capability_id), tuple(path)


def _validate_capability_exception_governance(exception: dict[str, Any]) -> None:
    reason = exception.get("reason")
    if (
        not isinstance(reason, str)
        or len(reason.strip()) < 12
        or reason.strip().lower() in {"temporary", "legacy", "needed"}
    ):
        raise ValueError("capability exception requires a concrete reason")
    owner_issue = exception.get("owner_issue")
    if (
        not isinstance(owner_issue, int)
        or isinstance(owner_issue, bool)
        or owner_issue < 1
    ):
        raise ValueError("capability exception requires a positive owner_issue")
    review_gate = exception.get("review_gate")
    if (
        not isinstance(review_gate, str)
        or len(review_gate.strip()) < 12
        or review_gate.strip().lower() in {"later", "tbd", "none"}
    ):
        raise ValueError("capability exception requires a concrete review_gate")


def _validate_capability_exceptions(
    matrix: dict[str, Any],
    *,
    rules: dict[str, dict[str, Any]],
    capabilities: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    exceptions = matrix.get("capability_exceptions", [])
    if not isinstance(exceptions, list):
        raise ValueError("capability_exceptions must be a list")
    seen: set[tuple[str, str, str, tuple[str, ...]]] = set()
    for exception in exceptions:
        if not isinstance(exception, dict) or set(exception) != CAPABILITY_EXCEPTION_FIELDS:
            raise ValueError("capability exception fields violate canonical contract")
        key = _validate_capability_exception_scope(
            exception, rules=rules, capabilities=capabilities
        )
        _validate_capability_exception_governance(exception)
        if key in seen:
            raise ValueError(f"duplicate capability exception: {key}")
        seen.add(key)
    return exceptions


def _architecture_layer_names(matrix: dict[str, Any]) -> set[str]:
    layers = matrix.get("layers")
    if not isinstance(layers, list) or not layers:
        raise ValueError("architecture layer matrix requires layers")
    names: list[str] = []
    for layer in layers:
        if not isinstance(layer, dict):
            raise ValueError("architecture layers must be mappings")
        name = layer.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("architecture layer requires a name")
        _matrix_string_list(layer, "module_globs", label=f"architecture layer {name}")
        names.append(name)
    if len(names) != len(set(names)):
        raise ValueError("architecture layer names must be unique")
    return set(names)


def _validate_capability_module_universe(
    capabilities: dict[str, dict[str, Any]],
    rules: dict[str, dict[str, Any]],
    exceptions: list[dict[str, Any]],
    *,
    matrix: dict[str, Any],
    modules: set[str],
) -> None:
    layers_by_module = classify_modules(modules, matrix)
    for capability_id, declaration in capabilities.items():
        owner = declaration["owner_layer"]
        for provider in declaration["provider_modules"]:
            if provider not in modules:
                raise ValueError(
                    f"architecture capability {capability_id} provider is absent: {provider}"
                )
            if layers_by_module[provider] != owner:
                raise ValueError(
                    f"architecture capability {capability_id} provider {provider} "
                    f"belongs to layer {layers_by_module[provider]}, not owner {owner}"
                )
    for exception in exceptions:
        absent_path_modules = sorted(set(exception["path"]) - modules)
        if absent_path_modules:
            raise ValueError(
                "capability exception path modules are absent: "
                f"{absent_path_modules}"
            )
        source_layer = layers_by_module[exception["source_module"]]
        rule = rules[exception["rule_id"]]
        if source_layer not in rule["source_layers"]:
            raise ValueError(
                f"capability exception source layer {source_layer} is outside rule "
                f"{exception['rule_id']}"
            )


def validate_architecture_matrix(
    matrix: dict[str, Any],
    *,
    modules: set[str] | None = None,
) -> None:
    """Validate capability declarations against the canonical layer matrix."""

    layer_names = _architecture_layer_names(matrix)

    capabilities = _validate_capability_declarations(
        matrix, layer_names=layer_names
    )
    rules = _validate_architecture_rules(
        matrix,
        layer_names=layer_names,
        capability_ids=set(capabilities),
    )
    exceptions = _validate_capability_exceptions(
        matrix,
        rules=rules,
        capabilities=capabilities,
    )
    if modules is None:
        return
    _validate_capability_module_universe(
        capabilities, rules, exceptions, matrix=matrix, modules=modules
    )


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


def _shortest_path_to_targets(
    source: str,
    *,
    targets: set[str],
    adjacency: dict[str, set[str]],
    excluded_paths: set[tuple[str, ...]] | None = None,
) -> tuple[str, ...] | None:
    queue: deque[tuple[str, ...]] = deque([(source,)])
    seen = {source}
    excluded_paths = excluded_paths or set()
    while queue:
        path = queue.popleft()
        for target in sorted(adjacency.get(path[-1], set())):
            if target in path:
                continue
            candidate = (*path, target)
            if target in targets:
                if candidate not in excluded_paths:
                    return candidate
                continue
            # Exact path exceptions require considering an alternate route to
            # the same intermediate module. With no exceptions, retain the
            # original linear-time canonical BFS behavior.
            if excluded_paths or target not in seen:
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
    capabilities = {
        str(capability["id"]): set(capability["provider_modules"])
        for capability in matrix.get("capabilities", [])
    }
    capability_exceptions = {
        (
            str(exception["source_module"]),
            str(exception["rule_id"]),
            str(exception["capability_id"]),
            tuple(exception["path"]),
        )
        for exception in matrix.get("capability_exceptions", [])
    }
    violations: set[BoundaryViolation] = set()
    for rule in matrix["rules"]:
        sources = set(rule["source_layers"])
        for source in sorted(module for module in modules if layers[module] in sources):
            forbidden_modules = {
                target
                for target in modules
                if _rule_forbidden(rule, target, layers[target])
            }
            for target in sorted(adjacency[source] & forbidden_modules):
                violations.add(
                    BoundaryViolation(
                        rule_id=str(rule["id"]),
                        kind="direct",
                        source_layer=layers[source],
                        target_layer=layers[target],
                        path=(source, target),
                    )
                )
            path = _shortest_path_to_targets(
                source,
                targets=forbidden_modules,
                adjacency=adjacency,
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
            for capability_id in rule.get("forbidden_target_capabilities", []):
                providers = capabilities[capability_id]
                excluded_paths = {
                    exception_path
                    for (
                        exception_source,
                        exception_rule,
                        exception_capability,
                        exception_path,
                    ) in capability_exceptions
                    if exception_source == source
                    and exception_rule == str(rule["id"])
                    and exception_capability == capability_id
                }
                for target in sorted(adjacency[source] & providers):
                    direct_path = (source, target)
                    if (
                        source,
                        str(rule["id"]),
                        capability_id,
                        direct_path,
                    ) in capability_exceptions:
                        continue
                    violations.add(
                        BoundaryViolation(
                            rule_id=str(rule["id"]),
                            capability_id=capability_id,
                            kind="direct",
                            source_layer=layers[source],
                            target_layer=layers[target],
                            path=direct_path,
                        )
                    )
                path = _shortest_path_to_targets(
                    source,
                    targets=providers,
                    adjacency=adjacency,
                    excluded_paths=excluded_paths,
                )
                if path is not None and len(path) > 2:
                    if (
                        source,
                        str(rule["id"]),
                        capability_id,
                        path,
                    ) in capability_exceptions:
                        continue
                    violations.add(
                        BoundaryViolation(
                            rule_id=str(rule["id"]),
                            capability_id=capability_id,
                            kind="transitive",
                            source_layer=layers[path[0]],
                            target_layer=layers[path[-1]],
                            path=path,
                        )
                    )
    return tuple(
        sorted(
            violations,
            key=lambda item: (
                item.rule_id,
                item.capability_id or "",
                item.kind,
                item.path,
            ),
        )
    )


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
    validate_architecture_matrix(payload)
    return payload


def audit_architecture(
    *,
    root: Path = ROOT,
    matrix_path: Path | None = None,
) -> dict[str, Any]:
    matrix = load_layer_matrix(matrix_path or root / "config" / "architecture-layers.yml")
    source_roots = tuple(str(item) for item in matrix["source_roots"])
    modules, edges = build_canonical_import_graph(root, source_roots)
    validate_architecture_matrix(matrix, modules=set(modules))
    cycles = strongly_connected_components(set(modules), edges)
    violations = boundary_violations(set(modules), edges, matrix)
    plane_model = matrix.get("plane_model")
    identity_model = plane_model.get("identity_model") if plane_model else None
    version_graph = identity_model.get("version_graph") if identity_model else None
    record_taxonomy = plane_model.get("record_taxonomy") if plane_model else None
    agent_harness = (
        plane_model.get("agent_harness_boundary") if plane_model else None
    )
    return {
        "schema": "finharness.architecture_audit.v1",
        "matrix_schema": matrix["schema"],
        "module_count": len(modules),
        "edge_count": len(edges),
        "cycles": [list(component) for component in cycles],
        "violations": [violation.as_dict() for violation in violations],
        "capability_count": len(matrix.get("capabilities", [])),
        "capability_provider_count": sum(
            len(capability["provider_modules"])
            for capability in matrix.get("capabilities", [])
        ),
        "capability_exception_count": len(matrix.get("capability_exceptions", [])),
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
        "record_category_count": (
            len(record_taxonomy["categories"]) if record_taxonomy else 0
        ),
        "record_surface_migration_count": (
            len(record_taxonomy["surface_migrations"]) if record_taxonomy else 0
        ),
        "record_surface_component_count": (
            sum(
                len(surface["components"])
                for surface in record_taxonomy["surface_migrations"]
            )
            if record_taxonomy
            else 0
        ),
        "agent_mature_runtime_capability_count": (
            len(agent_harness["mature_runtime_capabilities"])
            if agent_harness
            else 0
        ),
        "agent_delegated_decision_mechanic_count": (
            len(agent_harness["delegated_behind_current_decision_port"])
            if agent_harness
            else 0
        ),
        "agent_dispatch_crossing_count": (
            len(agent_harness["primary_runtime_path"]["all_tool_dispatch_must_cross"])
            if agent_harness
            else 0
        ),
        "agent_harness_semantic_count": (
            len(agent_harness["finharness_owned_semantics"])
            if agent_harness
            else 0
        ),
        "agent_first_task_output_count": (
            len(agent_harness["first_evaluation_task"]["allowed_outputs"])
            if agent_harness
            else 0
        ),
        "agent_first_task_evaluation_criterion_count": (
            len(agent_harness["first_evaluation_task"]["evaluation_criteria"])
            if agent_harness
            else 0
        ),
        "agent_first_task_case_basis_count": (
            len(agent_harness["first_evaluation_task"]["required_case_basis"])
            if agent_harness
            else 0
        ),
        "agent_authority_context_binding_count": (
            len(agent_harness["first_evaluation_task"]["authority_context"]["includes"])
            if agent_harness
            else 0
        ),
        "ok": not cycles and not violations,
    }


def render_audit(audit: dict[str, Any]) -> str:
    return json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True)
