# ExecutionEngineInterface — Nautilus Default Spec (for Codex)

Executable spec for **Phase 3** — the highest-authority-risk step. Goal: make the
execution graph default to the NautilusTrader paper adapter and restrict the fake
adapter to tests, **without weakening the live block**.
[discipline-layer-baseline.md](discipline-layer-baseline.md) is the hard
regression guard: its 42 tests (incl. `test_live_mode_is_blocked_before_submit`)
must stay green.

**Prerequisite / sequencing:** start only after Phase 2b's `task check` is green.

## 0. Current state (verified)

- `src/finharness/execution.py` already has `NautilusPaperExecutionAdapter`
  (delegates order shape to NautilusTrader typed orders; routes nothing, simulates
  no fills, authorizes no live) and `FakePaperExecutionAdapter` (deterministic
  fills for tests).
- `collect_execution_events(..., adapter=None)` **already defaults to
  `NautilusPaperExecutionAdapter()`** and already blocks live:
  `if context.requested_mode == "live": blocked_event("live execution is blocked
  in Layer 9 MVP")`.
- The leak: `execution_graph.py` hardcodes `FakePaperExecutionAdapter` in two
  nodes — `submit_or_dry_run_node`
  ([execution_graph.py:175](../../src/finharness/execution_graph.py)) and
  `snapshot_node`
  ([execution_graph.py:229](../../src/finharness/execution_graph.py)). So the real
  graph path runs the fake adapter, not Nautilus.

## 1. The change

Make the adapter selection in both nodes explicit and Nautilus-default:

- Default: pass `adapter=None` to `collect_execution_events` (→ Nautilus), OR
  build `NautilusPaperExecutionAdapter()` explicitly.
- Fake only on explicit opt-in: build `FakePaperExecutionAdapter(fill_mode=...)`
  **only** when the state explicitly requests it, e.g. a new state key
  `state.get("execution_adapter") == "fake"` (default `"nautilus"`). The existing
  `fake_fill_mode` is read only on that branch.
- Keep both nodes consistent (they must select the adapter the same way).

The fake adapter stays importable for tests; it is simply no longer the default
production path.

## 2. Red lines

- **Live stays blocked.** Do not touch the live-block branch in
  `collect_execution_events`. `test_live_mode_is_blocked_before_submit` and the
  rest of the discipline baseline must pass unchanged.
- **No broker routing.** Nautilus is used only for typed paper order shaping. Do
  not wire any real venue, broker session, or live endpoint.
- **Fake not reachable by default.** After this change, the default graph run uses
  Nautilus; the fake adapter is reached only when a test explicitly sets
  `execution_adapter="fake"`.
- **No new execution authority.** `execution_allowed` / live defaults unchanged;
  human attestation path unchanged.

## 3. Tests to write

1. Default path: a graph run with no `execution_adapter` produces Nautilus-backed
   paper events (assert the Nautilus adapter name / `NAUTILUS_ORDER_BACKEND` in
   the events), not fake fills.
2. Explicit fake: setting `execution_adapter="fake"` (with `fake_fill_mode`) still
   yields the deterministic fake events — so existing deterministic execution
   tests keep working via explicit opt-in.
3. Live still blocked through the graph: a live-mode request still produces a
   `blocked_before_submit` event end-to-end.
4. Discipline baseline: re-run the 42 baseline tests; all green.

## 4. Acceptance checklist

- [ ] `submit_or_dry_run_node` and `snapshot_node` default to Nautilus; fake only
      on explicit `execution_adapter="fake"`.
- [ ] Live block untouched and proven by test through the graph.
- [ ] No broker/venue/live wiring added.
- [ ] Existing deterministic execution tests updated to opt into the fake adapter
      explicitly; all green.
- [ ] Discipline-baseline tests green; `uv run ruff check` clean; `task check`
      passes.
- [ ] Report with test evidence, not a bare "done".

## 5. Out of scope

- No live trading path, no real broker adapter — that remains gated behind the
  existing OKX/Alpaca fail-closed controls and is not part of this phase.
- Policy/Evidence work is Phase 5 (separate plan).
