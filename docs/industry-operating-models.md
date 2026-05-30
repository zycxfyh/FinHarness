# Industry Operating Models

This document is a memory map for learning industries from first principles.
It deliberately removes trivia. For each industry, remember only:

1. What scarce problem does it solve?
2. What flows through the system?
3. Who captures value?
4. What can break?
5. Which numbers prove the business is healthy?

Use Occam's razor: if a detail does not change incentives, risk, cash flow, or
execution, ignore it until later.

## Universal Pattern

Every industry can be reduced to this loop:

```text
Input -> Transformation -> Distribution -> Payment -> Risk Control -> Feedback
```

Every company can be reduced to this machine:

```text
Acquire resources -> Create value -> Deliver value -> Collect cash -> Reinvest
```

Every institution has five layers:

```text
Front office: wins customers, deals, orders, or users
Middle office: measures risk, quality, pricing, and performance
Back office: settles, records, supports, reconciles, reports
Infrastructure: data, systems, logistics, compliance, security
Capital layer: funding, ownership, leverage, cash conversion
```

## How To Study Any Industry

Ask these questions in order:

1. What is the unit of value?
   Example: barrel of oil, seat-mile, loan, trade, ad impression, kilowatt-hour.

2. Who pays, and why now?
   Separate user, buyer, payer, regulator, and beneficiary.

3. What is the main bottleneck?
   Demand, supply, trust, distribution, capital, regulation, talent, or data.

4. What is the cost structure?
   Fixed cost, variable cost, marginal cost, working capital, depreciation.

5. What is the risk that kills the business?
   Liquidity, fraud, leverage, commodity price, regulation, safety, churn.

6. What metric tells the truth?
   Do not memorize 30 metrics. Find the one that exposes the engine.

## Finance

Core problem: move money across time, risk, and trust.

Flow:

```text
Capital -> Underwriting/pricing -> Allocation -> Execution -> Risk control -> Return
```

Main actors:

```text
Banks: transform deposits and credit.
Asset managers: allocate other people's capital.
Insurers: pool risk across many people.
Exchanges/brokers: connect buyers and sellers.
Market makers: provide liquidity and earn spread.
Payment networks: move money reliably.
```

Key metrics:

```text
Return on equity
Net interest margin
Assets under management
Loss ratio
Default rate
Value at risk
Max drawdown
Liquidity coverage
```

What can break:

```text
Leverage
Bad underwriting
Duration mismatch
Liquidity run
Fraud
Model error
Regulatory breach
```

First principle:

Finance is not "money making". It is pricing trust under uncertainty.

## Banking

Core problem: borrow short, lend long, and manage trust.

Flow:

```text
Deposits/funding -> Credit underwriting -> Loan book -> Interest collection -> Loss reserves
```

Key roles:

```text
Relationship managers
Credit analysts
Risk managers
Treasury
Operations
Compliance
```

Key metrics:

```text
Net interest margin
Non-performing loan ratio
Loan-to-deposit ratio
Capital adequacy
Cost of funds
Credit loss provision
```

What can break:

```text
Bank run
Bad credit cycle
Asset-liability mismatch
Interest-rate shock
Regulatory capital shortage
```

## Asset Management

Core problem: turn capital into risk-adjusted return.

Flow:

```text
Mandate -> Research -> Portfolio construction -> Trading -> Risk monitoring -> Reporting
```

Key roles:

```text
Portfolio manager
Research analyst
Trader
Risk analyst
Client reporting
Compliance
```

Key metrics:

```text
Alpha
Beta
Sharpe ratio
Max drawdown
Tracking error
Turnover
Assets under management
Fee rate
```

What can break:

```text
Style drift
Hidden leverage
Crowded trades
Bad liquidity
Poor risk controls
Client redemptions
```

First principle:

The product is not return. The product is a repeatable risk process.

## Insurance

Core problem: pool uncertain losses and price them before they happen.

Flow:

```text
Policy sale -> Underwriting -> Premium collection -> Investment float -> Claims -> Reserves
```

Key metrics:

```text
Loss ratio
Combined ratio
Premium growth
Reserve adequacy
Investment yield
Solvency ratio
```

What can break:

```text
Underpriced risk
Catastrophe loss
Fraudulent claims
Reserve shortfall
Reinsurance failure
```

## Software

Core problem: automate work with near-zero marginal distribution cost.

Flow:

```text
User pain -> Product -> Acquisition -> Activation -> Retention -> Expansion
```

Key roles:

```text
Product
Engineering
Design
Sales
Customer success
Security
Infrastructure
```

Key metrics:

```text
Monthly recurring revenue
Gross margin
Customer acquisition cost
Lifetime value
Net revenue retention
Churn
Daily/monthly active users
```

What can break:

```text
No real pain
High churn
Weak distribution
Security breach
Platform dependency
Technical debt
```

First principle:

Software compounds when the cost to serve the next user is lower than the value
captured from that user.

## AI / Agent Systems

Core problem: turn data, tools, and reasoning into reliable action.

Flow:

```text
Goal -> Context -> Tool selection -> Execution -> Evaluation -> Memory -> Improvement
```

Key roles:

```text
Model provider
Harness engineer
Data engineer
Eval engineer
Product owner
Security reviewer
Domain expert
```

Key metrics:

```text
Task success rate
Tool-call success rate
Latency
Cost per task
Eval pass rate
Human intervention rate
Regression rate
```

What can break:

```text
Hallucination
Bad tool permissions
Prompt injection
No evals
Unreliable data
Long feedback loops
Over-automation
```

First principle:

The model is not the product. The controlled loop around the model is the
product.

## Manufacturing

Core problem: transform materials into reliable physical goods at scale.

Flow:

```text
Raw materials -> Production planning -> Manufacturing -> Quality control -> Inventory -> Distribution
```

Key metrics:

```text
Yield
Defect rate
Capacity utilization
Gross margin
Inventory turnover
On-time delivery
Unit cost
```

What can break:

```text
Supply disruption
Quality failure
Overcapacity
Inventory build-up
Commodity price shock
Safety incident
```

First principle:

Manufacturing is controlled repetition under cost, quality, and time constraints.

## Energy

Core problem: produce, store, transmit, and price usable power.

Flow:

```text
Resource -> Extraction/generation -> Storage/transmission -> Distribution -> Consumption
```

Key metrics:

```text
Cost per unit
Capacity factor
Reserve replacement
Grid reliability
Utilization
Commodity spread
Carbon intensity
```

What can break:

```text
Commodity price collapse
Political risk
Grid failure
Reserve depletion
Environmental liability
Capital cost overrun
```

First principle:

Energy is civilization's throughput constraint.

## Healthcare

Core problem: improve health outcomes under trust, biology, and payment constraints.

Flow:

```text
Patient need -> Diagnosis -> Treatment -> Monitoring -> Payment -> Outcome measurement
```

Key actors:

```text
Patients
Doctors
Hospitals
Drug/device companies
Insurers
Regulators
Pharmacies
```

Key metrics:

```text
Clinical outcome
Cost per patient
Utilization
Readmission rate
Approval rate
Gross-to-net pricing
Safety events
```

What can break:

```text
Bad incentives
Clinical failure
Regulatory rejection
Safety issue
Reimbursement cut
Data privacy breach
```

First principle:

Healthcare is not just medicine. It is medicine plus incentives plus trust.

## Retail / Consumer

Core problem: match products with consumer desire at the right time and price.

Flow:

```text
Demand sensing -> Sourcing -> Merchandising -> Inventory -> Store/app traffic -> Conversion -> Repeat purchase
```

Key metrics:

```text
Same-store sales
Gross margin
Inventory turnover
Conversion rate
Average order value
Customer acquisition cost
Repeat purchase rate
```

What can break:

```text
Wrong inventory
Weak brand
High returns
Low foot traffic
Price competition
Supply chain delay
```

First principle:

Retail is inventory risk plus customer attention.

## Logistics

Core problem: move goods through space with reliability, speed, and cost control.

Flow:

```text
Order -> Routing -> Pickup -> Line-haul -> Sorting -> Last mile -> Proof of delivery
```

Key metrics:

```text
On-time delivery
Cost per shipment
Utilization
Route density
Damage rate
Fuel cost
Working capital cycle
```

What can break:

```text
Low route density
Fuel shock
Labor shortage
Customs delay
Capacity mismatch
Weather disruption
```

First principle:

Logistics is network density under time pressure.

## Real Estate

Core problem: convert location, capital, and time into usable space.

Flow:

```text
Land/property -> Financing -> Development/operation -> Leasing/sales -> Cash flow -> Refinancing/exit
```

Key metrics:

```text
Occupancy
Net operating income
Cap rate
Loan-to-value
Debt service coverage
Rent growth
Vacancy
```

What can break:

```text
Interest-rate shock
Vacancy
Overbuilding
Refinancing failure
Construction delay
Local policy change
```

First principle:

Real estate is leveraged cash flow tied to location.

## Media / Advertising

Core problem: capture attention and convert it into influence or demand.

Flow:

```text
Content -> Audience -> Attention -> Targeting -> Ad sale/subscription -> Measurement
```

Key metrics:

```text
Active users
Watch time
Engagement
Cost per mille
Click-through rate
Subscriber churn
Ad fill rate
```

What can break:

```text
Audience decay
Platform dependency
Content cost inflation
Ad market weakness
Brand safety issue
Regulation
```

First principle:

Media sells attention. Advertising sells measurable access to that attention.

## Education

Core problem: convert time and guidance into capability, credentials, or status.

Flow:

```text
Learner need -> Curriculum -> Instruction -> Practice -> Assessment -> Credential/outcome
```

Key metrics:

```text
Completion rate
Learning outcome
Placement rate
Retention
Cost per learner
Credential value
Student satisfaction
```

What can break:

```text
Weak outcomes
Low completion
Credential inflation
Poor distribution
Regulatory risk
Misaligned incentives
```

First principle:

Education sells transformation, not content.

## Agriculture / Food

Core problem: turn land, biology, labor, and logistics into safe calories.

Flow:

```text
Inputs -> Production -> Harvest/processing -> Storage -> Distribution -> Consumption
```

Key metrics:

```text
Yield per acre
Input cost
Spoilage
Commodity price
Processing margin
Food safety incidents
Inventory turnover
```

What can break:

```text
Weather
Disease
Commodity volatility
Supply chain failure
Food safety issue
Water scarcity
```

First principle:

Food is biological production under weather and logistics uncertainty.

## Telecom / Networks

Core problem: move information reliably across distance.

Flow:

```text
Spectrum/fiber/capex -> Network buildout -> Subscriber acquisition -> Data usage -> Billing -> Maintenance
```

Key metrics:

```text
Average revenue per user
Churn
Network utilization
Capex intensity
Coverage
Latency
Customer acquisition cost
```

What can break:

```text
High capex
Price war
Regulatory pressure
Network outage
Spectrum constraints
Technology cycle shift
```

First principle:

Telecom is capital-intensive trust in connectivity.

## Government / Public Sector

Core problem: provide public goods and enforce rules.

Flow:

```text
Mandate -> Budget -> Policy/program -> Procurement -> Delivery -> Audit/accountability
```

Key metrics:

```text
Budget execution
Service coverage
Outcome measures
Compliance
Public trust
Cost per citizen served
Cycle time
```

What can break:

```text
Misaligned incentives
Procurement waste
Policy failure
Corruption
Low trust
Poor measurement
```

First principle:

Government operates where markets fail, but must solve coordination and
accountability problems.

## Minimal Memory Table

| Industry | Unit of value | Core flow | Truth metric | Fatal risk |
| --- | --- | --- | --- | --- |
| Finance | Risk-adjusted capital | Capital -> pricing -> allocation -> return | ROE / drawdown | Leverage + liquidity |
| Banking | Loan | Funding -> underwriting -> interest -> loss reserves | NIM / NPL ratio | Run or bad credit |
| Asset management | Portfolio | Mandate -> research -> portfolio -> reporting | Sharpe / alpha | Hidden risk |
| Insurance | Policy | Premium -> underwriting -> float -> claims | Combined ratio | Mispriced risk |
| Software | User/workflow | Pain -> product -> retention -> expansion | NRR / churn | No retention |
| AI agents | Task | Goal -> tools -> eval -> memory | Eval pass rate | Uncontrolled action |
| Manufacturing | Unit | Materials -> production -> QC -> delivery | Yield / unit cost | Quality failure |
| Energy | Usable power | Resource -> generation -> transmission -> use | Cost/unit | Price/policy shock |
| Healthcare | Patient outcome | Diagnosis -> treatment -> payment -> outcome | Outcome/cost | Bad incentives |
| Retail | SKU/order | Sourcing -> inventory -> conversion -> repeat | Inventory turnover | Wrong inventory |
| Logistics | Shipment | Order -> route -> delivery -> proof | On-time cost | Low density |
| Real estate | Space/cash flow | Property -> lease -> cash flow -> refinance | NOI / occupancy | Rate shock |
| Media | Attention | Content -> audience -> monetization | Watch time / ARPU | Audience decay |
| Education | Capability | Curriculum -> practice -> assessment -> outcome | Completion/outcome | Weak transformation |
| Food | Calorie/product | Inputs -> harvest -> processing -> distribution | Yield/spoilage | Weather/safety |
| Telecom | Connection | Capex -> network -> subscriber -> billing | ARPU/churn | Capex trap |
| Government | Public service | Mandate -> budget -> program -> audit | Outcome/cost | Low accountability |

## Daily Practice

For any article, company, or project, write five lines:

```text
Industry:
Unit of value:
Core flow:
Truth metric:
Fatal risk:
```

If you can do this quickly, you are no longer memorizing facts. You are seeing
the operating model.

