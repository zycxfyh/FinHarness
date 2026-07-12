"""Contract tests for the dependency-consumer audit artifact.

This test intentionally validates an audit artifact, not debt closure. Moving
requirements between groups and changing ENG-DEBT-0005 remain later decisions.
"""

from __future__ import annotations

import ast
import json
import re
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
TASKFILE = ROOT / "Taskfile.yml"
MANIFEST = ROOT / "docs" / "governance" / "dependency-consumers.json"

EXPECTED_TOP_LEVEL_KEYS = {
    "schema",
    "status",
    "debt_ref",
    "source_roots",
    "entries",
}
EXPECTED_ENTRY_KEYS = {
    "distribution",
    "requirement",
    "declared_group",
    "recommended_group",
    "import_modules",
    "import_consumers",
    "task_consumers",
    "rationale",
    "confidence",
}
ALLOWED_RECOMMENDATIONS = {
    "base",
    "dev",
    "data",
    "research",
    "agent",
    "eval",
    "paper",
    "security",
    "unused",
}
ALLOWED_CONFIDENCE = {"high", "medium", "low"}
AUDITED_PYTHON_ROOTS = {"src", "scripts", "tests", "experiments"}
IMPORT_TO_DISTRIBUTION = {
    "agents": "openai-agents",
    "backtrader": "backtrader",
    "beancount": "beancount",
    "beanquery": "beanquery",
    "deepeval": "deepeval",
    "fastapi": "fastapi",
    "httpx": "httpx",
    "keyring": "keyring",
    "langgraph": "langgraph",
    "nautilus_trader": "nautilus-trader",
    "pandas": "pandas",
    "pandera": "pandera",
    "pydantic_settings": "pydantic-settings",
    "pytest": "pytest",
    "quantstats": "quantstats",
    "riskfolio": "riskfolio-lib",
    "scipy": "scipy",
    "sqlmodel": "sqlmodel",
    "structlog": "structlog",
    "uvicorn": "uvicorn",
    "uuid6": "uuid6",
    "vectorbt": "vectorbt",
    "yfinance": "yfinance",
}


def _distribution_name(requirement: str) -> str:
    match = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", requirement)
    if match is None:
        raise AssertionError(f"cannot parse requirement: {requirement}")
    return re.sub(r"[-_.]+", "-", match.group(1)).lower()


def _declared_requirements() -> dict[str, tuple[str, str]]:
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    result: dict[str, tuple[str, str]] = {}
    for requirement in project["project"]["dependencies"]:
        result[_distribution_name(requirement)] = (requirement, "base")
    for group, requirements in project.get("dependency-groups", {}).items():
        for requirement in requirements:
            name = _distribution_name(requirement)
            if name in result:
                raise AssertionError(f"duplicate declared dependency: {name}")
            result[name] = (requirement, group)
    return result


def _task_names() -> set[str]:
    text = TASKFILE.read_text(encoding="utf-8")
    return set(re.findall(r"^  ([A-Za-z0-9:_-]+):\s*$", text, re.MULTILINE))


def _observed_imports() -> dict[str, tuple[set[str], set[str]]]:
    observed: dict[str, tuple[set[str], set[str]]] = {
        name: (set(), set()) for name in _declared_requirements()
    }
    for root_name in AUDITED_PYTHON_ROOTS:
        for path in (ROOT / root_name).rglob("*.py"):
            if "archive" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                modules: list[str] = []
                if isinstance(node, ast.Import):
                    modules.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules.append(node.module)
                for module in modules:
                    top_level = module.split(".", maxsplit=1)[0]
                    if module.startswith("opentelemetry.sdk"):
                        distribution = "opentelemetry-sdk"
                    elif module.startswith("opentelemetry"):
                        distribution = "opentelemetry-api"
                    else:
                        distribution = IMPORT_TO_DISTRIBUTION.get(top_level)
                    if distribution not in observed:
                        continue
                    import_modules, consumer_paths = observed[distribution]
                    import_modules.add(top_level)
                    consumer_paths.add(path.relative_to(ROOT).as_posix())
    return observed


class DependencyConsumerManifestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(MANIFEST.exists(), f"missing dependency audit: {MANIFEST}")
        self.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_manifest_identity_is_an_audit_not_a_resolution_claim(self) -> None:
        self.assertEqual(set(self.manifest), EXPECTED_TOP_LEVEL_KEYS)
        self.assertEqual(
            self.manifest["schema"],
            "finharness.dependency_consumer_manifest.v1",
        )
        self.assertEqual(self.manifest["status"], "current")
        self.assertEqual(self.manifest["debt_ref"], "ENG-DEBT-0005")
        self.assertEqual(
            set(self.manifest["source_roots"]),
            {"pyproject.toml", "Taskfile.yml", *AUDITED_PYTHON_ROOTS},
        )

    def test_every_direct_requirement_has_exactly_one_entry(self) -> None:
        declared = _declared_requirements()
        entries = self.manifest["entries"]
        self.assertIsInstance(entries, list)
        by_name = {entry["distribution"]: entry for entry in entries}
        self.assertEqual(len(by_name), len(entries), "duplicate manifest distribution")
        self.assertEqual(set(by_name), set(declared))
        for name, (requirement, group) in declared.items():
            with self.subTest(distribution=name):
                entry = by_name[name]
                self.assertEqual(set(entry), EXPECTED_ENTRY_KEYS)
                self.assertEqual(entry["requirement"], requirement)
                self.assertEqual(entry["declared_group"], group)

    def test_consumer_evidence_is_bounded_and_resolvable(self) -> None:
        task_names = _task_names()
        observed_imports = _observed_imports()
        for entry in self.manifest["entries"]:
            with self.subTest(distribution=entry["distribution"]):
                self.assertIn(entry["recommended_group"], ALLOWED_RECOMMENDATIONS)
                self.assertIn(entry["confidence"], ALLOWED_CONFIDENCE)
                self.assertTrue(entry["rationale"].strip())
                for field in ("import_modules", "import_consumers", "task_consumers"):
                    self.assertIsInstance(entry[field], list)
                    self.assertEqual(len(entry[field]), len(set(entry[field])))
                for module in entry["import_modules"]:
                    self.assertRegex(module, r"^[A-Za-z_][A-Za-z0-9_]*$")
                for consumer in entry["import_consumers"]:
                    path = Path(consumer)
                    self.assertFalse(path.is_absolute())
                    self.assertIn(path.parts[0], AUDITED_PYTHON_ROOTS)
                    self.assertEqual(path.suffix, ".py")
                    self.assertTrue((ROOT / path).is_file(), f"missing consumer: {consumer}")
                for task in entry["task_consumers"]:
                    self.assertIn(task, task_names, f"unknown Taskfile task: {task}")
                expected_modules, expected_consumers = observed_imports[entry["distribution"]]
                self.assertEqual(set(entry["import_modules"]), expected_modules)
                self.assertEqual(set(entry["import_consumers"]), expected_consumers)
                if entry["recommended_group"] == "unused":
                    self.assertEqual(entry["import_consumers"], [])
                    self.assertEqual(entry["task_consumers"], [])
                else:
                    self.assertTrue(
                        entry["import_consumers"] or entry["task_consumers"],
                        "a kept dependency needs an observed consumer",
                    )


if __name__ == "__main__":
    unittest.main()
