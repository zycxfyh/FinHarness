from __future__ import annotations

import asyncio
import os

from agents import Runner

from finharness.agent_tools import finance_research_agent


async def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set; agent runner skipped.")
        print("Tools are still available and covered by tests/test_agent_tools.py.")
        return

    result = await Runner.run(
        finance_research_agent,
        (
            "Fetch historical risk metrics for SPY from 2025-01-01 to 2025-06-30, "
            "evaluate the latest risk note, and summarize the result. "
            "Mention the data source and whether it is TradingView data."
        ),
    )
    print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())
