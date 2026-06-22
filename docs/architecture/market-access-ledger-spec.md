# Market-Access Limit Ledger — Execution Spec (NOW-4 / G06)

Executable spec for the last NOW-phase gap and the one Codex caught that the
Claude analysis under-weighted: today every cap is **per-order**, but SEC Rule
15c3-5(i) requires **aggregate pre-set credit/capital limits across all access**.
Many small orders, each under the per-order cap, can still breach a sensible
daily total. NOW-4 adds one **shared, persisted aggregate limit ledger** that
**every mutation-capable path consumes**. See gap **G06** in
[07 Final Merged Plan](industry-benchmark/07-final-merged-plan.md).

**No new dependency** (pydantic + stdlib, mirroring `trading_state_store.py` and
`rule_change_ledger.py`).

## 0. Current state (verified)

- `okx_live_gate.py`: `assess_live_order` enforces a **per-order** notional cap
  (`order_notional` → `None` ⇒ fail-closed block; `> max_notional` ⇒ block) and
  writes a receipt. No window accumulation.
- `risk_gate.py`: `max_notional_check` is `requested_notional <= max_paper_notional`,
  **per run**. No accumulation.
- No path tracks cumulative usage; nothing shared across OKX / Alpaca / paper.

## 1. New module `src/finharness/market_access_ledger.py`

Mirror `trading_state_store` (persistence) + `rule_change_ledger` (receipts).

```python
class MarketAccessKey(BaseModel):          # frozen
    environment: Literal["paper", "live"]
    venue: str                              # "okx" | "alpaca" | "paper_review"
    operator: str                           # attester identity
    account: str
    symbol: str

class MarketAccessLimit(BaseModel):         # frozen — the human-set ceiling
    window: Literal["daily"] = "daily"
    max_window_notional: float
    max_window_order_count: int

class LedgerEntry(BaseModel):               # frozen
    entry_id: str
    window_id: str                          # UTC date for daily windows
    key: MarketAccessKey
    notional: float
    created_at_utc: str

class MarketAccessDecision(BaseModel):      # frozen
    allowed_within_limit: bool              # NOT execution authority
    window_id: str
    used_notional: float
    remaining_notional_after: float
    used_order_count: int
    remaining_orders_after: int
    blocking_reasons: list[str] = Field(default_factory=list)
    execution_allowed: bool = False         # always; ledger never authorizes
```

Functions:

- `window_id(now) -> str` — UTC date string for the daily window.
- `usage_in_window(ledger, key, window_id) -> (used_notional, used_count)` —
  sum over entries matching the key in the window.
- `evaluate_market_access(*, key, notional, limit, ledger, now) -> MarketAccessDecision`
  — **read-only**, computes whether the request fits the *remaining* aggregate.
- `record_consumption(*, key, notional, ledger, now, state_root=None,
  receipt_root=None) -> LedgerEntry` — appends the entry, persists state
  (atomic, env-overridable path like `trading_state_store`), and writes a receipt
  recording **remaining limit** after consumption.

## 2. Fail-closed evaluation rules

`evaluate_market_access` blocks (sets `allowed_within_limit=False`) when:

- `notional` is `None`, non-finite, or `<= 0` → "notional could not be bounded;
  refusing fail-closed" (same posture as `order_notional` → `None`);
- `limit` is missing/unset for the key → "no pre-set aggregate limit configured;
  refusing fail-closed";
- `used_notional + notional > limit.max_window_notional` → "aggregate window
  notional … exceeds remaining …";
- `used_count + 1 > limit.max_window_order_count` → "aggregate window order count
  exceeded".

Otherwise `allowed_within_limit=True` with `remaining_*_after` populated.

## 3. Wiring — every mutation-capable path consumes the same ledger

The ledger is an **additional** pre-trade brake layered on the existing controls,
never a replacement.

- **OKX live gate** (`assess_live_order`): after the per-order cap passes, also
  call `evaluate_market_access`; if not `allowed_within_limit`, add a blocking
  reason and block. On an authorized, executed order, call `record_consumption`.
- **Paper execution / risk_gate path**: consult the ledger (environment=`paper`)
  as a pre-submit check; consume on an authorized paper order.
- **Alpaca paper path**: same adapter shape (consult + consume).

Order of checks is unchanged otherwise: guard → reset flag → per-order cap →
**aggregate ledger** → human attestation → execute. The ledger only ever
*subtracts*; it cannot grant authority.

## 4. Red lines

- **Aggregate, not per-order** — the ledger accumulates across requests in a
  window. This is the whole point; do not reduce it to another per-order check.
- **One shared ledger + one limit model** consumed by OKX, Alpaca, and paper
  paths. No per-path private counter.
- **Ceilings are human-set config, not a CLI flag.** `MarketAccessLimit` comes
  from a config/constant a human owns; raising a ceiling is a rule-change with
  lineage (gap G09), never a request-time argument. A request can only spend
  *within* the ceiling.
- **Fail-closed** on uncomputable notional, missing limit, or over-aggregate.
- **Consume only after authorization.** `record_consumption` runs only once the
  request has cleared the gate + per-order cap + human attestation and is actually
  proceeding — `evaluate_market_access` never mutates state.
- **No execution authority.** `execution_allowed=false` always; risk_gate,
  human attestation, and the live block all still apply on top.
- **Receipt records remaining limit** (15c3-5(iv) surveillance evidence).
- **No new dependency.**

## 5. Tests (`tests/test_market_access_ledger.py`)

1. **Aggregate block:** two orders each under the per-order cap but together over
   `max_window_notional` → the second is blocked by the ledger.
2. **Order-count block:** count ceiling reached → next blocked.
3. **Fail-closed:** `notional=None`/`<=0` → blocked; missing limit → blocked.
4. **Within limit:** allowed with correct `remaining_notional_after`.
5. **Window rollover:** entries from a prior `window_id` do not count toward today.
6. **Consume-after-auth:** `evaluate_market_access` does not write state;
   `record_consumption` appends one entry and writes a receipt with remaining.
7. **No authority:** decision has no path to `execution_allowed=true`; model field
   is `False`.
8. **OKX integration:** an over-aggregate live order blocks even when the
   per-order cap passes; a within-limit order records consumption.

## 6. Acceptance checklist

- [ ] `market_access_ledger.py` added; persistence mirrors `trading_state_store`
      (atomic write, env-overridable path); receipts mirror `rule_change_ledger`.
- [ ] `evaluate_market_access` fail-closed per §2; `record_consumption` post-auth
      only; receipt records remaining limit.
- [ ] OKX live gate + paper/risk_gate path consume the shared ledger; Alpaca path
      uses the same adapter.
- [ ] Ceilings are human-owned config, not request-time args.
- [ ] No execution authority field reachable; `execution_allowed=false` preserved;
      discipline-baseline tests still green.
- [ ] New tests (§5) green; `ruff` clean; `task check` passes; `task security:scan`
      passes (this touches the live-write path).
- [ ] Report with test evidence, not a bare "done".

## 7. Out of scope

- Typed operator/account authorization model (gap **G07**) — separate Next spec.
- Ceiling-vs-request governance / raising ceilings with lineage (gap **G09**) —
  separate Next spec; NOW-4 only requires the ceiling to be human-owned config.
- Per-symbol vs per-account aggregation policy beyond the key above can be refined
  later; start with the key in §1.
