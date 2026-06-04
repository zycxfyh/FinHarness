"""Generate FinHarness local SBOM and provenance baseline artifacts.

This intentionally avoids adding a new dependency. The output is a local
baseline for release governance, not a formal CycloneDX/SPDX attestation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SBOM = ROOT / "data" / "security" / "sbom" / "finharness-sbom.json"
DEFAULT_PROVENANCE = (
    ROOT / "data" / "security" / "provenance" / "finharness-provenance-baseline.json"
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repo_path(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def component_ref(ecosystem: str, name: str, version: str) -> str:
    return f"{ecosystem}:{name}@{version}"


def component(
    *,
    ecosystem: str,
    name: str,
    version: str,
    source_file: str,
    scope: str = "locked",
    package_type: str = "library",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "bom_ref": component_ref(ecosystem, name, version),
        "type": package_type,
        "ecosystem": ecosystem,
        "name": name,
        "version": version,
        "scope": scope,
        "source_file": source_file,
    }
    if extra:
        payload.update(extra)
    return payload


def python_components(root: Path = ROOT) -> list[dict[str, Any]]:
    lock_path = root / "uv.lock"
    if not lock_path.exists():
        return []
    lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    components = []
    for package in lock.get("package", []):
        name = str(package["name"])
        version = str(package.get("version", "unknown"))
        hashes = []
        for wheel in package.get("wheels", []) or []:
            if isinstance(wheel, dict) and wheel.get("hash"):
                hashes.append(str(wheel["hash"]))
        sdist = package.get("sdist")
        if isinstance(sdist, dict) and sdist.get("hash"):
            hashes.append(str(sdist["hash"]))
        components.append(
            component(
                ecosystem="pypi",
                name=name,
                version=version,
                source_file="uv.lock",
                extra={"hashes": sorted(set(hashes))},
            )
        )
    return components


def _parse_pnpm_package_key(key: str) -> tuple[str, str] | None:
    text = key.strip("/")
    if not text:
        return None
    first = text.split("/", 1)[0]
    if first.startswith("@"):
        match = re.match(r"(?P<scope>@[^+]+)\+(?P<name>[^@]+)@(?P<version>[^_]+)", first)
        if not match:
            return None
        return f"{match.group('scope')}/{match.group('name')}", match.group("version")
    if "@" not in first:
        return None
    name, version = first.rsplit("@", 1)
    if not name or not version:
        return None
    return name, version


def npm_components(root: Path = ROOT) -> list[dict[str, Any]]:
    lock_path = root / "pnpm-lock.yaml"
    if not lock_path.exists():
        return []
    lock = yaml.safe_load(lock_path.read_text(encoding="utf-8")) or {}
    packages = lock.get("packages") or {}
    components = []
    for key in sorted(packages):
        parsed = _parse_pnpm_package_key(str(key))
        if not parsed:
            continue
        name, version = parsed
        components.append(
            component(
                ecosystem="npm",
                name=name,
                version=version,
                source_file="pnpm-lock.yaml",
            )
        )
    return components


def rust_components(root: Path = ROOT) -> list[dict[str, Any]]:
    lock_path = root / "Cargo.lock"
    if not lock_path.exists():
        return []
    lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    components = []
    for package in lock.get("package", []):
        components.append(
            component(
                ecosystem="cargo",
                name=str(package["name"]),
                version=str(package.get("version", "unknown")),
                source_file="Cargo.lock",
                extra={"checksum": package.get("checksum")},
            )
        )
    return components


def manifest_components(root: Path = ROOT) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        project = data.get("project", {})
        items.append(
            component(
                ecosystem="local",
                name=str(project.get("name", "finharness")),
                version=str(project.get("version", "0.0.0")),
                source_file="pyproject.toml",
                scope="root",
                package_type="application",
                extra={"license": project.get("license")},
            )
        )
    package_json = root / "package.json"
    if package_json.exists():
        data = json.loads(package_json.read_text(encoding="utf-8"))
        items.append(
            component(
                ecosystem="local",
                name=str(data.get("name", "finharness-js-tools")),
                version=str(data.get("version", "0.0.0")),
                source_file="package.json",
                scope="root",
                package_type="application",
                extra={"license": data.get("license")},
            )
        )
    cargo_toml = root / "crates" / "finharness-cli" / "Cargo.toml"
    if cargo_toml.exists():
        data = tomllib.loads(cargo_toml.read_text(encoding="utf-8"))
        package = data.get("package", {})
        items.append(
            component(
                ecosystem="local",
                name=str(package.get("name", "finharness-cli")),
                version=str(package.get("version", "0.0.0")),
                source_file="crates/finharness-cli/Cargo.toml",
                scope="root",
                package_type="application",
                extra={"license": package.get("license")},
            )
        )
    return items


def build_sbom(root: Path = ROOT) -> dict[str, Any]:
    generated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    components = [
        *manifest_components(root),
        *python_components(root),
        *npm_components(root),
        *rust_components(root),
    ]
    unique = {item["bom_ref"]: item for item in components}
    ordered = sorted(unique.values(), key=lambda item: item["bom_ref"])
    counts: dict[str, int] = {}
    for item in ordered:
        counts[item["ecosystem"]] = counts.get(item["ecosystem"], 0) + 1
    return {
        "schema": "finharness.local_sbom.v1",
        "generated_at": generated_at,
        "git_head": git_head(),
        "tool": "scripts/generate_security_sbom.py",
        "formal_standard": "local_baseline_not_cyclonedx_or_spdx",
        "component_count": len(ordered),
        "component_counts_by_ecosystem": counts,
        "source_files": [
            "pyproject.toml",
            "uv.lock",
            "package.json",
            "pnpm-lock.yaml",
            "Cargo.lock",
            "crates/finharness-cli/Cargo.toml",
        ],
        "components": ordered,
        "execution_allowed": False,
    }


def build_provenance_baseline(sbom: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    source_files = [root / item for item in sbom["source_files"] if (root / item).exists()]
    return {
        "schema": "finharness.provenance_baseline.v1",
        "generated_at": sbom["generated_at"],
        "git_head": sbom["git_head"],
        "subject": {
            "name": "FinHarness source dependency baseline",
            "sbom_ref": repo_path(DEFAULT_SBOM),
            "component_count": sbom["component_count"],
        },
        "materials": [
            {
                "path": repo_path(path),
                "sha256": sha256_file(path),
            }
            for path in source_files
        ],
        "builder": {
            "type": "local_task",
            "task": "task security:sbom",
            "script": "scripts/generate_security_sbom.py",
        },
        "slsa_status": "planning_baseline_not_attestation",
        "non_claims": [
            "Not a signed SLSA provenance statement.",
            "Not a complete runtime artifact attestation.",
            "Does not authorize live trading.",
        ],
        "execution_allowed": False,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sbom-output", type=Path, default=DEFAULT_SBOM)
    parser.add_argument("--provenance-output", type=Path, default=DEFAULT_PROVENANCE)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sbom = build_sbom()
    provenance = build_provenance_baseline(sbom)
    write_json(args.sbom_output, sbom)
    write_json(args.provenance_output, provenance)
    print(
        json.dumps(
            {
                "sbom_ref": repo_path(args.sbom_output),
                "provenance_ref": repo_path(args.provenance_output),
                "component_count": sbom["component_count"],
                "component_counts_by_ecosystem": sbom["component_counts_by_ecosystem"],
                "execution_allowed": False,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
