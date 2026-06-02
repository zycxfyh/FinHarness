# Hypotheses Layer Institutional Practices

Date: 2026-06-02

## Question

How should FinHarness build layer 5, the Hypotheses layer, after the
Interpretation layer is complete?

## Short Answer

The layer should not try to predict or recommend. It should convert
source-backed interpretation into falsifiable research statements that the next
layer can validate.

The practical shape is:

```text
interpretation
-> hypothesis
-> expected observations
-> disconfirming evidence
-> validation plan
-> receipt
```

## What Top Practitioners Suggest

### Man AHL: Testable Ideas Only

Man AHL publicly describes its approach as scientific and empirical. It states
that it only trades ideas and theories that can be tested and proved, and that
technology helps move models from concept through back-testing and into
production trading.

Implication for FinHarness:

```text
Hypotheses must be written so they can become validation jobs.
Untestable narrative is not a valid fifth-layer output.
```

Reference:

```text
https://www.man.com/ahl
```

### AQR: Economic Intuition, Research Precision, Multiple Testing

AQR describes systematic investing as grounded in economic theory, with
research and precision applying from design to implementation. AQR also
highlights the multiple-testing problem in financial research: when researchers
run many analyses and report only the best, false findings become more likely.

Implication for FinHarness:

```text
Each hypothesis needs:
  economic or market mechanism
  explicit test plan
  record of rejected or weak variants
  warning against treating one good backtest as truth
```

References:

```text
https://www.aqr.com/What-We-Do/Our-Approach
https://www.aqr.com/Insights/Research/Journal-Article/A-Data-Science-Solution-to-the-Multiple-Testing-Crisis-in-Financial-Research?aqrPDF=1
```

### Bridgewater: Expose Ideas And Be Willing To Be Wrong

Bridgewater's idea meritocracy language emphasizes truth, transparency, and
speaking honestly while being willing to be wrong.

Implication for FinHarness:

```text
Hypotheses should carry their own failure mode.
The system should make disconfirmation normal, not embarrassing.
```

Reference:

```text
https://www.bridgewater.com/culture/bridgewaters-idea-meritocracy
```

### BlackRock / Aladdin: Scenario And Risk Context, Not Prediction Certainty

BlackRock's Aladdin materials emphasize risk workflow, transparency, and
portfolio visibility, while its disclosures state that risk models are based on
assumptions and cannot predict every loss scenario.

Implication for FinHarness:

```text
Hypotheses must be assumption-bound.
They should point to scenario and validation work, not claim certainty.
```

References:

```text
https://www.blackrock.com/aladdin/products/aladdin-risk
https://www.blackrock.com/us/individual/literature/whitepaper/alpha-reimagined-en.pdf
```

## FinHarness Translation

Layer 4 says:

```text
This event may matter through these mechanisms.
```

Layer 5 should say:

```text
If that mechanism is real, then these observable things should happen.
If these other observable things happen, the hypothesis weakens or fails.
The next layer should test these exact checks.
```

Layer 5 must not say:

```text
Take a trade.
Increase risk.
This is validated.
This is alpha.
```

## Proposed Hypothesis Record

```text
hypothesis_id
source_interpretation_ids
source_event_ids
symbol
mechanism
hypothesis
horizon
expected_observations
disconfirming_observations
validation_plan
assumptions
confidence_prior
status
created_at_utc
```

Example shape:

```text
If NVDA's 10-Q meaningfully changes investor understanding of data-center
revenue durability, then later filing details, management commentary, price /
volume reaction, and semiconductor basket context should show confirming
evidence over a quarters horizon.

The hypothesis weakens if the filing is mostly backward-looking, market
expectations already reflected the content, or related index / basket reaction
contradicts the single-name move.
```

## Proposed Quality Gates

```text
source_backed_hypotheses
testable_predictions_present
disconfirming_evidence_present
horizon_present
validation_plan_present
no_execution_language
no_recommendation_language
claim_not_marked_validated
temporal_context_separated
duplicate_hypothesis_check
```

The `temporal_context_separated` gate exists because the Hermes LLM experiment
showed a real risk: the model may mix a current quote snapshot with an older
historical price window unless every fact keeps its source and time context.

## Proposed Workflow

```text
source_config
-> load_interpretation_snapshot
-> select_hypothesis_candidates
-> formulate_hypotheses
-> attach_disconfirming_evidence
-> attach_validation_plan
-> quality
-> lineage
-> snapshot
-> receipt
-> consumer_handoff
-> review_hook
-> final
```

## First MVP Boundary

```text
input:
  InterpretationSnapshot from the SEC EDGAR slice

method:
  rule-guided template

universe:
  Magnificent Seven
  SPY / QQQ as context

max output:
  10 hypothesis records

execution:
  disabled
```

## Design Judgment

The fifth layer is the first layer where FinHarness becomes meaningfully
research-native. It is no longer only collecting data or explaining events. It
is shaping questions that can be proven wrong.

That is the edge:

```text
not faster prediction
not more confident narrative
but better falsifiable thinking
```
