"""Export deterministic FinHarness red-team corpus artifacts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from finharness.hardening import (  # noqa: E402
    build_red_team_manifest,
    load_red_team_payloads,
    render_promptfoo_boundary_eval,
    render_red_team_jsonl,
    render_red_team_manifest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        type=Path,
        default=ROOT / "data" / "redteam" / "payloads" / "asset-boundary-v0.json",
    )
    parser.add_argument(
        "--promptfoo-output",
        type=Path,
        default=ROOT / "evals" / "promptfoo" / "redteam-boundary.yaml",
    )
    parser.add_argument(
        "--jsonl-output",
        type=Path,
        default=ROOT / "data" / "redteam" / "exports" / "asset-boundary-v0.jsonl",
    )
    parser.add_argument(
        "--manifest-output",
        type=Path,
        default=ROOT / "data" / "redteam" / "exports" / "manifest.json",
    )
    parser.add_argument(
        "--readiness-ref",
        default="data/redteam/exports/tool-readiness.json",
    )
    return parser.parse_args()


def repo_ref(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def main() -> int:
    args = parse_args()
    payloads = load_red_team_payloads(args.corpus)

    args.promptfoo_output.parent.mkdir(parents=True, exist_ok=True)
    args.promptfoo_output.write_text(
        render_promptfoo_boundary_eval(payloads),
        encoding="utf-8",
    )

    args.jsonl_output.parent.mkdir(parents=True, exist_ok=True)
    args.jsonl_output.write_text(render_red_team_jsonl(payloads), encoding="utf-8")

    manifest = build_red_team_manifest(
        corpus_ref=repo_ref(args.corpus),
        promptfoo_ref=repo_ref(args.promptfoo_output),
        jsonl_ref=repo_ref(args.jsonl_output),
        payloads=payloads,
        readiness_ref=args.readiness_ref,
    )
    args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_output.write_text(
        render_red_team_manifest(manifest),
        encoding="utf-8",
    )

    print(
        "wrote red-team artifacts "
        f"payload_count={len(payloads)} "
        f"promptfoo={args.promptfoo_output} "
        f"jsonl={args.jsonl_output} "
        f"manifest={args.manifest_output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
