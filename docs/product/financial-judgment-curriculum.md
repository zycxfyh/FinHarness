# Financial Judgment Curriculum

Status: current
Scope: product capability map / education / agent-assist boundaries
Non-runtime: true

This document defines the financial judgment capabilities FinHarness should help
the user build. It is a capability map, not a runtime roadmap. It does not turn
every finance concept below into an implementation commitment.

The important distinction is not whether finance words may appear. They should.
Users need to learn the real language of markets: Buy / Hold / Sell, target
price, position sizing, stop loss, trade plan, valuation, research report, risk
budget, catalyst, and post-trade review. FinHarness should not sanitize finance
education into vague product-safe euphemisms.

The important distinction is where a word appears and what authority it carries:

- education language teaches the real concepts;
- research/report language states views, assumptions, and evidence;
- runtime artifact language records candidates, checks, reviews, and receipts;
- execution/broker language is only valid in explicit, high-authority,
  controlled execution surfaces.

In short: learn finance in finance language; govern capital action by permission
and consequence.

## Permission And Consequence Posture

FinHarness should not be defined as simply "trading" or "anti-trading." Its
posture depends on permission level, consequence level, evidence quality, and
review state.

```text
posture = f(permission_level, consequence_level, evidence_quality, review_state)
```

| Layer | Posture | Allows | Does not allow |
| --- | --- | --- | --- |
| Default / no authorization | anti-trading | learning, explanation, records, reminders | trade plan, order, broker submission |
| Education / curriculum | pro-learning | real finance language, examples, training tasks | personalized execution authority |
| Research / report | pro-analysis | thesis, Buy / Hold / Sell as research rating language, valuation range, target-price logic, counter-evidence | suitability claim, personal advice, approval |
| Planning | trade-oriented | trade idea, risk budget, position sizing candidate, stop-loss logic, TradePlanCandidate | order ticket, broker instruction |
| Review | anti-unaudited | allow / deny / defer / request more evidence for next stage | execution authorization by implication |
| Execution candidate | anti-unauthorized execution | order candidate staging under explicit constraints | broker submission |
| Explicit execution | controlled execution | limited broker submission under explicit authorization, limits, kill switch, receipt, post-review | default automation, unlimited authority |
| Post-action | pro-learning / anti-repeat-error | attribution, lesson, rule candidate, behavior review | treating outcome as proof of correctness |

The invariant is not "never trade." The invariant is that a lower-authority layer
cannot pretend to be a higher-authority layer.

## Core Invariants

These statements are stronger than any slogan:

- low permission cannot masquerade as high permission;
- research cannot masquerade as personalized suitability or approval;
- valuation cannot masquerade as certainty;
- a plan cannot masquerade as an order;
- review cannot masquerade as execution authorization;
- paper trading or simulation cannot masquerade as live execution;
- receipt evidence cannot masquerade as correctness;
- agent output cannot masquerade as human responsibility;
- broker submission receipt cannot masquerade as execution success or strategy
  correctness;
- outcome does not become a lesson until reviewed.

## Curriculum Is Not A Runtime Roadmap

This map answers:

- what the user should learn to judge;
- where agents can assist;
- where FinHarness can later support evidence, review, simulation, candidate,
  receipt, or learning surfaces;
- which interpretations are not allowed at a given layer.

It does not say:

- build every module now;
- turn education examples into automated recommendations;
- turn research ratings into personal advice;
- turn trade plans into orders;
- add broker execution by default.

## Six Capability Layers

### 1. Financial Worldview

The user should learn to judge:

- finance as resource allocation across time, risk, cash flow, rights, and
  price;
- why markets exist: financing, investing, hedging, liquidity, and price
  discovery;
- who bears risk and who earns what;
- how households, companies, governments, and financial institutions connect
  through balance sheets.

Agents may assist by:

- explaining market structure;
- mapping participants such as banks, brokers, exchanges, market makers,
  custodians, clearing houses, pension funds, insurers, hedge funds, and retail
  investors;
- turning a market question into a money-flow or risk-transfer diagram.

FinHarness surfaces may support:

- financial glossary;
- market structure notes;
- source-linked concept cards;
- educational walkthroughs.

Allowed outputs:

- money-flow map;
- player map;
- asset-class ontology;
- plain-language concept explanation.

Forbidden interpretations:

- a world map is not a trade recommendation;
- a market-structure explanation is not a claim that a specific user should act.

### 2. Language And Facts

The user should learn to judge:

- return, volatility, drawdown, Sharpe, beta, alpha;
- interest rate, discount rate, risk-free rate, risk premium;
- PE, PB, PS, EV/EBITDA;
- duration, credit spread, yield curve;
- leverage, margin, liquidation risk, liquidity risk;
- nominal return, real return, inflation-adjusted return;
- price, value, narrative, expectation, and fact.

Agents may assist by:

- defining terms in plain language;
- extracting facts from filings, statements, reports, and market data;
- separating fact, claim, inference, assumption, uncertainty, and non-claim.

FinHarness surfaces may support:

- glossary and terminology map;
- research evidence;
- claim/evidence separation;
- source_refs and as_of timestamps.

Allowed outputs:

- fact table;
- term card;
- evidence pack;
- source-linked summary.

Forbidden interpretations:

- a fact summary is not authority to act;
- a market statistic is not a complete thesis.

### 3. Analysis And Valuation

The user should learn to judge:

- what a company owns, owes, earns, and converts to cash;
- whether growth is healthy;
- whether capital expenditure, research spending, debt, buybacks, and dividends
  help or hurt long-term value;
- why a good company can be a bad stock at the wrong price;
- how DCF, comparable companies, implied expectations, and scenario valuation
  constrain stories.

Agents may assist by:

- reading financial statements;
- drafting one-page company health reports;
- building valuation assumptions;
- producing DCF, comps, sensitivity, and implied-expectation explanations;
- generating counter-evidence and uncertainty lists.

FinHarness surfaces may support:

- evidence pack;
- research note;
- valuation scenario;
- uncertainty set;
- review note draft.

Allowed outputs:

- Buy / Hold / Sell as educational or research-rating language when clearly
  scoped to a report context;
- target price logic tied to assumptions and time horizon;
- valuation range;
- bull/base/bear scenarios;
- research conclusion.

Forbidden interpretations:

- a research rating is not personalized suitability;
- a target price is not a guarantee;
- a valuation range is not an execution instruction;
- a research report is not a broker order.

### 4. Portfolio And Risk

The user should learn to judge:

- single-asset risk versus portfolio risk;
- correlation, concentration, drawdown, VaR, stress tests, and scenario risk;
- risk budget and maximum tolerable loss;
- why correct direction can still lose money through size, leverage, timing, or
  liquidity;
- how a trade affects the whole portfolio, not only the traded asset.

Agents may assist by:

- identifying exposures;
- estimating drawdown and stress scenarios;
- finding crowded or correlated risks;
- drafting position sizing candidates;
- identifying stop-loss, exit, or disconfirmation conditions.

FinHarness surfaces may support:

- preflight;
- simulation report;
- TradePlanCandidate;
- CapitalObjectiveFit;
- TradePlanReviewGate;
- future risk budget checks.

Allowed outputs:

- risk budget;
- position sizing candidate;
- stop-loss logic;
- exit condition candidate;
- portfolio impact summary;
- do-nothing alternative.

Forbidden interpretations:

- position sizing analysis is not an order quantity;
- stop-loss logic is not a broker stop order;
- a preflight pass is not trade approval;
- an objective fit is not investment advice.

### 5. Behavior And AI Decision Control

The user should learn to judge:

- loss aversion, confirmation bias, overconfidence, revenge trading, anchoring,
  hindsight narrative, and meme-driven impatience;
- when an AI response is helping analysis versus rationalizing an impulse;
- how to ask for counter-evidence;
- how to separate idea, fact, evidence, conclusion, plan, and action.

Agents may assist by:

- doing blindspot passes;
- generating counter-evidence;
- flagging missing assumptions;
- drafting review questions;
- identifying behavior patterns after gains and losses;
- helping convert a lesson into a rule candidate.

FinHarness surfaces may support:

- agentic unknowns protocol;
- review notes;
- behavioral risk flags;
- post-action review;
- lesson and rule-change loop.

Allowed outputs:

- impulse check;
- revenge-trade check;
- narrative-rationalization warning;
- counter-evidence list;
- open questions;
- review prompt.

Forbidden interpretations:

- agent confidence is not correctness;
- a persuasive explanation is not evidence;
- a behavior warning is not a moral judgment;
- a lesson candidate is not a rule until promoted.

### 6. Project-Based Training

The user should learn to produce:

- personal balance sheet and cash-flow dashboard;
- ETF allocation plan;
- single-company research report;
- event-driven review;
- trade plan and risk-control record;
- weekly market review;
- monthly portfolio review;
- error log and concept cards.

Agents may assist by:

- structuring the assignment;
- retrieving and organizing sources;
- drafting first-pass artifacts;
- checking for missing evidence;
- preparing a review quiz;
- comparing the user's actual artifact against the curriculum rubric.

FinHarness surfaces may support:

- tutorials;
- golden paths;
- sample receipts;
- learning cockpit;
- review workspace;
- practice workflows.

Allowed outputs:

- complete research report;
- trade plan exercise;
- paper-trade record;
- event review;
- concept card;
- portfolio health report.

Forbidden interpretations:

- a training artifact is not a live instruction;
- a paper-trade plan is not an actual broker submission;
- a sample receipt is not a production receipt.

## Real Finance Language By Layer

FinHarness should not ban finance terms. It should preserve their meaning and
control their authority.

| Term | Curriculum / education | Research / report | Runtime artifact | Execution / broker |
| --- | --- | --- | --- | --- |
| Buy / Hold / Sell | Real rating language users must understand. | Permitted as report rating when source, assumptions, and scope are clear. | Should be stored as research stance or external report content, not user-specific approval. | Not an order. |
| Trading advice | Discuss as an industry and regulatory concept. | Avoid as FinHarness-authored phrasing unless quoting or classifying external content. | Use candidate thesis / review evidence semantics. | Requires explicit authorization and broker workflow if it becomes action. |
| Target price | Teach how it comes from assumptions. | Permitted with valuation method, time horizon, and scenario. | Store as valuation scenario or implied expectation range. | Not executable price unless converted later into an order candidate. |
| Position sizing | Teach sizing, risk budget, and max loss. | Permitted as sizing analysis. | Position sizing candidate / risk-budget-bounded sizing. | Not broker quantity until order candidate stage. |
| Stop loss | Teach as disconfirmation and risk control. | Permitted as exit thesis. | Exit condition candidate / disconfirmation condition. | Not a stop order until explicit order candidate stage. |
| Trade plan | Core practical training artifact. | Permitted as plan structure. | TradePlanCandidate / reviewable trade plan. | Not an order ticket. |
| Trade Plan Receipt | Useful educational phrase. | Can describe review evidence. | Prefer TradePlanCandidate receipt / review evidence receipt. | Not execution receipt. |

## Relationship To Current Capital Action Pipeline

The current mainline already contains the beginning of a judgment-to-action
pipeline:

```text
CapitalMandate
  → AgentAuthorityGrant
  → ActionIntentAuthorityBinding
  → ActionIntentPreflight
  → ActionIntentSimulationReport
  → TradePlanCandidate
  → CapitalObjectiveFit
  → TradePlanReviewGate
```

This pipeline should not become an approval machine, but it also should not
pretend that finance stops before trading. Its purpose is to let capital action
move only as far as evidence, permission, consequence, and review allow.

The curriculum supplies the capability map behind that pipeline:

- financial worldview keeps trades from becoming isolated bets;
- language and facts keep claims grounded;
- analysis and valuation constrain stories;
- portfolio and risk control size and downside;
- behavior and AI decision control reduce self-rationalization;
- project training turns repeated practice into durable judgment.

## Decision Fork

After evidence, hypothesis, valuation, and risk analysis, the right next step is
not always a trade. The system should support a fork:

```text
Raw Data
  → Financial State
  → Evidence / Claims
  → Hypothesis
  → Valuation / Risk / Portfolio Impact
  → Decision Fork
      ├── Research Note
      ├── Watchlist
      ├── Paper Trade
      ├── TradePlanCandidate
      ├── Defer / Request More Evidence
      └── Controlled Execution Path
```

Trading is a legitimate exit under the right permission and consequence layer.
It is not the default exit, and it is not the only useful exit.

## Scope Notes

This document is a financial judgment curriculum and product capability map. It
describes what users should learn to reason about, where agents can assist, and
where FinHarness may later support evidence, review, receipt, simulation,
candidate, or learning surfaces.

It is not an API contract, a broker integration plan, a suitability framework,
or a commitment to implement every module named here.

