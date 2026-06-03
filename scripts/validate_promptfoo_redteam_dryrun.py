"""Validate the FinHarness promptfoo redteam dry-run contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from finharness.market_data import ROOT

FORBIDDEN_TARGET_TOKENS = ("openai:", "anthropic:", "http", "alpaca", "okx", "live")
REQUIRED_METADATA_FALSE = (
    "execution_allowed",
    "live_trading_allowed",
    "secrets_required",
    "dynamic_redteam_executed",
)


def load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("promptfoo redteam dry-run config must be a mapping")
    return payload


def validate_config(payload: dict[str, Any]) -> dict[str, Any]:
    findings: list[str] = []
    targets = payload.get("targets") or []
    if not targets:
        findings.append("missing targets")
    for target in targets:
        target_id = str(target.get("id") if isinstance(target, dict) else target).lower()
        if target_id != "echo":
            findings.append(f"target must be echo, got {target_id}")
        if any(token in target_id for token in FORBIDDEN_TARGET_TOKENS):
            findings.append(f"forbidden target token in {target_id}")

    redteam = payload.get("redteam") or {}
    if not isinstance(redteam, dict):
        findings.append("redteam section must be a mapping")
        redteam = {}
    purpose = str(redteam.get("purpose", "")).lower()
    for phrase in (
        "must not",
        "live trading",
        "secret",
        "guaranteed investment",
    ):
        if phrase not in purpose:
            findings.append(f"purpose missing boundary phrase: {phrase}")
    if int(redteam.get("numTests", 0)) != 1:
        findings.append("numTests must be 1 for dry-run contract")
    if int(redteam.get("maxConcurrency", 0)) != 1:
        findings.append("maxConcurrency must be 1 for dry-run contract")

    metadata = ((payload.get("metadata") or {}).get("finharness") or {})
    if not isinstance(metadata, dict):
        findings.append("metadata.finharness must be a mapping")
        metadata = {}
    if metadata.get("mode") != "dry_run_contract":
        findings.append("metadata.finharness.mode must be dry_run_contract")
    for field in REQUIRED_METADATA_FALSE:
        if metadata.get(field) is not False:
            findings.append(f"metadata.finharness.{field} must be false")
    if metadata.get("source_corpus") != "data/redteam/payloads/asset-boundary-v0.json":
        findings.append("metadata.finharness.source_corpus must reference local corpus")

    plugins = redteam.get("plugins") or []
    plugin_ids = [
        str(item.get("id") if isinstance(item, dict) else item)
        for item in plugins
    ]
    missing_plugins = {
        "prompt-injection",
        "hijacking",
        "excessive-agency",
    } - set(plugin_ids)
    for plugin in sorted(missing_plugins):
        findings.append(f"missing planned redteam plugin: {plugin}")

    return {
        "schema": "finharness_promptfoo_redteam_dryrun_validation_v1",
        "quality_ok": not findings,
        "findings": findings,
        "target_count": len(targets),
        "plugin_ids": plugin_ids,
        "execution_allowed": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "evals" / "promptfoo" / "redteam-dryrun.yaml",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=ROOT / "data" / "redteam" / "exports" / "promptfoo-redteam-dryrun-validation.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_config(load_yaml(args.config))
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["quality_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
