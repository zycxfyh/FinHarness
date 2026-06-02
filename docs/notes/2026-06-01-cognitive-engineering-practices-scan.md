# Cognitive Engineering Practices Scan

Date: 2026-06-01

Purpose: compare how leading engineering organizations, scientific institutions,
and business operators preserve knowledge, decisions, experiments, and lessons;
then adapt the useful parts to FinHarness.

## Core Compression

Across industry, academia, and business, top organizations converge on one
principle:

```text
important thinking must become structured, reviewable, reusable state
```

They use different names:

```text
postmortems
ADRs
RFCs
KEPs
lessons learned
data management plans
preregistrations
working backwards documents
A3 reports
handbooks
```

But the pattern is the same:

```text
before action:
  clarify intent, assumptions, plan, and success criteria

during action:
  track evidence, changes, decisions, and anomalies

after action:
  review outcomes, extract lessons, update the system
```

FinHarness should copy the pattern, not the bureaucracy.

## Industry / Engineering

### Google SRE: Blameless Postmortems

Google SRE treats postmortems as a core reliability practice.

Useful pattern:

```text
significant event triggers written postmortem
record impact, timeline, root causes, action items
review the postmortem
share it broadly enough to spread learning
focus on systems and conditions, not blame
```

FinHarness adaptation:

```text
Every meaningful workflow failure, bad proposal, data issue, or risk-gate miss
should produce a review receipt or postmortem.
```

Important boundary:

```text
not every tiny issue needs a postmortem
define triggers before the incident
```

### Microsoft / ADR Practice: Architecture Decision Records

Microsoft's architecture guidance treats ADRs as important deliverables for
documenting architectural decisions, context, alternatives, and implications.

Useful pattern:

```text
record architecturally significant decisions
include ruled-out alternatives
maintain the ADR over the workload lifetime
use it as an append-only decision log
```

FinHarness adaptation:

```text
Use ADRs for provider choice, durable schema shape, permission model,
module boundaries, and execution authority decisions.
```

### Rust RFCs / Kubernetes KEPs

Rust RFCs and Kubernetes KEPs are proposal-before-implementation mechanisms for
substantial changes.

Useful pattern:

```text
motivation before implementation
goals and non-goals
detailed design
alternatives and drawbacks
review before large code change
implementation tracked after acceptance
```

FinHarness adaptation:

```text
Use docs/proposals/ before building new layers such as Events,
Interpretation, Hypotheses, Proposals, or Review.
```

### NASA Lessons Learned

NASA maintains an official lessons learned system with reviewed lessons from
programs and projects. Lessons include the original driving event and
recommendations that feed continuous improvement.

Useful pattern:

```text
lessons are curated, searchable, and reviewed
lessons feed training, best practices, policy, and procedure
knowledge has owners and operational responsibility
```

FinHarness adaptation:

```text
Do not only store receipts. Periodically distill receipts into lessons.
```

This means:

```text
receipt -> review -> lesson -> module upgrade / ADR / checklist
```

## Academia / Science

### NIH Data Management And Sharing

NIH's Data Management and Sharing policy expects researchers to plan how data
will be managed and shared, promoting validation, reuse, and accessibility.

Useful pattern:

```text
plan data management before research
preserve data so others can validate and reuse it
make repository and sharing plans explicit
```

FinHarness adaptation:

```text
MarketDataSnapshot and IndicatorSnapshot should always keep lineage, hashes,
payload refs, and quality reports.
```

The lesson:

```text
data without management plan is not research-grade evidence
```

### OSF Preregistration / Registered Reports

Open Science Framework preregistration creates a time-stamped, read-only study
plan before data collection or analysis.

Useful pattern:

```text
separate planned hypothesis from after-the-fact explanation
make analysis plan visible before results
detect deviation between plan and outcome
```

FinHarness adaptation:

```text
Before major experiments, write a proposal or hypothesis record:

hypothesis
data
method
success signal
failure mode
decision rule
```

After the experiment:

```text
compare planned analysis with actual result
record deviations explicitly
```

This is directly relevant to trading research because finance is vulnerable to:

```text
p-hacking
narrative fitting
overfitting
survivorship bias
selective memory
```

### Nature / Reproducibility Norms

Nature Portfolio reporting standards emphasize transparency of reporting,
availability of data, materials, code, and protocols, and reproducibility.

Useful pattern:

```text
data, code, methods, and protocols must be available enough for review
```

FinHarness adaptation:

```text
Every workflow result should link to:

source data
code path
parameters
quality report
receipt
test evidence
```

## Business / Management

### Finance / Investment: CFA Institute And BlackRock Aladdin

CFA Institute's professional standards emphasize diligence, reasonable basis,
and records that support investment analysis, recommendations, and actions.
BlackRock's Aladdin materials show the institutional direction from isolated
analysis toward integrated portfolio, risk, data, scenario, and oversight
workflows.

Useful pattern:

```text
investment action needs a reasonable basis
recommendations need supporting records
risk and return should be visible across the whole portfolio
scenario analysis and stress testing belong near the decision workflow
```

FinHarness adaptation:

```text
Every proposal should be able to answer:

what data was used?
what analysis supported the view?
what alternatives were considered?
what risk, sizing, and scenario checks were performed?
what record proves this was not just a narrative?
```

The deeper lesson:

```text
AI-generated financial reasoning must become auditable investment reasoning.
```

### Amazon: Working Backwards And Builders' Library

Amazon's culture emphasizes customer obsession, working backwards, ownership,
dive deep, high standards, and written mechanisms. The Builders' Library turns
Amazon engineering lessons into reusable public operating knowledge.

Useful pattern:

```text
start from desired customer/user outcome
write narrative before building
use repeatable mechanisms
convert lessons into reusable library knowledge
```

FinHarness adaptation:

```text
Before building a large feature, write:

who is the user?
what decision gets better?
what evidence will they see?
what risk is reduced?
what does the receipt prove?
```

For FinHarness, the "customer" can be:

```text
future self
future agent
research workflow
risk gate
paper-trade reviewer
```

### Toyota: A3 / PDCA

Toyota-style A3 thinking compresses problem understanding, root cause,
countermeasures, implementation, and follow-up onto a constrained problem
solving document. It is deeply tied to PDCA.

Useful pattern:

```text
force concise problem understanding
show current condition
analyze causes
choose countermeasures
follow up and reflect
```

FinHarness adaptation:

```text
Use one-page module proposals for small vertical slices:

problem
current condition
target condition
root cause / bottleneck
countermeasure
test
follow-up
```

This guards against architecture drift.

## Shared Pattern

The top-level shared pattern is:

```text
1. Externalize important cognition.
2. Structure it enough to be reviewed.
3. Link it to evidence.
4. Preserve alternatives and rejected paths.
5. Run the work.
6. Review outcomes.
7. Update future behavior.
```

This maps directly onto FinHarness:

```text
ideas:
  optionality and raw observations

think:
  first-principles reasoning

notes:
  research and implementation synthesis

modules:
  current truth and upgrade history

ADRs:
  architecture decisions and alternatives

proposals:
  preregistered design for major work

receipts:
  runtime evidence

tests:
  behavioral evidence

reviews:
  lessons and process updates
```

## What Not To Copy

Do not copy the full ceremony of large organizations.

Avoid:

```text
approval theater
huge templates
writing before thinking
documentation without owners
stale handbooks
postmortems without action
preregistration without review
lessons learned that nobody searches
```

The small-project version must stay lightweight.

## FinHarness Operating Rule

Use the smallest durable artifact that protects future learning:

```text
small thought:
  idea/backlog entry

substantial insight:
  think note

external research:
  notes scan

module change:
  module upgrade log

architecture decision:
  ADR

major new layer:
  proposal before code

runtime action:
  receipt

failure or surprise:
  review / lesson
```

## Immediate Recommendation

FinHarness should keep the current cognitive engineering system.

But add one more loop:

```text
monthly or milestone-based lesson distillation
```

Procedure:

```text
1. Review new ideas, notes, ADRs, modules, receipts, and tests.
2. Extract repeated patterns and failures.
3. Promote durable lessons into AGENTS.md, module docs, or checklists.
4. Archive or reject stale ideas.
5. Choose the next vertical slice.
```

This is the bridge between:

```text
recording knowledge
and
becoming a learning system
```

## Sources

- Google SRE postmortem culture:
  https://sre.google/sre-book/postmortem-culture/
- Google SRE postmortem workbook:
  https://sre.google/workbook/postmortem-culture/
- Microsoft ADR guidance:
  https://learn.microsoft.com/en-ie/azure/well-architected/architect-role/architecture-decision-record
- ADR overview:
  https://adr.github.io/
- Rust RFCs:
  https://github.com/rust-lang/rfcs
- Kubernetes Enhancement Proposals:
  https://www.kubernetes.dev/resources/keps/
- NASA Lessons Learned:
  https://www.nasa.gov/nasa-lessons-learned/
- NASA Knowledge Management:
  https://www.nasa.gov/learning-resources/for-professionals/appel-knowledge-management/
- NIH Data Management and Sharing Policy:
  https://www.grants.nih.gov/policy-and-compliance/policy-topics/sharing-policies/dms/policy-overview
- OSF registrations and preregistrations:
  https://help.osf.io/article/330-welcome-to-registrations
- Nature reporting standards:
  https://www.nature.com/ncomms/editorial-policies/reporting-standards
- CFA Institute Standard V(A), Diligence and Reasonable Basis:
  https://www.cfainstitute.org/standards/professionals/code-ethics-standards/standards-of-practice-v-a
- CFA Institute Standard V(C), Record Retention:
  https://www.cfainstitute.org/standards/professionals/code-ethics-standards/standards-of-practice-v-c
- BlackRock Aladdin Risk:
  https://www.blackrock.com/aladdin/products/aladdin-risk
- BlackRock Aladdin whole portfolio brochure:
  https://www.blackrock.com/aladdin/literature/product-brief/aladdin-whole-portfolio-brochure.pdf
- Amazon Leadership Principles:
  https://www.aboutamazon.com/working-at-amazon/our-leadership-principles
- Amazon Builders' Library:
  https://aws.amazon.com/builders-library/faqs/
- Lean Enterprise Institute, A3 / PDCA problem solving:
  https://www.lean.org/events-training/events/intro-to-problem-solving/
