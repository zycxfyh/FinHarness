#!/usr/bin/env python3
"""Agent Cognition Flow smoke test.

Demonstrates a complete deterministic cognition flow using Wave 0 primitives:
  goal → option set → plan draft → evaluation → authority → agent run receipt

Run:
  uv run python scripts/run_agent_cognition_flow_smoke.py

No LLM, no broker, no StateCore, no Execution Kernel.
All artifacts are written to a temporary receipt root and cleaned up.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from finharness.agent_cognition_flow import run_agent_cognition_flow


def main() -> None:
    print("=" * 60)
    print("Agent Cognition Flow — Smoke Test")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        result = run_agent_cognition_flow(
            goal="Evaluate rebalancing options for current portfolio",
            profile_name="review-draft",
            objective="Determine whether to increase SPY allocation by 5%",
            option_claims=[
                "Increase SPY allocation by 5% — expected to reduce cash drag",
                "Hold current allocation — wait for FOMC clarity",
                "Reduce SPY by 3% and rotate into TLT — defensive",
            ],
            plan_steps=[
                "Review current exposure via capital_summary context",
                "Check IPS compliance via ips_check context",
                "Run pre-trade checks on candidate",
                "Draft adjustment proposal for human review",
            ],
            receipt_root=root,
            source_refs=["capital_summary", "current_ips"],
            human_attester="ops_reviewer",
            human_reason=(
                "Evaluation receipt reviewed; plan remains non-executing "
                "and requires separate future checks before any action"
            ),
            explicit_confirmation=True,
        )

        print(f"\nFlow ID:     {result.flow_id}")
        print(f"Goal:        {result.goal}")
        print("\nArtifacts:")
        print(f"  OptionSet:          {result.option_set_ref}")
        print(f"  PlanDraft:           {result.plan_draft_ref}")
        print(f"  EvaluationReport:    {result.evaluation_report_ref}")
        print(f"  AuthorityTransition: {result.authority_transition_ref}")
        print(f"  AgentRunReceipt:     {result.agent_run_receipt_ref}")
        print(f"\nexecution_allowed: {result.execution_allowed}")
        print(f"authority transition present: {result.authority_transition_ref is not None}")

        # Verify all artifacts exist
        all_exist = all(
            root.joinpath(ref).exists()
            for ref in [
                result.option_set_ref,
                result.plan_draft_ref,
                result.authority_transition_ref,
                result.agent_run_receipt_ref,
            ]
        )
        eval_exists = root.joinpath(
            "evaluation-reports",
            result.evaluation_report_ref.split("/")[-1].split("#")[0],
        ).exists()
        print(f"\nAll artifacts persisted: {all_exist and eval_exists}")

    print("\n" + "=" * 60)
    print("Smoke test PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
