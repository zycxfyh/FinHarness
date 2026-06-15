# FinHarness User Guide

**New here? This is the front door. Read it top to bottom once — about 30 minutes — and you will understand what FinHarness is for and have run it yourself.**

This guide is for the **operator** — the person using FinHarness to govern their own
trading research and discipline. If instead you want to *extend* the lab (add
adapters, gates, or wheels), start with [../README.md](../README.md),
[../CONTEXT.md](../CONTEXT.md), and [../AGENTS.md](../AGENTS.md) — this guide does not
cover building.

---

## 1. What FinHarness is (in one sentence)

> FinHarness is **not a trading bot**. It is a governed financial-decision bench:
> it uses mature trading and research tools to help you form evidence-bound
> suggestions, then wraps those suggestions in **guardrails and an audit trail**.

It does **not** promise to make you money. Any retail tool that promises that should
be closed immediately. It also does not pretend to be advice-free: the point is to
help you understand, plan, decide, and review. The difference is that FinHarness
forces each non-trivial suggestion to show its evidence, assumptions, rejected
alternatives, risks, authority boundary, receipt path, and future review condition.
What FinHarness bets on is different: most retail losses come from **behavior and
self-deception** — averaging down into a drawdown, trading without a thesis,
mistaking luck for skill, reading only the bullish half of a report. Every part of
FinHarness is aimed at those failure modes.

## 2. The one idea: a closed loop

Everything in FinHarness is one loop. If you remember only one picture, remember this:

```
   observe the market (read-only)
        │
        ▼
   get stopped by a guardrail when you act on impulse
        │
        ▼
   real actions leave a receipt (an automatic audit record)
        │
        ▼
   receipts pile up into a lesson
        │
        ▼
   a human promotes the lesson into a stricter rule
        │
        ▼
   the next time you are about to trade, the rule stops you earlier
```

It does not predict prices. It makes **your process compound** — so the same mistake
costs you less the second time. That layer is what FinHarness adds; the price data,
backtests, and execution semantics all come from mature libraries.

## 3. What it is *not*

- ❌ Not a magic answer or execution authority. FinHarness can produce governed
  suggestions, policy drafts, and review prompts, but the market cockpit is
  hard-wired to `execution_allowed: false` and produces review evidence only.
- ❌ Not one-click auto-trading. A live write needs an env flag **and** an interactive
  confirmation **and** a written thesis — by design.
- ❌ Not a from-scratch reinvention. Strategy, backtesting, portfolio, and execution
  semantics belong to mature wheels (vectorbt, NautilusTrader, OpenBB, …). Local code
  is only adapters, guards, receipts, and workflows. See [CONTEXT.md](../CONTEXT.md).

When FinHarness suggests something, read it as:

```text
claim + evidence + assumptions + rejected alternatives + risks + authority boundary
```

not as:

```text
guaranteed edge or permission to trade.
```

## 4. Before your first session

First-time setup is in the README ([../README.md](../README.md)). Short version:

```bash
mise trust && mise install && direnv allow
task setup     # sync deps from lockfiles
task check     # standard local verification
```

You do **not** need a brokerage account, an API key, or any trading history to do the
golden path below. The first two steps run fully offline. Steps that need the network
or an LLM provider are marked.

## 5. Your first session (the golden path)

Run these in order. After each, read the "What you should see" note — that is where the
point lands.

### Step 1 — Confirm the bench is alive *(offline)*

```bash
task status
```

**What you should see:** a Python version, `pnpm` version, and the list of mature
wheels already cloned under `vendor/` (vectorbt, backtrader, OpenBB, langgraph, …).
This proves the bench is wired and the heavy lifting lives in real libraries, not
local code.

### Step 2 — Watch a guardrail stop you *(offline — the core moment)*

You have made zero trades, yet you can still ask: *"If I were down 3% and had lost 3
in a row, may I keep trading?"*

```bash
task guard:interactive -- --drawdown-pct -3 --consecutive-losses 3
```

**What you should see:** `"trade_allowed": false`, `"level": "hard_stop"`, a list of
`reasons`, a list of `required_actions`, and the process exiting with a **non-zero
code**. That non-zero exit is not an error — it is the point. When the guardrail
blocks you, the whole pipeline hard-stops with it (this is called **fail-closed**).

Now soften the scenario and watch the verdict change:

```bash
task guard:interactive -- --drawdown-pct -1.5 --consecutive-losses 1 --thesis   # caution, still blocked
task guard:interactive -- --drawdown-pct -0.5 --consecutive-losses 0 --thesis   # clear, allowed
```

The guard has three states: **clear** (allowed) → **caution** (blocked, near a limit)
→ **hard_stop** (blocked, limit breached). Note that without `--thesis`, even a clean
drawdown adds the reason *"planned trade has no written thesis"* — no thesis, no trade.

### Step 3 — See the closed loop as a real artifact *(offline, reading files)*

The thresholds the guard just used are **not hard-coded** — they have lineage. Look at
the cooldown rule the guard applied:

- The lesson it came from: [lessons/2026-06-14-loss-cooldown-tightening.md](lessons/2026-06-14-loss-cooldown-tightening.md)
- The rule change a human promoted: `data/state/rule-changes/rulechg_20260613T165140Z_ecd766ed.json`

That rule tightened the post-loss cooldown from 30 → 45 minutes, citing 747 receipts
with 37 quality failures as evidence. A real history of trades became a lesson, a human
approved it, and it now governs every future trade you propose. **This is the closed
loop from section 2, on disk.**

### Step 4 — Look at the read-only market cockpit *(needs network; read-only, no account)*

```bash
task cockpit:market
```

This pulls public price data and writes a one-screen watchlist to
[operations/market-cockpit-latest.md](operations/market-cockpit-latest.md): returns,
drawdown, trend, RSI, MACD, plus an honest list of **broken paths** and a **human
review queue**. The top of the file says `Execution allowed: false` and the bottom
repeats that it authorizes no orders. A tool that shows you its own broken paths is
more trustworthy than one that only draws red and green arrows.

### Step 5 — (Optional) Catch an AI note overclaiming *(needs an LLM provider configured)*

```bash
task eval:risk
```

This evaluates a generated finance note for **overclaiming and missing risk
warnings** — the research-quality side of the same discipline. Skip it for now if you
have not configured an LLM provider.

## 6. The four loops (the map)

Once the golden path makes sense, the whole system is just four loops plus
deterministic steps. One command each:

| Loop | What it does | Command |
|---|---|---|
| 1 — Observation | Daily evidence from the market | `task workflow:daily-evidence` |
| 2 — Hypotheses | Draft falsifiable hypotheses, gates check them | `task hypotheses:graph -- --llm-enabled` |
| 3 — Feedback | Show persisted behavioral trading state | `task trading-state:show` |
| 4 — Lessons | Draft lesson candidates; a human promotes them | `task lessons:draft` |

Loop topology and the target state live in
[think/2026-06-12-target-state-b-and-loop-topology.md](think/2026-06-12-target-state-b-and-loop-topology.md).

## 7. You are onboarded when you can answer "yes" to all of these

- [ ] I can state in one sentence what FinHarness is **and is not**.
- [ ] I ran `task guard:interactive` and understand why a non-zero exit is correct.
- [ ] I can name the three guard states (clear / caution / hard_stop).
- [ ] I can trace one rule back to the lesson and receipts that produced it.
- [ ] I know the cockpit is review-only and never authorizes an order.
- [ ] I know a live write needs an env flag + a written thesis + interactive confirmation.

If all six are checked, you understand FinHarness well enough to use it safely.

## 8. The golden rule (and the boundaries)

Everything is **fail-closed**: risk-gate and execution runs stay at
`needs_human_review` until a human attests with a written reason. The live OKX write
path refuses before it ever reaches the exchange on a hard-stop drawdown/loss state, an
over-cap notional, a missing thesis, or missing attestation.

**Never run a live write command from emotion or without a written plan.** The friction
on that path is deliberate — those few seconds are usually the seconds that save you
money. The Alpaca path is paper-only and the live Alpaca endpoint is intentionally not
wired. See the live-order gate at [../scripts/okx_live_order.py](../scripts/okx_live_order.py).

When a drawdown or a losing streak starts changing how you act, stop using the project
as an execution aid and switch it to review mode: `task trading:reset-check`
(see [notes/drawdown-reset-protocol.md](notes/drawdown-reset-protocol.md)).

## 9. Glossary (quick reference)

- **Receipt** — a durable, automatic record of inputs, tool versions, commands,
  decisions, outputs, and known limits. Evidence, not proof of future performance.
- **Risk gate** — a pre-trade control that decides whether an action may continue
  (drawdown, leverage, size, missing thesis, missing human confirmation).
- **Guard** — the behavioral check on drawdown / consecutive losses you ran in step 2.
- **Venue adapter** — a thin wrapper around an official broker/exchange surface; it
  normalizes symbols and records receipts, but never reimplements exchange logic.
- **Wheel** — a mature external library that owns a heavy capability (vectorbt,
  NautilusTrader, OpenBB, …). Local code adapts and governs wheels; it never becomes one.
- **Fail-closed** — when in doubt, deny. Blocks propagate; the pipeline hard-stops.
- **Attestation** — a human signing off with a written reason before a gated action runs.

Full domain definitions: [../CONTEXT.md](../CONTEXT.md).

## 10. Where to go next

- Build the assistant yourself, day by day: [week-01.md](week-01.md)
- The map of mature wheels in use: [wheels.md](wheels.md)
- Why local code stays thin (the architecture rule): [../CONTEXT.md](../CONTEXT.md)
- Paper and live broker wiring: the **Alpaca Paper** and **OKX Live** sections of
  [../README.md](../README.md)
