# SEC Rule 15c3-5 Market Access Review

Date: 2026-06-15
Status: draft review
Scope: FinHarness market-access-adjacent paths: risk gate, execution, OKX live
gate, Alpaca paper scripts, trading guard/state, receipts, ownership, and
security governance.

This is an engineering control review, not legal advice and not a compliance
certification. SEC Rule 15c3-5 directly applies to broker-dealers with market
access, or broker-dealers providing access to an exchange or ATS. FinHarness is a
local research and governance harness, not a broker-dealer, not an exchange or
ATS member/subscriber, and its ten-layer graph does not provide live securities
market access.

The rule is still a useful benchmark because it names the control shape a serious
electronic order-entry system must have before any order reaches a market.

## Source Baseline

Primary source:

- eCFR, 17 CFR 240.15c3-5, current display as of 2026-06-15:
  https://www.ecfr.gov/current/title-17/chapter-II/part-240/subject-group-ECFRc8401dcba174f73/section-240.15c3-5
- SEC Division of Trading and Markets FAQ:
  https://www.sec.gov/rules-regulations/staff-guidance/trading-markets-frequently-asked-questions/divisionsmarketregfaq-0

Relevant rule duties, paraphrased:

- Establish, document, and maintain risk management controls and supervisory
  procedures for market access.
- Financial controls must reject orders that exceed pre-set credit/capital
  thresholds and reject erroneous orders by price, size, duplicate-order, or
  short-period parameters.
- Regulatory controls must prevent orders unless pre-order regulatory
  requirements are satisfied, block restricted securities/persons, restrict
  market-access systems to authorized persons/accounts, and deliver immediate
  post-trade execution reports to surveillance personnel.
- Required controls must be under direct and exclusive control of the responsible
  broker-dealer, subject to narrow allocation rules.
- Controls must be reviewed regularly, at least annually, with documented review
  and CEO/equivalent certification.

SEC staff FAQ also states that if any electronic system is involved in effecting
execution, automated pre-trade controls must be used at the point orders become
systematized; controls that let orders enter and then chase/cancel are not enough.

## Applicability Boundary

| Surface | 15c3-5 direct legal scope? | Engineering relevance |
| --- | --- | --- |
| Ten-layer research -> risk -> execution chain | No direct market access; live blocked | Strong benchmark for pre-trade control shape |
| Alpaca paper scripts | Paper broker sandbox, not live market access | Useful for practicing pre-order controls and receipts |
| OKX live write path | Crypto venue path, not SEC securities exchange/ATS scope | High-risk live mutation path; use 15c3-5 discipline anyway |
| Future Alpaca live / equities live access | Could become market-access-adjacent through a broker | Must not be added without a real market-access control system |

## Positive Alignment

| Rule expectation | FinHarness evidence | Current read |
| --- | --- | --- |
| No unfiltered access | `risk_gate.py` blocks live mode and marks decisions `live_execution_allowed=False`; `execution.py` produces zero live order requests and a `blocked_before_submit` event | Good for MVP; ten-layer live is blocked |
| Pre-order controls | `risk_gate.py` checks mandate, allowed symbols/actions, paper-vs-live boundary, max paper notional, concentration, liquidity, drawdown/loss state, behavior reset, scenario notes, order-language, and human review | Good shape, still primitive |
| Financial caps remain local | Riskfolio output is fed only into requested concentration; mandate cap is not widened by optimizer evidence | Strong design principle |
| Erroneous/duplicate controls | `execution.py` creates deterministic idempotency keys and fake adapter rejects duplicate client order IDs; OKX notional is fail-closed when unbounded | Partial; not yet universal across broker scripts |
| Authorized live mutation chokepoint | `okx_live_gate.py` requires behavioral guard pass, bounded notional, attester, written reason, thesis, receipt; `okx_cli.py` adds allowlists and two env gates | Strongest live-adjacent surface |
| Direct control of local brakes | Local gates/caps live in FinHarness code rather than in mature math libraries | Aligned with the spirit of direct/exclusive control |
| Immediate evidence | Risk, execution, post-trade, OKX live attempts, and Alpaca paper paths write receipts | Good evidence habit; not yet surveillance-grade |
| High-risk ownership | `.github/CODEOWNERS` covers execution, risk gate, OKX, Alpaca, governance/security docs; security tests assert ownership coverage | Good review substrate |

## Findings

### F1 — No Formal Market Access Control System Or Named Control Owner

Severity: High if live securities access is ever added; Medium today.

Evidence:

- `README.md` and `AGENTS.md` correctly say FinHarness is not an AI trading bot and
  ten-layer live execution is unauthorized.
- `docs/security/ssdf-control-map.md` already lists recurring review cadence and
  live-provider dual-control as residual work.
- Existing human attestations are per-action. There is no durable control-owner
  record that says who owns the whole control system, when it was reviewed, what
  controls are in force, and what changed.

15c3-5 comparison:

- The rule expects written controls/procedures, regular review, and annual
  CEO/equivalent certification for broker-dealers. FinHarness has receipts and
  tests, but no owner certification analogue.

Recommendation:

- Add a `docs/operations/market-access-control-register.md` plus durable receipt
  with: control owner, authorized operators, authorized accounts, venues,
  products, thresholds, restricted list source, review cadence, last review,
  next review, and non-claim that this is not SEC compliance certification.

### F2 — Aggregate Credit/Capital Thresholds Are Not Yet Modeled

Severity: High for any live/paper broker expansion; Medium today.

Evidence:

- `risk_gate.py` has per-run `max_paper_notional` and symbol concentration.
- `okx_live_gate.py` has a single-order `max_notional` cap and fails closed when
  notional cannot be computed.
- `scripts/alpaca_paper_dca_buy.py` can place marketable paper buys with
  `--execute`, but has no aggregate daily/account cap, no per-symbol cap, and no
  persistent decrementing limit ledger.

15c3-5 comparison:

- The rule expects pre-set credit/capital thresholds in aggregate for each
  customer and broker-dealer, reject-before-entry if the order would exceed
  limits.

Recommendation:

- Add a shared `MarketAccessLimitLedger` consumed by all mutating broker/venue
  scripts, even paper scripts. Minimum fields: account_id, operator_id,
  environment, venue, product_type, symbol, order_id/client_order_id,
  requested_notional, accepted_notional, daily_limit, open_order_limit,
  remaining_limit, source_receipt_ref, and decision.

### F3 — Alpaca Paper DCA Is Outside The Typed L8/L9 Control Plane

Severity: Medium today; High if copied into live.

Evidence:

- `README.md` states live Alpaca endpoint is intentionally not wired.
- `alpaca_client.py` is paper-first and hard-codes `PAPER_BASE_URL`.
- `scripts/alpaca_paper_dca_buy.py` uses `TradingState` guard and writes receipts,
  but bypasses `risk_gate.py` and `execution.py`.

15c3-5 comparison:

- If an electronic order system is involved, controls should be automated before
  the order is systematized. A separate script with its own guard is weaker than
  one shared market-access gate.

Recommendation:

- Route all Alpaca paper mutation scripts through a common market-access gate
  interface. Keep paper-only, but require the same pre-order decision object:
  authorized operator, account, allowed symbol, restricted-list check, max
  notional/quantity, marketability/price collar, duplicate client id, open-order
  cap, and receipt.

### F4 — Erroneous Order Controls Are Partial

Severity: Medium today; High if any live order path expands.

Evidence:

- OKX limit-like notional must be computable; missing price blocks.
- `execution.py` caps quantity and blocks live mode before request creation.
- Alpaca paper order-cycle deliberately places far-below-market limit order and
  cancels.
- Alpaca DCA places market orders or notional orders intended to fill, but no
  explicit price collar, duplicate-order window, fat-finger cap, or open-order
  count cap appears in the script.

15c3-5 comparison:

- The rule names price, size, duplicate-order, and short-period parameters as
  controls for erroneous orders.

Recommendation:

- Add a reusable erroneous-order gate: max order notional, max quantity, max
  marketable slippage or price collar, duplicate client-order check, max orders
  per time window, and max open orders. For market orders, estimate notional from
  latest price and apply a conservative reject-on-missing-price rule.

### F5 — Authorized Persons And Accounts Are Not A First-Class Model

Severity: Medium today.

Evidence:

- OKX live order requires `--attester` and `--reason`.
- Risk-gate CLI requires `--attest-human-review` plus reason, but not an attester
  identity.
- CODEOWNERS names a reviewer for high-risk files, but runtime operator identity,
  authorized account list, and account capability scope are not represented as a
  typed object.

15c3-5 comparison:

- The rule requires restricting access to market access systems and technology to
  pre-approved and authorized persons and accounts.

Recommendation:

- Add `AuthorizedOperator` and `AuthorizedAccount` config/receipt models. Risk
  gate and execution attestations should include attester identity, reason,
  timestamp, scope, and authorized account/environment. Do not read or store
  secrets in this model.

### F6 — Restricted Securities / Restricted Trading Status Is Shallow

Severity: Medium if live securities are added; Low today.

Evidence:

- Risk gate has an allowlist of symbols and action types.
- Alpaca scripts query account status and some assets/capabilities, but there is
  no durable restricted-symbol list or per-symbol regulatory restriction check.

15c3-5 comparison:

- The rule expects preventing orders for securities when the broker, customer, or
  other person is restricted from trading them.

Recommendation:

- Add a local `restricted_symbols.json` reference plus provider-backed asset
  tradability check for securities-like brokers. Decision receipts should include
  restricted-list version and provider tradability evidence.

### F7 — Post-Trade Reports Exist, But Not Surveillance-Grade

Severity: Medium.

Evidence:

- Execution and post-trade layers preserve raw lifecycle events and receipts.
- OKX live gate writes receipts for blocked, error, and executed attempts.
- Alpaca scripts write paper receipts.
- There is no immediate surveillance queue, owner notification, or consolidated
  post-trade execution report view for all mutating paths.

15c3-5 comparison:

- The rule requires appropriate surveillance personnel to receive immediate
  post-trade execution reports that result from market access.

Recommendation:

- Add `task market-access:surveillance` and `data/receipts/market-access-surveillance/`.
  Every broker/venue mutation path should append a normalized report:
  who/what/when/account/symbol/notional/status/receipt_ref/follow-up_required.

### F8 — Threshold Changes Are Not Fully Governed

Severity: Medium today; High for live writes.

Evidence:

- Lesson-to-rule promotion and effective rules exist for guard thresholds.
- Riskfolio cannot widen mandate caps.
- OKX live CLI accepts `--max-notional`; the override is recorded, but there is
  no separate approval or maximum configured ceiling for raising it.

15c3-5 comparison:

- SEC FAQ says threshold changes after a limit is met may be appropriate only
  under supervisory procedures, with reasons documented and retained.

Recommendation:

- Split thresholds into `configured_ceiling` and `request_limit`. CLI may only
  lower or set within ceiling. Raising the ceiling requires a rule-change
  promotion or control-owner attestation receipt.

### F9 — Records Are Mutable Local Files

Severity: Medium.

Evidence:

- Receipts and normalized payloads are JSON/Markdown files under `data/` and
  `docs/`.
- Receipt schemas and references now exist, but receipts are not signed,
  immutable, or retained under a formal records policy.

15c3-5 comparison:

- The rule refers to preserving supervisory procedures, control descriptions,
  reviews, and certifications as books and records.

Recommendation:

- Add checksum manifests for market-access receipts, plus an optional signing or
  append-only manifest path for live-adjacent receipts.

## Requirement Mapping

| 15c3-5 element | Current status | Notes |
| --- | --- | --- |
| Written controls/procedures | Partial | Many docs and tests exist, but no single market-access control manual |
| Pre-set aggregate credit/capital thresholds | Gap | Per-order/per-run caps exist; no aggregate ledger |
| Erroneous order rejection | Partial | OKX/typed execution better; Alpaca DCA weak |
| Pre-order regulatory compliance | Partial/gap | Research/risk checks exist; no securities restricted-list/control registry |
| Restricted securities/persons | Gap for live securities | Symbol allowlist is not enough |
| Authorized persons/accounts | Partial | Attester and CODEOWNERS exist; no runtime authorized-person/account model |
| Immediate post-trade reports | Partial | Receipts exist; no surveillance inbox |
| Direct/exclusive control | Partial/inapplicable | Local controls are owned locally; no broker-dealer control assertion |
| Regular effectiveness review | Partial | dogfood/task checks exist; no recurring control-owner review |
| Annual certification analogue | Gap | No named owner certification receipt |
| Books/records retention | Partial | Receipts exist; no immutability/retention policy |

## Priority Execution Path

1. Create a market-access control register and owner-certification receipt.
2. Introduce a shared `MarketAccessGate` for every mutating broker/venue path.
3. Add aggregate limit ledger and threshold-change governance.
4. Move Alpaca paper DCA through the shared gate.
5. Add restricted-symbol and authorized-account/operator models.
6. Add normalized post-trade surveillance reports.
7. Add checksum/signature manifest for live-adjacent receipts.

## Bottom Line

FinHarness has the right safety instinct: fail closed, keep brakes local,
separate proposal/risk/execution, force human review, preserve receipts, and
block autonomous live execution. That is genuinely aligned with the spirit of
Rule 15c3-5.

It is not, however, a market-access control system. The missing pieces are not
more indicators or more backtests; they are control-system objects: owner,
authorized persons/accounts, aggregate limits, restricted lists, threshold-change
procedures, immediate surveillance reports, and periodic certification.

The strongest current surface is OKX live gate. The weakest market-access-like
surface is Alpaca paper DCA because it can place marketable paper orders through
a script-local guard instead of a shared pre-trade control plane.

Non-claims:

- This review does not certify compliance with SEC, FINRA, broker, exchange,
  custody, tax, accounting, or books-and-records requirements.
- This review does not authorize live trading.
- This review does not inspect real credentials, account holdings, or private
  broker configuration.
