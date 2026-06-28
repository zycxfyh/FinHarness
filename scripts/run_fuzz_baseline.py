"""Run the FinHarness deterministic fuzzing baseline.

This is a local fuzz-style boundary harness for governance inputs. It avoids
new dependencies and does not claim OSS-Fuzz, ClusterFuzzLite, or SLSA coverage.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from finharness.market_data import ROOT
from finharness.repo_intelligence import classify_security_surface
from finharness.research_assets import resolve_research_assets

DEFAULT_CORPUS = ROOT / "data" / "security" / "fuzzing" / "corpus.json"
DEFAULT_REPORT = ROOT / "data" / "security" / "fuzzing" / "latest.json"
VALID_LAYERS: set[str] = {"L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9", "L10"}


def repo_path(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load_corpus(path: Path = DEFAULT_CORPUS) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload.get("cases", []))


def generated_cases(*, seed: int, count: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)  # noqa: S311 -- deterministic fuzz corpus, not crypto.
    cases: list[dict[str, Any]] = []
    path_fragments = [
        "src/finharness/authorization.py",
        "src/finharness/restricted_symbols.py",
        "src/finharness/providers/ccxt_provider.py",
        "docs/ordinary.md",
        "docs/security/finharness-threat-model.md",
        ".github/workflows/security.yml",
        "data/security/restricted-symbols.json",
        "data/receipts/generated.json",
        "../outside.env",
        "experiments/archive/live_trading_legacy/okx/okx_cli.py",
        "tests/test_authorization.py",
    ]
    asset_fragments = [
        "trend_following_v0",
        "no_lookahead_validation_v0",
        "unknown_asset",
        "live_write_enable",
        "../secret",
        "",
        "alpaca_paper_adapter",
    ]
    for index in range(count):
        cases.append(
            {
                "id": f"generated_security_surface_{index}",
                "target": "security_surface",
                "paths": rng.sample(path_fragments, k=rng.randint(1, 4)),
            }
        )
        cases.append(
            {
                "id": f"generated_research_assets_{index}",
                "target": "research_assets",
                "asset_ids": rng.sample(asset_fragments, k=rng.randint(1, 4)),
                "layer": rng.choice(sorted(VALID_LAYERS)),
            }
        )
    return cases


def run_security_surface_case(case: dict[str, Any]) -> dict[str, Any]:
    paths = [str(item) for item in case.get("paths", [])]
    surface = classify_security_surface(paths)
    invariant_ok = surface["execution_allowed"] is False
    # A test file is not the execution surface (editing tests/* grants no execution),
    # so it must not be expected to require human review; matches classify_security_surface.
    if any(
        not path.startswith("tests/")
        and (
            path.startswith(".github/")
            or path.startswith("docs/security/")
            or path.startswith("data/security/")
            or path.startswith("experiments/archive/live_trading_legacy/")
            or "authorization" in path.replace("-", "_")
            or "restricted_symbols" in path.replace("-", "_")
            or "providers" in path.replace("-", "_")
        )
        for path in paths
    ):
        invariant_ok = invariant_ok and surface["requires_human_review"] is True
    return {
        "target": "security_surface",
        "case_id": str(case.get("id", "unnamed")),
        "invariant_ok": invariant_ok,
        "summary": surface,
    }


def run_research_assets_case(case: dict[str, Any]) -> dict[str, Any]:
    layer = str(case.get("layer", "L9"))
    if layer not in VALID_LAYERS:
        layer = "L9"
    selection = resolve_research_assets(
        research_asset_ids=[str(item) for item in case.get("asset_ids", [])],
    )
    context = selection.context_for_layer(layer)  # type: ignore[arg-type]
    invariant_ok = (
        selection.execution_allowed is False
        and context["execution_allowed"] is False
        and context["policy"] == "cite_only"
    )
    return {
        "target": "research_assets",
        "case_id": str(case.get("id", "unnamed")),
        "invariant_ok": invariant_ok,
        "summary": {
            "layer": layer,
            "missing_ids": selection.missing_ids,
            "strategy_ids": context["strategy_ids"],
            "method_ids": context["method_ids"],
            "reference_ids": context["reference_ids"],
            "execution_allowed": False,
        },
    }


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    target = case.get("target")
    try:
        if target == "security_surface":
            return run_security_surface_case(case)
        if target == "research_assets":
            return run_research_assets_case(case)
        return {
            "target": str(target),
            "case_id": str(case.get("id", "unnamed")),
            "invariant_ok": False,
            "error": "unknown target",
        }
    except Exception as exc:
        return {
            "target": str(target),
            "case_id": str(case.get("id", "unnamed")),
            "invariant_ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def build_fuzz_report(
    *,
    seed: int,
    generated_count: int,
    corpus_path: Path = DEFAULT_CORPUS,
) -> dict[str, Any]:
    corpus_cases = load_corpus(corpus_path)
    cases = [*corpus_cases, *generated_cases(seed=seed, count=generated_count)]
    results = [run_case(case) for case in cases]
    failed = [item for item in results if not item["invariant_ok"]]
    targets = sorted({str(item.get("target")) for item in results})
    return {
        "schema": "finharness.fuzz_baseline.v1",
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "seed": seed,
        "generated_count": generated_count,
        "corpus_ref": repo_path(corpus_path),
        "case_count": len(results),
        "passed_case_count": len(results) - len(failed),
        "failed_case_count": len(failed),
        "failed_cases": failed,
        "targets": targets,
        "scorecard_status": "local_baseline_not_oss_fuzz_or_clusterfuzzlite",
        "non_claims": [
            "Not OSS-Fuzz coverage.",
            "Not ClusterFuzzLite coverage.",
            "Not live exchange fuzzing.",
            "Does not authorize live trading.",
        ],
        "execution_allowed": False,
    }


def write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20260604)
    parser.add_argument("--generated-count", type=int, default=32)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_fuzz_report(
        seed=args.seed,
        generated_count=args.generated_count,
        corpus_path=args.corpus,
    )
    write_report(args.report_output, report)
    print(
        json.dumps(
            {
                "report_ref": repo_path(args.report_output),
                "case_count": report["case_count"],
                "failed_case_count": report["failed_case_count"],
                "targets": report["targets"],
                "execution_allowed": False,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report["failed_case_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
