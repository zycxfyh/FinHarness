from __future__ import annotations

import copy
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

import yaml

from finharness.architecture_boundaries import (
    audit_architecture,
    build_canonical_import_graph,
    load_layer_matrix,
    validate_agent_harness_boundary,
    validate_architecture_matrix,
    validate_identity_model,
    validate_plane_model,
    validate_record_taxonomy,
)

MATRIX = """\
schema: finharness.architecture_layers.v1
source_roots: [src]
layers:
  - name: statecore
    module_globs: [pkg.statecore, pkg.statecore.*]
  - name: api_frontend
    module_globs: [pkg.api, pkg.api.*]
  - name: core
    module_globs: [pkg, pkg.*]
rules:
  - id: statecore-foundation
    source_layers: [statecore]
    forbidden_target_layers: [api_frontend]
"""

CAPABILITY_MATRIX = """\
schema: finharness.architecture_layers.v1
source_roots: [src]
layers:
  - name: statecore
    module_globs: [finharness.statecore, finharness.statecore.*]
  - name: execution
    module_globs: [finharness.execution, finharness.execution.*]
  - name: agent
    module_globs: [finharness.agent_*]
  - name: research
    module_globs: [finharness.research_*]
  - name: core
    module_globs: [finharness, finharness.*]
capabilities:
  - id: execution.broker_registry_resolution
    owner_layer: execution
    semantics: Resolve the configured broker adapter.
    provider_modules: [finharness.execution.broker]
  - id: execution.broker_submission
    owner_layer: execution
    semantics: Submit an order through the canonical command or adapter.
    provider_modules:
      - finharness.execution.commands
      - finharness.execution.adapters.simulated_broker
  - id: statecore.canonical_mutation
    owner_layer: statecore
    semantics: Mutate canonical StateCore state.
    provider_modules:
      - finharness.statecore.capital_mandates
      - finharness.statecore.agent_authority_grants
      - finharness.statecore.snapshot_ingest
      - finharness.statecore.proposals
      - finharness.statecore.receipt_index
capability_exceptions: []
rules:
  - id: agent-does-not-bypass-execution-commands
    source_layers: [agent]
    forbidden_target_capabilities:
      - execution.broker_registry_resolution
      - execution.broker_submission
  - id: research-does-not-write-state-or-execute
    source_layers: [research]
    forbidden_target_capabilities: [statecore.canonical_mutation]
"""


class ArchitectureBoundaryTest(unittest.TestCase):
    _CAPABILITY_PROVIDER_FILES: ClassVar[dict[str, str]] = {
        "src/finharness/__init__.py": "",
        "src/finharness/execution/broker.py": "",
        "src/finharness/execution/commands.py": "",
        "src/finharness/execution/adapters/simulated_broker.py": "",
        "src/finharness/statecore/capital_mandates.py": "",
        "src/finharness/statecore/agent_authority_grants.py": "",
        "src/finharness/statecore/snapshot_ingest.py": "",
        "src/finharness/statecore/proposals.py": "",
        "src/finharness/statecore/receipt_index.py": "",
        "src/finharness/statecore/models.py": "",
        "src/finharness/statecore/decision_scaffold.py": "",
        "src/finharness/agent_capabilities.py": "",
    }

    def _repo(self, files: dict[str, str]) -> tuple[tempfile.TemporaryDirectory, Path]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        for relative, content in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        (root / "matrix.yml").write_text(MATRIX, encoding="utf-8")
        return temp, root

    def _capability_repo(
        self,
        files: dict[str, str],
        *,
        mutate: Callable[[dict[str, Any]], None] | None = None,
    ) -> tuple[tempfile.TemporaryDirectory, Path]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        for relative, content in {**self._CAPABILITY_PROVIDER_FILES, **files}.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        matrix = yaml.safe_load(CAPABILITY_MATRIX)
        if mutate is not None:
            mutate(matrix)
        (root / "matrix.yml").write_text(
            yaml.safe_dump(matrix, sort_keys=False), encoding="utf-8"
        )
        return temp, root

    def test_relative_imports_resolve_to_canonical_modules(self) -> None:
        temp, root = self._repo(
            {
                "src/pkg/__init__.py": "",
                "src/pkg/a.py": "from . import b\n",
                "src/pkg/b.py": "from .sub import c\n",
                "src/pkg/sub/__init__.py": "",
                "src/pkg/sub/c.py": "VALUE = 1\n",
            }
        )
        self.addCleanup(temp.cleanup)
        _, edges = build_canonical_import_graph(root, ("src",))
        pairs = {(edge.source, edge.target) for edge in edges}
        self.assertIn(("pkg.a", "pkg.b"), pairs)
        self.assertIn(("pkg.b", "pkg.sub.c"), pairs)

    def test_same_production_gate_reports_cycle(self) -> None:
        temp, root = self._repo(
            {
                "src/pkg/__init__.py": "",
                "src/pkg/a.py": "from . import b\n",
                "src/pkg/b.py": "from . import a\n",
            }
        )
        self.addCleanup(temp.cleanup)
        audit = audit_architecture(root=root, matrix_path=root / "matrix.yml")
        self.assertFalse(audit["ok"])
        self.assertEqual(audit["cycles"], [["pkg.a", "pkg.b"]])

    def test_direct_and_transitive_forbidden_paths_are_complete(self) -> None:
        temp, root = self._repo(
            {
                "src/pkg/__init__.py": "",
                "src/pkg/statecore/__init__.py": "",
                "src/pkg/statecore/direct.py": "from pkg.api import endpoint\n",
                "src/pkg/statecore/indirect.py": "from pkg import bridge\n",
                "src/pkg/bridge.py": "from pkg.api import endpoint\n",
                "src/pkg/api/__init__.py": "",
                "src/pkg/api/endpoint.py": "VALUE = 1\n",
            }
        )
        self.addCleanup(temp.cleanup)
        audit = audit_architecture(root=root, matrix_path=root / "matrix.yml")
        paths = {(item["kind"], tuple(item["path"])) for item in audit["violations"]}
        self.assertIn(
            ("direct", ("pkg.statecore.direct", "pkg.api.endpoint")),
            paths,
        )
        self.assertIn(
            ("transitive", ("pkg.statecore.indirect", "pkg.bridge", "pkg.api.endpoint")),
            paths,
        )

    def test_agent_broker_capability_rejects_direct_and_hidden_paths(self) -> None:
        cases = (
            (
                "direct registry resolution",
                {"src/finharness/agent_probe.py": "import finharness.execution.broker\n"},
                "execution.broker_registry_resolution",
                "direct",
                ("finharness.agent_probe", "finharness.execution.broker"),
            ),
            (
                "hidden registry resolution",
                {
                    "src/finharness/agent_probe.py": "import finharness.neutral_helper\n",
                    "src/finharness/neutral_helper.py": "import finharness.execution.broker\n",
                },
                "execution.broker_registry_resolution",
                "transitive",
                (
                    "finharness.agent_probe",
                    "finharness.neutral_helper",
                    "finharness.execution.broker",
                ),
            ),
            (
                "actual submission command",
                {"src/finharness/agent_probe.py": "import finharness.execution.commands\n"},
                "execution.broker_submission",
                "direct",
                ("finharness.agent_probe", "finharness.execution.commands"),
            ),
            (
                "hidden adapter submission",
                {
                    "src/finharness/agent_probe.py": "import finharness.neutral_helper\n",
                    "src/finharness/neutral_helper.py": (
                        "import finharness.execution.adapters.simulated_broker\n"
                    ),
                },
                "execution.broker_submission",
                "transitive",
                (
                    "finharness.agent_probe",
                    "finharness.neutral_helper",
                    "finharness.execution.adapters.simulated_broker",
                ),
            ),
        )
        for label, files, capability_id, kind, path in cases:
            with self.subTest(label=label):
                temp, root = self._capability_repo(files)
                try:
                    audit = audit_architecture(
                        root=root, matrix_path=root / "matrix.yml"
                    )
                finally:
                    temp.cleanup()
                matches = [
                    violation
                    for violation in audit["violations"]
                    if violation["capability_id"] == capability_id
                ]
                self.assertEqual(len(matches), 1)
                self.assertEqual(matches[0]["kind"], kind)
                self.assertEqual(tuple(matches[0]["path"]), path)
                self.assertEqual(
                    matches[0]["rule_id"],
                    "agent-does-not-bypass-execution-commands",
                )

    def test_research_mutation_capability_covers_representative_writers(self) -> None:
        providers = (
            "capital_mandates",
            "agent_authority_grants",
            "snapshot_ingest",
            "proposals",
            "receipt_index",
        )
        for provider in providers:
            target = f"finharness.statecore.{provider}"
            for hidden in (False, True):
                with self.subTest(provider=provider, hidden=hidden):
                    files = {
                        "src/finharness/research_probe.py": (
                            "import finharness.neutral_helper\n"
                            if hidden
                            else f"import {target}\n"
                        )
                    }
                    expected_path: tuple[str, ...] = (
                        "finharness.research_probe",
                        target,
                    )
                    if hidden:
                        files["src/finharness/neutral_helper.py"] = f"import {target}\n"
                        expected_path = (
                            "finharness.research_probe",
                            "finharness.neutral_helper",
                            target,
                        )
                    temp, root = self._capability_repo(files)
                    try:
                        audit = audit_architecture(
                            root=root, matrix_path=root / "matrix.yml"
                        )
                    finally:
                        temp.cleanup()
                    violation = audit["violations"][0]
                    self.assertEqual(
                        violation["capability_id"], "statecore.canonical_mutation"
                    )
                    self.assertEqual(
                        violation["kind"], "transitive" if hidden else "direct"
                    )
                    self.assertEqual(tuple(violation["path"]), expected_path)

    def test_new_capability_provider_is_enforced_without_rule_change(self) -> None:
        def add_provider(matrix: dict[str, Any]) -> None:
            mutation = next(
                capability
                for capability in matrix["capabilities"]
                if capability["id"] == "statecore.canonical_mutation"
            )
            mutation["provider_modules"].append("finharness.statecore.new_writer")

        temp, root = self._capability_repo(
            {
                "src/finharness/statecore/new_writer.py": "",
                "src/finharness/research_probe.py": (
                    "import finharness.statecore.new_writer\n"
                ),
            },
            mutate=add_provider,
        )
        self.addCleanup(temp.cleanup)
        audit = audit_architecture(root=root, matrix_path=root / "matrix.yml")
        self.assertEqual(len(audit["violations"]), 1)
        self.assertEqual(
            audit["violations"][0]["capability_id"],
            "statecore.canonical_mutation",
        )
        self.assertEqual(
            audit["violations"][0]["target_module"],
            "finharness.statecore.new_writer",
        )

    def test_capabilities_preserve_legitimate_read_only_paths(self) -> None:
        temp, root = self._capability_repo(
            {
                "src/finharness/research_projection.py": (
                    "import finharness.statecore.models\n"
                    "import finharness.statecore.decision_scaffold\n"
                ),
                "src/finharness/agent_probe.py": (
                    "import finharness.agent_capabilities\n"
                    "import finharness.statecore.models\n"
                ),
            }
        )
        self.addCleanup(temp.cleanup)
        audit = audit_architecture(root=root, matrix_path=root / "matrix.yml")
        self.assertEqual(audit["violations"], [])
        self.assertTrue(audit["ok"])

    def test_capability_configuration_corruption_fails_closed(self) -> None:
        base = yaml.safe_load(CAPABILITY_MATRIX)

        def mutation_capability(matrix: dict[str, Any]) -> dict[str, Any]:
            return next(
                capability
                for capability in matrix["capabilities"]
                if capability["id"] == "statecore.canonical_mutation"
            )

        corruptions: tuple[tuple[str, Callable[[dict[str, Any]], None], str], ...] = (
            (
                "unknown capability reference",
                lambda matrix: matrix["rules"][0][
                    "forbidden_target_capabilities"
                ].append("execution.unknown"),
                "references unknown capabilities",
            ),
            (
                "duplicate capability id",
                lambda matrix: matrix["capabilities"].append(
                    copy.deepcopy(matrix["capabilities"][0])
                ),
                "duplicate architecture capability id",
            ),
            (
                "duplicate provider",
                lambda matrix: mutation_capability(matrix)["provider_modules"].append(
                    mutation_capability(matrix)["provider_modules"][0]
                ),
                "duplicate provider_modules",
            ),
            (
                "empty provider set",
                lambda matrix: mutation_capability(matrix).__setitem__(
                    "provider_modules", []
                ),
                "provider_modules as a non-empty string list",
            ),
            (
                "unknown owner layer",
                lambda matrix: mutation_capability(matrix).__setitem__(
                    "owner_layer", "unknown"
                ),
                "unknown owner layer",
            ),
            (
                "missing owner layer",
                lambda matrix: mutation_capability(matrix).pop("owner_layer"),
                "fields violate canonical contract",
            ),
            (
                "broad provider pattern",
                lambda matrix: mutation_capability(matrix).__setitem__(
                    "provider_modules", ["finharness.statecore.*"]
                ),
                "provider must be an exact module",
            ),
            (
                "capability removed while referenced",
                lambda matrix: matrix["capabilities"].pop(0),
                "references unknown capabilities",
            ),
            (
                "misspelled parallel rule field",
                lambda matrix: matrix["rules"][0].__setitem__(
                    "forbidden_target_capability", "execution.broker_submission"
                ),
                "rule fields violate canonical contract",
            ),
        )
        for label, corrupt, message in corruptions:
            with self.subTest(label=label):
                matrix = copy.deepcopy(base)
                corrupt(matrix)
                with self.assertRaisesRegex(ValueError, message):
                    validate_architecture_matrix(matrix)

    def test_capability_exceptions_are_exact_and_review_gated(self) -> None:
        valid_exception = {
            "source_module": "finharness.agent_probe",
            "rule_id": "agent-does-not-bypass-execution-commands",
            "capability_id": "execution.broker_registry_resolution",
            "path": ["finharness.agent_probe", "finharness.execution.broker"],
            "reason": "Bounded compatibility path pending removal.",
            "owner_issue": 369,
            "review_gate": "Remove after compatibility path migration.",
        }
        base = yaml.safe_load(CAPABILITY_MATRIX)
        corruptions = (
            (
                "broad source",
                {**valid_exception, "source_module": "finharness.*"},
                "one exact module",
            ),
            (
                "wrong capability",
                {**valid_exception, "capability_id": "statecore.canonical_mutation"},
                "cannot mask capability",
            ),
            (
                "unknown owner issue",
                {**valid_exception, "owner_issue": 0},
                "positive owner_issue",
            ),
            (
                "missing review gate",
                {**valid_exception, "review_gate": ""},
                "concrete review_gate",
            ),
            (
                "vague reason",
                {**valid_exception, "reason": "temporary"},
                "concrete reason",
            ),
        )
        for label, exception, message in corruptions:
            with self.subTest(label=label):
                matrix = copy.deepcopy(base)
                matrix["capability_exceptions"] = [exception]
                with self.assertRaisesRegex(ValueError, message):
                    validate_architecture_matrix(matrix)

    def test_capability_exception_does_not_mask_another_path(self) -> None:
        def add_exception(matrix: dict[str, Any]) -> None:
            matrix["capability_exceptions"] = [
                {
                    "source_module": "finharness.agent_probe",
                    "rule_id": "agent-does-not-bypass-execution-commands",
                    "capability_id": "execution.broker_registry_resolution",
                    "path": [
                        "finharness.agent_probe",
                        "finharness.neutral_helper",
                        "finharness.execution.broker",
                    ],
                    "reason": "Bounded compatibility path pending removal.",
                    "owner_issue": 369,
                    "review_gate": "Remove after compatibility path migration.",
                }
            ]

        temp, root = self._capability_repo(
            {
                "src/finharness/agent_probe.py": (
                    "import finharness.neutral_helper\n"
                    "import finharness.second_helper\n"
                ),
                "src/finharness/neutral_helper.py": (
                    "import finharness.execution.broker\n"
                ),
                "src/finharness/second_helper.py": (
                    "import finharness.execution.broker\n"
                ),
            },
            mutate=add_exception,
        )
        self.addCleanup(temp.cleanup)
        audit = audit_architecture(root=root, matrix_path=root / "matrix.yml")
        paths = [
            tuple(violation["path"])
            for violation in audit["violations"]
            if violation["capability_id"] == "execution.broker_registry_resolution"
        ]
        self.assertEqual(
            paths,
            [
                (
                    "finharness.agent_probe",
                    "finharness.second_helper",
                    "finharness.execution.broker",
                )
            ],
        )

    def test_capability_provider_absent_from_module_universe_is_rejected(self) -> None:
        temp, root = self._capability_repo({})
        self.addCleanup(temp.cleanup)
        (root / "src/finharness/statecore/receipt_index.py").unlink()
        with self.assertRaisesRegex(ValueError, "provider is absent"):
            audit_architecture(root=root, matrix_path=root / "matrix.yml")

    def test_current_repository_passes_the_ci_gate(self) -> None:
        audit = audit_architecture()
        self.assertEqual(audit["cycles"], [])
        self.assertEqual(audit["violations"], [])
        self.assertEqual(audit["plane_count"], 8)
        self.assertGreater(audit["plane_dependency_edges"], 0)
        self.assertEqual(audit["identity_namespace_count"], 7)
        self.assertEqual(audit["version_graph_node_count"], 8)
        self.assertEqual(audit["version_graph_edges"], 7)
        self.assertEqual(audit["freshness_rule_count"], 8)
        self.assertEqual(audit["record_category_count"], 6)
        self.assertEqual(audit["record_surface_migration_count"], 9)
        self.assertEqual(audit["record_surface_component_count"], 14)
        self.assertEqual(audit["capability_count"], 3)
        self.assertEqual(audit["capability_provider_count"], 18)
        self.assertEqual(audit["capability_exception_count"], 0)
        self.assertEqual(audit["agent_mature_runtime_capability_count"], 6)
        self.assertEqual(audit["agent_delegated_decision_mechanic_count"], 5)
        self.assertEqual(audit["agent_dispatch_crossing_count"], 4)
        self.assertEqual(audit["agent_harness_semantic_count"], 10)
        self.assertEqual(audit["agent_first_task_output_count"], 5)
        self.assertEqual(
            audit["agent_first_task_evaluation_criterion_count"], 8
        )
        self.assertEqual(audit["agent_first_task_case_basis_count"], 4)
        self.assertEqual(audit["agent_authority_context_binding_count"], 3)
        self.assertTrue(audit["ok"])

    def test_current_architecture_audit_is_deterministic(self) -> None:
        self.assertEqual(audit_architecture(), audit_architecture())

    def test_canonical_plane_model_is_complete_and_horizontal_assurance_is_separate(
        self,
    ) -> None:
        matrix = load_layer_matrix()
        planes = {plane["name"]: plane for plane in matrix["plane_model"]["planes"]}
        self.assertEqual(
            set(planes),
            {
                "truth",
                "knowledge",
                "judgment",
                "control",
                "agent",
                "action-learning",
                "product",
                "assurance",
            },
        )
        self.assertEqual(
            {name: plane["depends_on"] for name, plane in planes.items()},
            {
                "truth": [],
                "knowledge": [],
                "control": ["truth"],
                "judgment": ["truth", "knowledge", "control"],
                "agent": ["truth", "knowledge", "judgment", "control"],
                "action-learning": [
                    "truth",
                    "knowledge",
                    "judgment",
                    "control",
                    "agent",
                ],
                "product": [
                    "truth",
                    "knowledge",
                    "judgment",
                    "control",
                    "agent",
                    "action-learning",
                ],
                "assurance": [],
            },
        )
        self.assertEqual(planes["assurance"]["kind"], "horizontal")
        self.assertEqual(planes["assurance"]["depends_on"], [])
        self.assertEqual(
            set(planes["assurance"]["supports"]),
            set(planes) - {"assurance"},
        )
        self.assertEqual(
            planes["truth"]["canonical_inputs"],
            [
                "external SourceArtifact records",
                "valuation inputs",
                "reconciliation artifacts and results awaiting truth admission",
            ],
        )
        self.assertIn(
            "admitted Knowledge output consumption",
            planes["truth"]["forbidden_responsibilities"],
        )
        self.assertIn(
            "admitted Truth output consumption",
            planes["knowledge"]["forbidden_responsibilities"],
        )
        self.assertIn("ReviewStateVersion", planes["judgment"]["owned_objects"])
        self.assertIn("DecisionValidity", planes["judgment"]["owned_objects"])
        self.assertIn("ProposalVersion", planes["judgment"]["owned_objects"])
        self.assertIn("PolicyVersion", planes["control"]["owned_objects"])
        self.assertEqual(
            planes["product"]["canonical_outputs"],
            ["human commands", "explanations", "presentation and session state", "navigation"],
        )

    def test_identity_namespaces_and_version_direction_are_canonical(self) -> None:
        model = load_layer_matrix()["plane_model"]["identity_model"]
        source = model["external_source_identity"]
        self.assertEqual(source["canonical_key"], ["source_namespace", "source_native_id"])
        self.assertEqual(source["shared_reference_planes"], ["truth", "knowledge"])
        self.assertEqual(
            set(source["non_authoritative_tokens"]),
            {"display_id", "request_id", "local_alias", "path"},
        )
        self.assertEqual(
            model["namespace_substitution_policy"],
            "forbidden_unless_explicitly_allowed",
        )
        self.assertEqual(model["allowed_namespace_substitutions"], [])
        nodes = {
            node["name"]: node for node in model["version_graph"]["nodes"]
        }
        self.assertEqual(
            nodes["DecisionCaseVersion"]["depends_on"],
            [
                "CapitalStateVersion",
                "EvidenceSetVersion",
                "PolicyVersion",
                "ProposalVersion",
            ],
        )
        self.assertNotIn(
            "ScenarioVersion", nodes["DecisionCaseVersion"]["depends_on"]
        )
        self.assertEqual(
            nodes["ScenarioVersion"]["depends_on"], ["DecisionCaseVersion"]
        )
        self.assertEqual(nodes["DecisionRecord"]["may_cite"], ["ScenarioVersion"])

    def _identity_model(self) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
        plane_model = copy.deepcopy(load_layer_matrix()["plane_model"])
        planes = {plane["name"]: plane for plane in plane_model["planes"]}
        return plane_model["identity_model"], planes

    def test_truth_and_knowledge_cannot_split_source_identity_authority(self) -> None:
        model, planes = self._identity_model()
        model["external_source_identity"]["shared_reference_planes"] = ["truth"]
        with self.assertRaisesRegex(ValueError, "must share one external source"):
            validate_identity_model(model, planes=planes)

    def test_non_authoritative_tokens_cannot_replace_source_or_domain_identity(
        self,
    ) -> None:
        for source, target in (
            ("agent-runtime", "principal"),
            ("request", "external-source"),
            ("display_id", "principal"),
            ("local_alias", "external-source"),
            ("path", "external-source"),
            ("content_digest", "domain-version"),
            ("git-commit", "domain-version"),
        ):
            with self.subTest(source=source, target=target):
                model, planes = self._identity_model()
                barriers = {
                    barrier["source"]: barrier
                    for barrier in model["substitution_barriers"]
                }
                barriers[source]["cannot_replace"].remove(target)
                with self.assertRaisesRegex(
                    ValueError, "substitution barriers are incomplete"
                ):
                    validate_identity_model(model, planes=planes)

    def test_identity_namespaces_are_mutually_non_substitutable(self) -> None:
        for source, target in (
            ("domain-logical", "domain-version"),
            ("domain-version", "domain-logical"),
            ("agent-runtime", "domain-logical"),
            ("agent-runtime", "domain-version"),
            ("external-source", "domain-logical"),
        ):
            with self.subTest(source=source, target=target):
                model, planes = self._identity_model()
                model["allowed_namespace_substitutions"] = [
                    {"source": source, "target": target}
                ]
                with self.assertRaisesRegex(ValueError, "mutually non-substitutable"):
                    validate_identity_model(model, planes=planes)

    def test_identity_namespace_authority_drift_is_rejected(self) -> None:
        for name, authority in (
            ("principal", "request_id"),
            ("domain-logical", "caller supplied string"),
            ("domain-version", "caller supplied UUID"),
        ):
            with self.subTest(name=name):
                model, planes = self._identity_model()
                namespaces = {
                    namespace["name"]: namespace for namespace in model["namespaces"]
                }
                namespaces[name]["authority"] = authority
                with self.assertRaisesRegex(ValueError, f"namespace {name} requires"):
                    validate_identity_model(model, planes=planes)

    def test_scenario_cannot_enter_case_identity(self) -> None:
        model, planes = self._identity_model()
        nodes = {node["name"]: node for node in model["version_graph"]["nodes"]}
        nodes["DecisionCaseVersion"]["depends_on"].append("ScenarioVersion")
        with self.assertRaisesRegex(ValueError, "version graph contains a cycle"):
            validate_identity_model(model, planes=planes)

    def test_complete_version_node_contract_is_exact(self) -> None:
        for node_name, field, value in (
            ("ReviewStateVersion", "depends_on", ["ScenarioVersion"]),
            ("DecisionRecord", "depends_on", ["ScenarioVersion"]),
            ("PolicyVersion", "depends_on", ["ProposalVersion"]),
            ("CapitalStateVersion", "identity_namespace", "domain-logical"),
        ):
            with self.subTest(node=node_name, field=field):
                model, planes = self._identity_model()
                nodes = {
                    node["name"]: node for node in model["version_graph"]["nodes"]
                }
                nodes[node_name][field] = value
                with self.assertRaisesRegex(
                    ValueError, f"node {node_name} violates canonical contract"
                ):
                    validate_identity_model(model, planes=planes)

    def test_version_graph_cycle_is_rejected(self) -> None:
        model, planes = self._identity_model()
        nodes = {node["name"]: node for node in model["version_graph"]["nodes"]}
        nodes["ProposalVersion"]["depends_on"].append("DecisionCaseVersion")
        with self.assertRaisesRegex(ValueError, "version graph contains a cycle"):
            validate_identity_model(model, planes=planes)

    def test_freshness_trigger_requires_one_canonical_owner(self) -> None:
        for mutation in ("missing", "duplicate"):
            with self.subTest(mutation=mutation):
                model, planes = self._identity_model()
                rules = model["version_graph"]["freshness_rules"]
                if mutation == "missing":
                    rules[0].pop("trigger_owner_plane")
                    message = "capital_state_admission requires trigger owner truth"
                else:
                    rules.append(copy.deepcopy(rules[0]))
                    message = "capital_state_admission has multiple owners"
                with self.assertRaisesRegex(ValueError, message):
                    validate_identity_model(model, planes=planes)

    def test_freshness_effect_redistribution_is_rejected(self) -> None:
        model, planes = self._identity_model()
        rules = {
            rule["trigger"]: rule
            for rule in model["version_graph"]["freshness_rules"]
        }
        rules["capital_state_admission"]["affects"] = ["CapitalStateVersion"]
        rules["review_event"]["affects"] = [
            "ReviewStateVersion",
            "DecisionCaseVersion",
            "ScenarioVersion",
        ]
        with self.assertRaisesRegex(ValueError, "non-canonical effects"):
            validate_identity_model(model, planes=planes)

    def test_currentness_owner_derives_from_affected_node_owner(self) -> None:
        model, planes = self._identity_model()
        model["version_graph"]["currentness_owner_semantics"] = "trigger_owner_plane"
        with self.assertRaisesRegex(ValueError, "affected node ownership"):
            validate_identity_model(model, planes=planes)

    def _record_taxonomy(self) -> dict[str, object]:
        return copy.deepcopy(load_layer_matrix()["plane_model"]["record_taxonomy"])

    def test_record_taxonomy_has_six_explicit_non_inferred_categories(self) -> None:
        taxonomy = self._record_taxonomy()
        self.assertEqual(
            taxonomy["enforcement"],
            {
                "classification": "explicit_contract_only",
                "universal_base_class": "forbidden",
                "inference_from_name_path_or_storage": "forbidden",
            },
        )
        self.assertEqual(
            {category["name"] for category in taxonomy["categories"]},
            {
                "DomainRecord",
                "OperationReceipt",
                "ArtifactProvenance",
                "AgentRunTrace",
                "BuildAttestation",
                "ProjectionIndex",
            },
        )

    def test_every_record_category_field_is_an_exact_contract(self) -> None:
        fields = (
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
        for category_name in (
            "DomainRecord",
            "OperationReceipt",
            "ArtifactProvenance",
            "AgentRunTrace",
            "BuildAttestation",
            "ProjectionIndex",
        ):
            for field in fields:
                with self.subTest(category=category_name, field=field):
                    taxonomy = self._record_taxonomy()
                    categories = {
                        category["name"]: category
                        for category in taxonomy["categories"]
                    }
                    current = categories[category_name][field]
                    categories[category_name][field] = (
                        list(reversed(current))
                        if isinstance(current, list)
                        else f"{current} drift"
                    )
                    with self.assertRaisesRegex(
                        ValueError, f"record category {category_name} violates"
                    ):
                        validate_record_taxonomy(taxonomy)

    def test_operation_receipt_cannot_grant_domain_or_decision_authority(self) -> None:
        for field in ("domain_authority_effect", "decision_validity_effect"):
            with self.subTest(field=field):
                taxonomy = self._record_taxonomy()
                categories = {
                    category["name"]: category
                    for category in taxonomy["categories"]
                }
                categories["OperationReceipt"][field] = "granted"
                with self.assertRaisesRegex(ValueError, "OperationReceipt violates"):
                    validate_record_taxonomy(taxonomy)

    def test_trace_and_build_attestation_require_domain_evidence_policy(self) -> None:
        for category_name in ("AgentRunTrace", "BuildAttestation"):
            with self.subTest(category=category_name):
                taxonomy = self._record_taxonomy()
                categories = {
                    category["name"]: category
                    for category in taxonomy["categories"]
                }
                categories[category_name]["financial_evidence_admission"] = "automatic"
                with self.assertRaisesRegex(ValueError, f"{category_name} violates"):
                    validate_record_taxonomy(taxonomy)

    def test_projection_index_must_remain_disposable_and_rebuildable(self) -> None:
        for field, value in (
            ("truth_owner", "projection database"),
            ("retention", "permanent"),
            ("reconstruction", "not rebuildable"),
            ("financial_evidence_admission", "index presence proves evidence"),
        ):
            with self.subTest(field=field):
                taxonomy = self._record_taxonomy()
                categories = {
                    category["name"]: category
                    for category in taxonomy["categories"]
                }
                categories["ProjectionIndex"][field] = value
                with self.assertRaisesRegex(ValueError, "ProjectionIndex violates"):
                    validate_record_taxonomy(taxonomy)

    # --- Migration component tests ---

    def _migration_component(
        self,
        surface: str,
        component_name: str,
    ) -> dict[str, object]:
        taxonomy = self._record_taxonomy()
        migrations = taxonomy["surface_migrations"]
        for migration in migrations:
            if migration["surface"] == surface:
                for component in migration["components"]:
                    if component["component"] == component_name:
                        return component, taxonomy  # type: ignore[return-value]
        raise AssertionError(f"component {surface}/{component_name} not found")

    def test_migration_component_single_target_category(self) -> None:
        component, taxonomy = self._migration_component(
            "statecore_receipt_backed_domain_writes", "canonical_domain_state"
        )
        component["target_category"] = ["DomainRecord", "OperationReceipt"]
        with self.assertRaisesRegex(
            ValueError, "target_category must be a single string"
        ):
            validate_record_taxonomy(taxonomy)

    def test_migration_component_exact_owner_issues(self) -> None:
        component, taxonomy = self._migration_component(
            "statecore_receipt_backed_domain_writes", "canonical_domain_state"
        )
        component["owner_issues"].remove(258)
        with self.assertRaisesRegex(
            ValueError, "migrations are incomplete"
        ):
            validate_record_taxonomy(taxonomy)

    def test_migration_component_no_spurious_owner_issue(self) -> None:
        component, taxonomy = self._migration_component(
            "statecore_receipt_backed_domain_writes", "canonical_domain_state"
        )
        component["owner_issues"].append(395)
        with self.assertRaisesRegex(
            ValueError, "migrations are incomplete"
        ):
            validate_record_taxonomy(taxonomy)

    def test_parent_owner_pool_is_rejected(self) -> None:
        taxonomy = self._record_taxonomy()
        migrations = taxonomy["surface_migrations"]
        # Add owner_issues directly to a surface entry — must fail with unknown field
        for migration in migrations:
            if migration["surface"] == "statecore_receipt_backed_domain_writes":
                migration["owner_issues"] = [999]
                break
        with self.assertRaisesRegex(
            ValueError, "surface migration fields violate canonical contract"
        ):
            validate_record_taxonomy(taxonomy)

    def test_current_conformance_separate_from_target_conforming_rejected(self) -> None:
        component, taxonomy = self._migration_component(
            "commit_identity_manifest_and_ci_artifacts",
            "commit_identity_verification_manifest",
        )
        component["current_conformance"] = "conforming"
        with self.assertRaisesRegex(
            ValueError, "migrations are incomplete"
        ):
            validate_record_taxonomy(taxonomy)

    def test_prerequisite_386_cannot_be_removed(self) -> None:
        component, taxonomy = self._migration_component(
            "commit_identity_manifest_and_ci_artifacts",
            "commit_identity_verification_manifest",
        )
        component["completed_prerequisites"] = []
        with self.assertRaisesRegex(
            ValueError, "migrations are incomplete"
        ):
            validate_record_taxonomy(taxonomy)

    def test_386_is_prerequisite_not_remaining_migration_owner(self) -> None:
        component, taxonomy = self._migration_component(
            "commit_identity_manifest_and_ci_artifacts",
            "commit_identity_verification_manifest",
        )
        component["completed_prerequisites"] = []
        component["owner_issues"] = [379, 386]
        with self.assertRaisesRegex(
            ValueError, "migrations are incomplete"
        ):
            validate_record_taxonomy(taxonomy)

    def test_commit_identity_not_domain_record(self) -> None:
        component, taxonomy = self._migration_component(
            "commit_identity_manifest_and_ci_artifacts",
            "commit_identity_verification_manifest",
        )
        component["target_category"] = "DomainRecord"
        with self.assertRaisesRegex(
            ValueError, "migrations are incomplete"
        ):
            validate_record_taxonomy(taxonomy)

    def test_disposition_cannot_claim_authenticated_build_attestation(self) -> None:
        component, taxonomy = self._migration_component(
            "commit_identity_manifest_and_ci_artifacts",
            "commit_identity_verification_manifest",
        )
        component["disposition"] = (
            "current manifest is already an authenticated BuildAttestation"
        )
        with self.assertRaisesRegex(
            ValueError, "migrations are incomplete"
        ):
            validate_record_taxonomy(taxonomy)

    # --- AgentRunTrace canonical trace tests ---

    def test_agent_trace_otel_exporter_not_authoritative(self) -> None:
        taxonomy = self._record_taxonomy()
        categories = {c["name"]: c for c in taxonomy["categories"]}
        categories["AgentRunTrace"]["authoritative_source"] = "OpenTelemetry exporter"
        with self.assertRaisesRegex(ValueError, "AgentRunTrace violates"):
            validate_record_taxonomy(taxonomy)

    def test_agent_trace_sampled_telemetry_not_reconstruction(self) -> None:
        taxonomy = self._record_taxonomy()
        categories = {c["name"]: c for c in taxonomy["categories"]}
        categories["AgentRunTrace"]["reconstruction"] = "sampled telemetry"
        with self.assertRaisesRegex(ValueError, "AgentRunTrace violates"):
            validate_record_taxonomy(taxonomy)

    def test_agent_trace_domain_authority_not_granted(self) -> None:
        taxonomy = self._record_taxonomy()
        categories = {c["name"]: c for c in taxonomy["categories"]}
        categories["AgentRunTrace"]["domain_authority_effect"] = "granted"
        with self.assertRaisesRegex(ValueError, "AgentRunTrace violates"):
            validate_record_taxonomy(taxonomy)

    # --- OTel observability export contract tests ---

    def test_otel_export_authority_not_authoritative(self) -> None:
        taxonomy = self._record_taxonomy()
        taxonomy["agent_trace_observability_export"]["authority"] = "authoritative"
        with self.assertRaisesRegex(
            ValueError, "agent_trace_observability_export.authority"
        ):
            validate_record_taxonomy(taxonomy)

    def test_otel_export_sampling_not_canonical_trace(self) -> None:
        taxonomy = self._record_taxonomy()
        taxonomy["agent_trace_observability_export"]["sampling"] = (
            "canonical trace may be sampled"
        )
        with self.assertRaisesRegex(
            ValueError, "agent_trace_observability_export.sampling"
        ):
            validate_record_taxonomy(taxonomy)

    def test_otel_export_cannot_satisfy_restart_hydration(self) -> None:
        taxonomy = self._record_taxonomy()
        cannot = taxonomy["agent_trace_observability_export"]["cannot_satisfy"]
        cannot.remove("restart hydration")
        with self.assertRaisesRegex(
            ValueError, "agent_trace_observability_export.cannot_satisfy"
        ):
            validate_record_taxonomy(taxonomy)

    def test_otel_export_cannot_satisfy_canonical_trace_completeness(self) -> None:
        taxonomy = self._record_taxonomy()
        cannot = taxonomy["agent_trace_observability_export"]["cannot_satisfy"]
        cannot.remove("canonical trace completeness")
        with self.assertRaisesRegex(
            ValueError, "agent_trace_observability_export.cannot_satisfy"
        ):
            validate_record_taxonomy(taxonomy)

    # --- Unknown field and category guard tests ---

    def test_record_taxonomy_unknown_top_level_field_is_rejected(self) -> None:
        for field in (
            "runtime_classifier",
            "universal_record_base",
            "second_registry",
            "retention_engine",
        ):
            with self.subTest(field=field):
                taxonomy = self._record_taxonomy()
                taxonomy[field] = "forbidden parallel mechanism"
                with self.assertRaisesRegex(
                    ValueError,
                    "top-level fields violate canonical contract",
                ):
                    validate_record_taxonomy(taxonomy)

    def test_migration_component_unknown_field_rejected(self) -> None:
        component, taxonomy = self._migration_component(
            "statecore_receipt_backed_domain_writes", "canonical_domain_state"
        )
        component["runtime_classifier"] = "suffix_based"
        with self.assertRaisesRegex(
            ValueError, "component fields violate canonical contract"
        ):
            validate_record_taxonomy(taxonomy)

    def test_migration_component_unknown_category_rejected(self) -> None:
        component, taxonomy = self._migration_component(
            "statecore_receipt_backed_domain_writes", "canonical_domain_state"
        )
        component["target_category"] = "GenericReceipt"
        with self.assertRaisesRegex(ValueError, "unknown target_category"):
            validate_record_taxonomy(taxonomy)

    def test_build_attestation_not_automatic_financial_evidence(self) -> None:
        taxonomy = self._record_taxonomy()
        categories = {c["name"]: c for c in taxonomy["categories"]}
        categories["BuildAttestation"]["financial_evidence_admission"] = "automatic"
        with self.assertRaisesRegex(ValueError, "BuildAttestation violates"):
            validate_record_taxonomy(taxonomy)

    def test_universal_base_or_inferred_category_enforcement_is_rejected(self) -> None:
        for field, value in (
            ("universal_base_class", "required"),
            ("inference_from_name_path_or_storage", "allowed"),
        ):
            with self.subTest(field=field):
                taxonomy = self._record_taxonomy()
                taxonomy["enforcement"][field] = value
                with self.assertRaisesRegex(ValueError, "forbids universal bases"):
                    validate_record_taxonomy(taxonomy)

    def _agent_harness_boundary(self) -> dict[str, object]:
        return copy.deepcopy(
            load_layer_matrix()["plane_model"]["agent_harness_boundary"]
        )

    def test_agent_harness_unknown_top_level_fields_are_rejected(self) -> None:
        for field in ("runtime_registry", "second_loop", "memory_platform"):
            with self.subTest(field=field):
                boundary = self._agent_harness_boundary()
                boundary[field] = "parallel mechanism"
                with self.assertRaisesRegex(ValueError, "top-level fields"):
                    validate_agent_harness_boundary(boundary)

    def test_agent_harness_primary_selection_point_is_exact(self) -> None:
        for field, value in (
            ("selection_point", "ProviderRunner"),
            ("selection_issue", 405),
            ("adapter_mode", "full_agent_runner"),
            ("decision_cardinality", "many actions until final output"),
            ("harness_loop_owner", "OpenAI Agents SDK Runner"),
            ("parallel_core_loops", "allowed"),
            ("sdk_runner_loop_on_primary_path", "allowed"),
            ("runtime_internal_tool_execution", "allowed"),
            ("runtime_internal_handoffs", "allowed terminal transition"),
            ("provider_dependency", "frozen_now"),
            ("tool_calls_return_as", "provider FunctionTool result"),
        ):
            with self.subTest(field=field):
                boundary = self._agent_harness_boundary()
                boundary["primary_runtime_path"][field] = value
                with self.assertRaisesRegex(ValueError, "violates canonical contract"):
                    validate_agent_harness_boundary(boundary)

    def test_every_tool_dispatch_must_cross_the_complete_harness_boundary(self) -> None:
        for crossing in (
            "Harness autonomy admission",
            "Harness tool and capability admission",
            "Harness work budgets",
            "canonical Observation reduction",
        ):
            with self.subTest(crossing=crossing):
                boundary = self._agent_harness_boundary()
                boundary["primary_runtime_path"][
                    "all_tool_dispatch_must_cross"
                ].remove(crossing)
                with self.assertRaisesRegex(ValueError, "violates canonical contract"):
                    validate_agent_harness_boundary(boundary)

    def test_provider_runtime_cannot_own_domain_semantics(self) -> None:
        for responsibility in (
            "CapitalState meaning",
            "evidence admission",
            "authority policy",
            "canonical AgentRunTrace",
        ):
            with self.subTest(responsibility=responsibility):
                boundary = self._agent_harness_boundary()
                boundary["delegated_behind_current_decision_port"].append(
                    responsibility
                )
                with self.assertRaisesRegex(ValueError, "violates canonical contract"):
                    validate_agent_harness_boundary(boundary)

    def test_mature_capability_does_not_imply_current_port_delegation(self) -> None:
        for capability in ("model turn loop", "tool execution", "handoffs"):
            with self.subTest(capability=capability):
                boundary = self._agent_harness_boundary()
                boundary["delegated_behind_current_decision_port"].append(capability)
                with self.assertRaisesRegex(ValueError, "violates canonical contract"):
                    validate_agent_harness_boundary(boundary)

    def test_provider_state_is_non_authoritative_but_resume_aware(self) -> None:
        for path, value in (
            (("authority",), "domain authority"),
            (("durability",), ["always disposable cache"]),
            (("retention", "may_prune_after"), ["at any time"]),
        ):
            with self.subTest(path=path):
                boundary = self._agent_harness_boundary()
                target = boundary["provider_state"]
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                with self.assertRaisesRegex(ValueError, "violates canonical contract"):
                    validate_agent_harness_boundary(boundary)

    def test_provider_state_cannot_replace_world_versions_or_trace(self) -> None:
        for protected in (
            "ContextWorld",
            "CapitalStateVersion",
            "DecisionCaseVersion",
            "EvidenceSetVersion",
            "PolicyVersion",
            "AgentRunTrace",
            "DomainRecord",
        ):
            with self.subTest(protected=protected):
                boundary = self._agent_harness_boundary()
                boundary["provider_state"]["cannot_replace"].remove(protected)
                with self.assertRaisesRegex(ValueError, "violates canonical contract"):
                    validate_agent_harness_boundary(boundary)

    def test_mcp_transport_authentication_and_oauth_remain_protocol_mechanics(
        self,
    ) -> None:
        for mechanic in (
            "transport authentication",
            "OAuth token and scope mechanics",
            "resource-server access decision",
        ):
            with self.subTest(mechanic=mechanic):
                boundary = self._agent_harness_boundary()
                boundary["mcp_boundary"]["may_own"].remove(mechanic)
                with self.assertRaisesRegex(ValueError, "violates canonical contract"):
                    validate_agent_harness_boundary(boundary)

    def test_mcp_transport_authorization_cannot_replace_finharness_authority(
        self,
    ) -> None:
        for protected in (
            "principal identity",
            "mandate",
            "grant",
            "tool admission",
            "evidence admission",
            "execution authority",
        ):
            with self.subTest(protected=protected):
                boundary = self._agent_harness_boundary()
                boundary["mcp_boundary"][
                    "transport_authorization_cannot_substitute_for"
                ].remove(protected)
                with self.assertRaisesRegex(ValueError, "violates canonical contract"):
                    validate_agent_harness_boundary(boundary)

    def test_mcp_cannot_own_finharness_admission_or_domain_state(self) -> None:
        boundary = self._agent_harness_boundary()
        boundary["mcp_boundary"]["may_own"].append("tool visibility and admission")
        with self.assertRaisesRegex(ValueError, "violates canonical contract"):
            validate_agent_harness_boundary(boundary)

    def test_workflow_engine_cannot_own_domain_policy_or_default_core(self) -> None:
        for field, value in (
            ("cannot_own", ["execution permission"]),
            ("default_core_dependency", "required"),
            ("activation", "future flexibility"),
        ):
            with self.subTest(field=field):
                boundary = self._agent_harness_boundary()
                boundary["workflow_engine_boundary"][field] = value
                with self.assertRaisesRegex(ValueError, "violates canonical contract"):
                    validate_agent_harness_boundary(boundary)

    def test_model_output_remains_candidate_and_non_executing(self) -> None:
        for field, value in (
            ("classification", "authoritative decision"),
            ("execution_allowed", True),
            ("allowed_outputs", ["execution order"]),
        ):
            with self.subTest(field=field):
                boundary = self._agent_harness_boundary()
                boundary["model_output"][field] = value
                with self.assertRaisesRegex(ValueError, "violates canonical contract"):
                    validate_agent_harness_boundary(boundary)

    def test_first_task_requires_server_resolved_world_and_exact_case_basis(
        self,
    ) -> None:
        for path, value in (
            (("input_root", "caller_supplied_world_refs"), "allowed"),
            (("exact_case", "basis_match"), "optional"),
            (("mixed_basis",), "allowed"),
            (("freshness_without_basis_match",), "sufficient"),
            (
                ("basis_resolution", "independent_latest_or_current_selection"),
                "allowed",
            ),
        ):
            with self.subTest(path=path):
                boundary = self._agent_harness_boundary()
                task = boundary["first_evaluation_task"]
                target = task
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                with self.assertRaisesRegex(ValueError, "violates canonical contract"):
                    validate_agent_harness_boundary(boundary)

    def test_first_task_requires_complete_decision_case_basis(self) -> None:
        for version in (
            "CapitalStateVersion",
            "EvidenceSetVersion",
            "PolicyVersion",
            "ProposalVersion",
        ):
            with self.subTest(version=version):
                boundary = self._agent_harness_boundary()
                boundary["first_evaluation_task"]["required_case_basis"].remove(
                    version
                )
                with self.assertRaisesRegex(ValueError, "violates canonical contract"):
                    validate_agent_harness_boundary(boundary)

    def test_first_task_authority_context_comes_from_exact_world(self) -> None:
        for mutation in ("wrong_source", "missing_mandate", "missing_grant"):
            with self.subTest(mutation=mutation):
                boundary = self._agent_harness_boundary()
                authority = boundary["first_evaluation_task"]["authority_context"]
                if mutation == "wrong_source":
                    authority["source"] = "MCP OAuth token"
                elif mutation == "missing_mandate":
                    authority["includes"].remove("CapitalMandateVersion")
                else:
                    authority["includes"].remove("AgentAuthorityGrantVersion")
                with self.assertRaisesRegex(ValueError, "violates canonical contract"):
                    validate_agent_harness_boundary(boundary)

    def test_first_task_maturity_and_owners_are_explicit(self) -> None:
        for field, value in (
            ("implementation_state", "conforming"),
            ("implementation_owner_issue", 405),
            ("prerequisite_issues", [284]),
        ):
            with self.subTest(field=field):
                boundary = self._agent_harness_boundary()
                boundary["first_evaluation_task"][field] = value
                with self.assertRaisesRegex(ValueError, "violates canonical contract"):
                    validate_agent_harness_boundary(boundary)

    def test_first_task_cannot_mutate_or_authorize_execution(self) -> None:
        for field, value in (
            ("direct_domain_mutation", "allowed"),
            ("execution_allowed", True),
            ("allowed_outputs", ["broker order"]),
        ):
            with self.subTest(field=field):
                boundary = self._agent_harness_boundary()
                boundary["first_evaluation_task"][field] = value
                with self.assertRaisesRegex(ValueError, "violates canonical contract"):
                    validate_agent_harness_boundary(boundary)

    def test_first_task_requires_complete_evaluation_contract(self) -> None:
        boundary = self._agent_harness_boundary()
        boundary["first_evaluation_task"]["evaluation_criteria"].remove(
            "exact world and domain-version freshness"
        )
        with self.assertRaisesRegex(ValueError, "violates canonical contract"):
            validate_agent_harness_boundary(boundary)

    def test_reverse_plane_dependency_is_rejected(self) -> None:
        model = copy.deepcopy(load_layer_matrix()["plane_model"])
        planes = {plane["name"]: plane for plane in model["planes"]}
        planes["truth"]["depends_on"] = ["product"]
        with self.assertRaisesRegex(ValueError, "reverse dependency truth -> product"):
            validate_plane_model(model)

    def test_equal_rank_plane_dependency_is_rejected(self) -> None:
        model = copy.deepcopy(load_layer_matrix()["plane_model"])
        planes = {plane["name"]: plane for plane in model["planes"]}
        planes["truth"]["depends_on"] = ["knowledge"]
        with self.assertRaisesRegex(ValueError, "reverse dependency truth -> knowledge"):
            validate_plane_model(model)

    def test_assurance_dependency_on_domain_plane_is_rejected(self) -> None:
        model = copy.deepcopy(load_layer_matrix()["plane_model"])
        planes = {plane["name"]: plane for plane in model["planes"]}
        planes["assurance"]["depends_on"] = ["truth"]
        with self.assertRaisesRegex(ValueError, "horizontal plane assurance cannot join"):
            validate_plane_model(model)

    def test_assurance_support_must_be_complete_and_unique(self) -> None:
        for mutation in ("missing", "duplicate"):
            with self.subTest(mutation=mutation):
                model = copy.deepcopy(load_layer_matrix()["plane_model"])
                planes = {plane["name"]: plane for plane in model["planes"]}
                if mutation == "missing":
                    planes["assurance"]["supports"].remove("product")
                else:
                    planes["assurance"]["supports"].append("truth")
                with self.assertRaisesRegex(
                    ValueError, "assurance must support every domain plane exactly once"
                ):
                    validate_plane_model(model)

    def test_duplicate_plane_ownership_is_rejected(self) -> None:
        model = copy.deepcopy(load_layer_matrix()["plane_model"])
        planes = {plane["name"]: plane for plane in model["planes"]}
        planes["knowledge"]["owned_objects"].append("CapitalStateVersion")
        with self.assertRaisesRegex(
            ValueError,
            "owned object CapitalStateVersion has multiple planes: truth, knowledge",
        ):
            validate_plane_model(model)

    def test_plane_vocabulary_is_shared_by_current_architecture_docs(self) -> None:
        paths = (
            "docs/adr/2026-07-16-finharness-plane-model-and-dependency-direction.md",
            "docs/architecture/capital-os-layering.md",
            "docs/architecture/module-map.md",
            "docs/architecture/finharness-evolution-roadmap.md",
        )
        for relative in paths:
            with self.subTest(path=relative):
                text = (Path(__file__).resolve().parents[1] / relative).read_text(
                    encoding="utf-8"
                )
                self.assertIn("Canonical plane model", text)
                self.assertIn("Truth", text)
                self.assertIn("Knowledge", text)
                self.assertIn("Judgment", text)
                self.assertIn("Control", text)
                self.assertIn("Agent", text)
                self.assertIn("Action/Learning", text)
                self.assertIn("Product", text)
                self.assertIn("Assurance", text)

    def test_capability_exception_source_must_belong_to_the_rule_layer(self) -> None:
        def add_wrong_layer_exception(matrix: dict[str, Any]) -> None:
            matrix["capability_exceptions"] = [
                {
                    "source_module": "finharness.neutral_helper",
                    "rule_id": "agent-does-not-bypass-execution-commands",
                    "capability_id": "execution.broker_registry_resolution",
                    "path": [
                        "finharness.neutral_helper",
                        "finharness.execution.broker",
                    ],
                    "reason": "Bounded compatibility path pending removal.",
                    "owner_issue": 369,
                    "review_gate": "Remove after compatibility path migration.",
                }
            ]

        temp, root = self._capability_repo(
            {
                "src/finharness/neutral_helper.py": (
                    "import finharness.execution.broker\n"
                )
            },
            mutate=add_wrong_layer_exception,
        )
        self.addCleanup(temp.cleanup)
        with self.assertRaisesRegex(ValueError, "outside rule"):
            audit_architecture(root=root, matrix_path=root / "matrix.yml")


if __name__ == "__main__":
    unittest.main()
