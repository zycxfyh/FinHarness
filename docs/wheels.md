# Wheels

## Finance

| Wheel | Local path | Role |
| --- | --- | --- |
| OpenBB | `vendor/OpenBB` | Financial data platform and analyst workflow foundation. |
| Backtrader | `vendor/backtrader` | Classic Python backtesting engine. |
| vectorbt | `vendor/vectorbt` | Fast vectorized strategy research and parameter sweeps. |
| NautilusTrader | installed wheel | Production-grade event-driven simulation and live-parity trading architecture. |
| Riskfolio-Lib | installed wheel | Portfolio optimization and risk-constrained allocation. |
| QuantStats | installed wheel | Performance analytics and tear sheets. |
| FinGPT | `vendor/FinGPT` | Financial LLM and NLP reference project. |

## Harness

| Wheel | Local path | Role |
| --- | --- | --- |
| OpenAI Agents SDK | `vendor/openai-agents-python` | Lightweight agent, tool, handoff, and tracing foundation. |
| LangGraph | `vendor/langgraph` | Durable stateful agent orchestration. |
| promptfoo | `vendor/promptfoo` | Prompt, RAG, agent, and red-team eval harness. |
| DeepEval | `vendor/deepeval` | LLM evaluation framework for regression testing. |

## Later

| Wheel | Why not first |
| --- | --- |
| QuantConnect Lean | Excellent professional-grade engine, but heavier C#/Python ecosystem. Add after basic backtesting is understood. |
| Langfuse / Phoenix | Add when we have traces worth observing. |
| DuckDB / Polars | Add when local financial datasets become larger. |
