from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from finharness.architecture_boundaries import (
    audit_architecture,
    build_canonical_import_graph,
    load_layer_matrix,
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


class ArchitectureBoundaryTest(unittest.TestCase):
    def _repo(self, files: dict[str, str]) -> tuple[tempfile.TemporaryDirectory, Path]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        for relative, content in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        (root / "matrix.yml").write_text(MATRIX, encoding="utf-8")
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
        self.assertTrue(audit["ok"])

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


if __name__ == "__main__":
    unittest.main()
