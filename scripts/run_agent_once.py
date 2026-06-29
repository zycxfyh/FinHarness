from __future__ import annotations

import argparse
import asyncio
import os
import sys

from agents import Runner

from finharness.agent_tools import build_finance_research_agent


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run one FinHarness Agent prompt.")
    parser.add_argument(
        "--profile",
        default=os.environ.get("FINHARNESS_AGENT_PROFILE", "default"),
    )
    args = parser.parse_args()
    try:
        agent = build_finance_research_agent(profile_name=args.profile)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set; agent runner skipped.")
        print("Tools are still available and covered by tests/test_agent_tools.py.")
        print(f"Selected profile: {args.profile}")
        return

    result = await Runner.run(
        agent,
        (
            "Fetch historical risk metrics for SPY from 2025-01-01 to 2025-06-30, "
            "evaluate the latest risk note, and summarize the result. "
            "Mention the data source and whether it is TradingView data."
        ),
    )
    print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())
